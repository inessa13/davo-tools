import datetime
import logging
import os
import pprint
import re
import time

import reprint
import yaml

import davo.utils
from davo import constants, errors, settings

from . import cache, conf, const, tasks, utils, workers

logger = logging.getLogger(__name__)

_CONFIRM_PERMANENT = {}
_MD5_ETAG_RE = re.compile(r"[0-9a-fA-F]{32}")


def _normalise_md5_etag(etag):
    """Return a normalised MD5 ETag, or ``None`` when it is not one."""
    if etag and etag.startswith('"') and etag.endswith('"'):
        etag = etag[1:-1]

    if etag and _MD5_ETAG_RE.fullmatch(etag):
        return etag.lower()

    return None


def _diff_display_lines(files, all_files, root_key="", verbose=False):
    """Return sorted diff lines, collapsing wholly missing directory trees."""
    if verbose:
        return [
            "{} {} {}".format(
                data["state"], key, ", ".join(data.get("comment", []))
            )
            for key, data in files.items()
        ]

    root_key = root_key.rstrip("/")
    root_prefix = "{}/".format(root_key) if root_key else ""
    candidates = {}
    for key, data in files.items():
        state = data["state"]
        if state not in {
            constants.STATE_LOCAL_NEW,
            constants.STATE_LOCAL_MISSING,
        }:
            continue

        parts = key.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            directory = "/".join(parts[:index])
            if not root_prefix or directory.startswith(root_prefix):
                candidates[directory] = state

    collapsed = {}
    for directory, state in candidates.items():
        descendants = [
            data
            for key, data in all_files.items()
            if key.startswith(directory + "/")
        ]
        if len(descendants) > 1 and all(
            data["state"] == state for data in descendants
        ):
            collapsed[directory] = len(descendants)

    # A parent directory represents all of its descendants, so only retain
    # outermost candidates.
    collapsed = {
        directory: count
        for directory, count in collapsed.items()
        if not any(
            directory.startswith(parent + "/") for parent in collapsed
        )
    }

    lines = []
    emitted = set()
    for key, data in sorted(files.items()):
        directory = next(
            (
                parent
                for parent in collapsed
                if key.startswith(parent + "/")
            ),
            None,
        )
        if directory:
            if directory not in emitted:
                lines.append(
                    "{} {}/ ({} files)".format(
                        data["state"], directory, collapsed[directory]
                    )
                )
                emitted.add(directory)
            continue

        lines.append(
            "{} {} {}".format(
                data["state"], key, ", ".join(data.get("comment", []))
            )
        )

    return lines


def on_config(namespace):
    if namespace.local:
        config_path = davo.utils.conf.find_project_config()
        if not config_path:
            raise errors.UserError("Local config not found")
        print("{}:".format(config_path))
        contents = davo.utils.conf._load_yaml_mapping(config_path)  # pylint: disable=protected-access
        config = contents.get("s3", {})
        if not isinstance(config, dict):
            raise errors.UserError("Invalid s3: expected a mapping")
        config = davo.utils.conf.mask_config_secrets(config)
    else:
        config = conf.load_config(mask=True)

    if config:
        pprint.pprint(config)

    else:
        print("Config is empty")


def on_info(namespace):
    if namespace.topic == "topics":
        logger.info("Available topics:")
        pprint.pprint(list(const.TOPICS.keys()))

    elif namespace.topic in const.TOPICS:
        logger.info("Available %s:", namespace.topic)
        pprint.pprint(const.TOPICS[namespace.topic])

    else:
        raise errors.UserError("Invalid topic")


def on_init(namespace):
    config_path = os.path.join(os.getcwd(), settings.PROJECT_CONFIG_NAME)
    contents = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as config_file:
                contents = yaml.safe_load(config_file) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise errors.UserError(
                "Invalid config {}: {}".format(config_path, exc)
            ) from exc
        if not isinstance(contents, dict):
            raise errors.UserError(
                "Invalid config {}: expected a mapping".format(config_path)
            )
    s3 = contents.setdefault("s3", {})
    if not isinstance(s3, dict):
        raise errors.UserError("Invalid s3: expected a mapping")
    s3["BUCKET"] = namespace.bucket
    with open(config_path, "w", encoding="utf-8") as config_file:
        yaml.safe_dump(
            contents,
            config_file,
            default_flow_style=False,
            allow_unicode=True,
        )


def on_list_buckets(_namespace):
    conf.init()

    conn = utils.connect_host()
    for bucket in conn.get_all_buckets():
        logger.info(bucket.name)


def on_diff(namespace, print_details=True):
    conf.init()

    bucket = utils.connect_bucket()
    if not bucket:
        raise errors.UserError("missing bucket")

    if namespace.all:
        modes = constants.STATES_ALL
    else:
        modes = namespace.modes

    path = os.path.abspath(namespace.path)

    src_files = []
    it = utils.iter_local_path(
        path=path,
        recursive=namespace.recursive,
        exclude=conf.get("IGNORE"),
        depth=namespace.depth,
    )
    for file_path in it:
        if not os.path.isfile(file_path):
            continue

        if not utils.check_file_type(file_path, namespace.file_types):
            continue

        key = utils.file_key(file_path)
        if namespace.ignore_case:
            key = key.lower()

        if key == conf.get("CACHE_FILE_NAME"):
            continue

        src_files.append((key, file_path))

    logger.info("%d local objects", len(src_files))

    remote_files = dict()

    if not namespace.no_cache:
        cache.cache.init()
        if not cache.cache.total():
            logger.info("updating cache...")
            utils.update_cache(bucket)

    ls_remote = utils.iter_remote_path(
        bucket,
        path,
        recursive=namespace.recursive,
        cached=not namespace.no_cache,
        depth=namespace.depth,
    )

    for file_ in ls_remote:
        if davo.utils.path.is_excluded(file_.name, conf.get("IGNORE")):
            continue

        if not utils.check_file_type(file_.name, namespace.file_types):
            continue

        key = file_.name
        if namespace.ignore_case:
            key = key.lower()

        remote_files[key] = dict(
            key=file_,
            name=file_.name,
            size=file_.size,
            modified=file_.last_modified,
            md5=_normalise_md5_etag(file_.etag),
            etag=file_.etag,
            state=constants.STATE_LOCAL_MISSING,
            comment=[],
            local_path=utils.file_path(file_.name),
        )

    if not namespace.no_cache:
        logger.info("%d remote objects, using cache", len(remote_files.keys()))
    else:
        logger.info("%d remote objects", len(remote_files.keys()))

    if not src_files and not remote_files:
        return None

    logger.info("comparing...")
    for key, f_path in src_files:
        stat = os.stat(f_path)

        if key in remote_files:
            equal = True
            remote = remote_files[key]
            remote["local_path"] = f_path

            if stat.st_size != remote["size"]:
                equal = False
                if remote["size"]:
                    diff = stat.st_size * 100 / float(remote["size"])
                else:
                    diff = 0
                remote["comment"].append("size: {:.2f}%".format(diff))

            elif namespace.md5:
                local_md5 = davo.utils.path.file_hash(f_path).hexdigest()
                remote_md5 = remote["md5"]
                if remote_md5 is None:
                    logger.warning(
                        "cannot compare MD5 for %s: S3 ETag %r is not a "
                        "single-part MD5",
                        remote["name"],
                        remote["etag"],
                    )
                elif local_md5 != remote_md5:
                    equal = False
                    if getattr(namespace, "verbose", False):
                        remote["comment"].append(
                            "md5: local {}, remote {}".format(
                                local_md5, remote_md5
                            )
                        )
                    else:
                        remote["comment"].append("md5: different")

            if equal:
                remote.update(state=constants.STATE_EQUAL, comment=[])
            else:
                remote["local_size"] = stat.st_size
                local_modified = datetime.datetime.fromtimestamp(
                    stat.st_ctime
                ).replace(microsecond=0)
                remote_modified = datetime.datetime.strptime(
                    remote["modified"], "%Y-%m-%dT%H:%M:%S.000Z"
                )
                remote_modified += datetime.timedelta(hours=4)

                delta = local_modified - remote_modified
                if delta.days > 1:
                    remote["comment"].append(
                        "modified: remote {0} days older".format(delta.days)
                    )
                else:
                    remote["comment"].append("modified: {0}".format(delta))

                if namespace.force_upload:
                    remote["state"] = constants.STATE_LOCAL_NEWER

                elif namespace.force_download:
                    remote["state"] = constants.STATE_LOCAL_OLDER

                elif local_modified > remote_modified:
                    remote["state"] = constants.STATE_LOCAL_NEWER

                else:
                    remote["state"] = constants.STATE_LOCAL_OLDER

            if remote["state"] not in modes:
                del remote_files[key]

        else:
            if (
                constants.STATE_LOCAL_NEW not in modes
                and constants.STATE_RENAMED not in modes
            ):
                continue

            remote_files[key] = dict(
                local_size=stat.st_size,
                local_path=f_path,
                modified=stat.st_mtime,
                md5=None,
                state=constants.STATE_LOCAL_NEW,
                comment=[],
            )
            if conf.get("ALLOWED_EXTENSIONS"):
                ext = davo.utils.path.get_extension(f_path, lower=True)
                if ext not in conf.get("ALLOWED_EXTENSIONS"):
                    remote_files[key]["state"] = constants.STATE_INVALID_TYPE
            if namespace.md5:
                remote_files[key]["md5"] = davo.utils.path.file_hash(
                    f_path
                ).hexdigest()

    # find renames
    if constants.STATE_RENAMED in modes:
        to_del = []
        for key, new_data in remote_files.items():
            if new_data["state"] != constants.STATE_LOCAL_NEW:
                continue
            for name, data in remote_files.items():
                if data["state"] != constants.STATE_LOCAL_MISSING:
                    continue
                if data["size"] != new_data["local_size"]:
                    continue
                if namespace.md5 and data["md5"] != new_data["md5"]:
                    continue
                remote_files[name].update(
                    state=constants.STATE_RENAMED,
                    local_name=key,
                    local_size=new_data["local_size"],
                )
                remote_files[name]["comment"].append("new: {0}".format(key))
                to_del.append(key)
                break

        for key in to_del:
            del remote_files[key]

    all_files = remote_files
    remote_files = {
        k: v for k, v in remote_files.items() if v["state"] in modes
    }

    if print_details and not namespace.brief:
        root_key = utils.file_key(path)
        for line in _diff_display_lines(
            remote_files,
            all_files,
            root_key=root_key,
            verbose=getattr(namespace, "verbose", False),
        ):
            print(line)

    davo.utils.path.count_diff(remote_files, verbose=True)

    return bucket, remote_files


def on_update(namespace):
    conf.init()
    if namespace.threads:
        conf.option("THREAD_MAX_COUNT", value=namespace.threads)

    bucket, files = on_diff(namespace, print_details=False)
    if not files:
        logger.error("no changes")
        return

    logger.info("processing...")

    _t = time.time()
    processed, size = 0, 0

    try:
        processed, size = _update(bucket, files, namespace)
    finally:
        delta = time.time() - _t
        if delta:
            speed = davo.utils.format.humanize_speed(size / delta)
            logger.info("average speed: %s", speed)

        logger.info(
            "%d actions processed, %d skipped",
            processed,
            len(files.keys()) - processed,
        )


def _update(bucket, files, namespace):
    processed = 0
    size = 0

    pool = workers.ThreadPool(conf.get("THREAD_MAX_COUNT"))

    for name, data in files.items():
        action = None

        if data["state"] == constants.STATE_EQUAL:
            processed += 1
            continue

        elif data["state"] == constants.STATE_LOCAL_NEW:
            if namespace.upload:
                action = tasks.Upload()
            elif namespace.delete_local:
                action = tasks.DeleteLocal()
            elif namespace.quiet:
                continue
            else:
                act = _confirm_update(
                    name, data, tasks.Upload(), tasks.DeleteLocal()
                )
                if act == "n":
                    continue
                else:
                    action = act

        elif data["state"] == constants.STATE_LOCAL_MISSING:
            if namespace.download:
                action = tasks.Download()
            elif namespace.delete_remote:
                action = tasks.DeleteRemote()
            elif namespace.quiet:
                continue
            else:
                act = _confirm_update(
                    name, data, tasks.Download(), tasks.DeleteRemote()
                )

                if act == "n":
                    continue
                action = act

        elif data["state"] == constants.STATE_RENAMED:
            if _check(name, data, namespace.quiet, namespace.rename_remote):
                action = tasks.RenameRemote()
            elif _check(name, data, namespace.quiet, namespace.rename_local):
                action = tasks.RenameLocal()
            else:
                continue

        elif data["state"] == constants.STATE_LOCAL_NEWER:
            if _check(name, data, namespace.quiet, namespace.replace_upload):
                action = tasks.ReplaceUpload()
            else:
                continue

        elif data["state"] == constants.STATE_LOCAL_OLDER:
            if _check(name, data, namespace.quiet, namespace.replace_download):
                action = tasks.Download()
            else:
                continue

        if not action:
            logging.error("Unknown action")
            continue
        pool.add_task(action.init(bucket, name, data))
        processed += 1

        if isinstance(action, tasks.Download):
            size += data.get("size") or 0
        elif isinstance(action, (tasks.Upload, tasks.ReplaceUpload)):
            size += data.get("local_size") or 0

        if processed >= namespace.limit > 0:
            logger.info("list limit reached!")
            break

    with reprint.output(initial_len=conf.get("THREAD_MAX_COUNT")) as output:
        pool.start(output)
        pool.join()

    return processed, size


def _check(name, data, quiet, confirm):
    if confirm:
        return True
    if quiet:
        return False

    return _confirm_update(name, data, "y") == "y"


def _confirm_update(name, data, *values):
    assert values

    code = data["state"]
    if code in _CONFIRM_PERMANENT:
        return _CONFIRM_PERMANENT[code]

    values_map = {str(value): value for value in values}

    if "n" not in values_map:
        values_map["n"] = "n"

    prompt_str = "{} {} {} ({} [all])? ".format(
        code,
        name,
        ", ".join(data.get("comment", [])),
        "/".join(values_map.keys()),
    )

    input_data = []
    while not input_data or input_data[0] not in values_map:
        input_data = input(prompt_str)
        input_data = input_data.split(" ", 1)

    if len(input_data) > 1 and input_data[1] == "all":
        _CONFIRM_PERMANENT[code] = values_map[input_data[0]]

    return values_map[input_data[0]]


def on_cache_update(_namespace):
    conf.init()
    cache.cache.init()
    bucket = utils.connect_bucket()
    with reprint.output() as output:
        utils.update_cache(bucket, reprint=output)
    logger.info("cached %d remote objects", cache.cache.total())
