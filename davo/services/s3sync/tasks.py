import datetime
import os
import time

import boto.s3.key

import davo.utils

from . import cache, conf, utils


class _Task:
    done = 'finished'

    def __init__(self):
        self.bucket = None
        self.name = None
        self.data = None
        self.worker = None
        self.show_estimate = False
        self._t = None

    def handler(self):
        raise NotImplementedError()

    def init(self, bucket, name, data):
        self.bucket = bucket
        self.name = name
        self.data = data
        return self

    def exec(self, worker=None):
        self.worker = worker
        self._t = time.time()
        self.handler()

        size = self.size()
        if size:
            self.worker.speed_list.append(size / (time.time() - self._t))

        self.output_finish()
        self.worker.cb_queue.put((self.name, 100, size))

    def size(self):  # pylint: disable=no-self-use
        return 0

    def progress(self, uploaded, full):
        len_full = 40
        progress = round(float(uploaded) / full, 2) * 100
        progress_len = int(progress) * len_full // 100

        size = self.size()
        if size:
            uploaded = size * float(uploaded) / full
            speed_value = self.worker.speed(uploaded / (time.time() - self._t))
            speed_human = davo.utils.format.humanize_speed(speed_value)
        else:
            speed_value = 0
            speed_human = 'n\\a'

        if self.show_estimate and speed_value and size:
            estimate_value = size * (100 - progress) / speed_value
            estimate = str(datetime.timedelta(seconds=estimate_value))
        else:
            estimate = ''

        self.worker.cb_queue.put((self.name, progress, uploaded))

        line = conf.get('UPLOAD_FORMAT').format(
            progress='=' * progress_len,
            left=' ' * (len_full - progress_len),
            progress_percent=progress,
            speed=speed_human,
            estimate=estimate,
            elapsed='',
            info='{} {}'.format(self, self.name)
        )
        self.output_edit(line)

    def output_edit(self, line):
        if self.worker:
            self.worker.output[self.worker.index] = line
        else:
            print(line)

    def output_finish(self):
        line = '{} {}'.format(self.done, self.name)
        if not self.worker:
            print(line)
            return

        utils.output_finish(self.worker.output, line)


def _upload(key, callback, local_path, cb_num, replace=False):
    local_file_path = utils.file_path(local_path)

    with open(local_file_path, 'rb') as local_file:
        key.set_contents_from_file(
            local_file,
            replace=replace,
            cb=callback,
            num_cb=cb_num,
            rewind=True,
        )

    cache.cache.update(key.name, {
        'name': key.name,
        'size': key.size,
        'last_modified': datetime.datetime.utcnow().strftime(
            '%Y-%m-%dT%H:%M:%S.000Z'),
        'etag': key.etag,
    })
    cache.cache.flush()


class Upload(_Task):
    done = 'uploaded'

    def __str__(self):
        return 'upload'

    def size(self):
        return self.data.get('local_size') or 0

    def handler(self):
        _upload(
            boto.s3.key.Key(bucket=self.bucket, name=self.name),
            self.progress,
            self.data['local_path'],
            conf.get('UPLOAD_CB_NUM'),
        )
        self.data['comment'] = ['uploaded']


class ReplaceUpload(_Task):
    done = 'uploaded (replace)'

    def __str__(self):
        return 'upload_replace'

    def size(self):
        return self.data.get('local_size') or 0

    def handler(self):
        _upload(
            self.data['key'],
            self.progress,
            self.data['local_path'],
            conf.get('UPLOAD_CB_NUM'),
            replace=True,
        )
        self.data['comment'] = ['uploaded(replaced)']


class DeleteRemote(_Task):
    done = 'deleted (remote)'

    def __str__(self):
        return 'delete_remote'

    def handler(self):
        self.data['key'].delete()
        self.data['comment'] = ['deleted from s3']


class RenameRemote(_Task):
    done = 'renamed (remote)'

    def __str__(self):
        return 'rename_remote'

    def handler(self):
        new_key = self.data['key'].copy(
            conf.get('BUCKET'), self.data['local_name'],
            metadata=None,
            preserve_acl=True,
            encrypt_key=False,
            validate_dst_bucket=True,
        )

        if new_key:
            self.data['key'].delete()
            self.data['comment'] = ['renamed']
        else:
            raise Exception('s3 key copy failed')


class RenameLocal(_Task):
    done = 'renamed (local)'

    def __str__(self):
        return 'rename_local'

    def handler(self):
        dest_name = os.path.join(
            conf.get('PROJECT_ROOT'), self.data['key'].name)

        davo.utils.path.ensure(dest_name, commit=True)

        os.rename(
            os.path.join(conf.get('PROJECT_ROOT'), self.data['local_name']),
            dest_name,
        )
        self.data['comment'] = ['renamed']


class Download(_Task):
    done = 'downloaded'

    def __str__(self):
        return 'download'

    def size(self):
        return self.data.get('size') or 0

    def handler(self):
        file_path = self.data['local_path']
        davo.utils.path.ensure(file_path, commit=True)
        self.data['key'].get_contents_to_filename(
            file_path,
            cb=self.progress,
            num_cb=20,
        )


class DeleteLocal(_Task):
    done = 'deleted (local)'

    def __str__(self):
        return 'delete_local'

    def handler(self):
        self.progress(0, 1)
        os.remove(self.data['local_path'])
        self.progress(1, 1)
