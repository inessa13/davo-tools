# PYTHON_ARGCOMPLETE_OK
import argparse
import argcomplete
import os
import yaml
import logging


logger = logging.getLogger(__name__)

CLR_HEADER = '\033[95m'
CLR_OKBLUE = '\033[94m'
CLR_OKGREEN = '\033[92m'
CLR_WARNING = '\033[93m'
CLR_FAIL = '\033[91m'
CLR_ENDC = '\033[0m'
CLR_BOLD = '\033[1m'
CLR_UNDERLINE = '\033[4m'


class CitError(Exception):
    pass


def init(conf, cwd, exclude):
    config_path = os.path.join(cwd, 'cit.yml')
    if os.path.exists(config_path):
        raise CitError('Config already exists')

    conf['root'] = cwd
    for project in conf['projects']:
        print('[{}{}{}]'.format(CLR_WARNING, project['name'], CLR_ENDC))
        if exclude:
            project['default'] = project['path'] not in exclude
        else:
            project['default'] = True
        print('default: {}'.format(project['default']))

    with open(config_path, 'w') as f:
        yaml.dump(conf, f)
    logger.warning('Config `cit.yml` created')


def main_(args, argv):
    logger.addHandler(logging.StreamHandler())
    if args.verbose:
        logger.setLevel(logging.INFO)

    if os.path.exists('cit.yml'):
        with open('cit.yml') as f:
            conf = yaml.safe_load(f)
        logger.info('Config `cit.yml` loaded')
    else:
        conf = {}

    if args.work_dir:
        if os.path.exists(args.work_dir):
            cwd = args.work_dir
        else:
            raise CitError('Invalid path')
    elif conf.get('root'):
        if os.path.exists(conf['root']):
            cwd = conf['root']
        else:
            raise CitError('Invalid path')
    else:
        cwd = os.getcwd()

    logger.info('CWD: {}'.format(cwd))

    if sum(map(bool, (args.search, args.tag, args.all))) > 1:
        raise CitError('Cannot use --all/--search/--tag together')

    args.init = 'init' in argv
    if args.search or args.init:
        logger.info('Searching for projects')
        conf['projects'] = []
        for f in os.listdir(cwd):
            if (os.path.isdir(os.path.join(cwd, f))
                    and os.path.exists(os.path.join(cwd, f, '.git'))):
                conf['projects'].append({
                    'name': f,
                    'path': f,
                })

    if args.init:
        return init(conf, cwd, args.exclude_dir)

    if not conf.get('projects'):
        raise CitError('There is no projects.')

    if argv:
        cmd = ' '.join(argv)
    else:
        cmd = 'st'

    print('>{}git {}{}'.format(CLR_OKBLUE, cmd, CLR_ENDC))
    last_result = 0
    for project in conf['projects']:
        if args.tag:
            if not set(project['tags']) & set(args.tag):
                continue
        elif not project.get('default') and not args.all:
            continue
        print('[{}{}{}]'.format(CLR_WARNING, project['name'], CLR_ENDC))
        result = os.system('git -C {} {}'.format(
            os.path.join(cwd, project['path']),
            cmd
        ))
        if result and result == last_result:
            logger.error(
                '{}Repeating errors, breaking{}'.format(CLR_FAIL, CLR_ENDC))
            # break
        last_result = result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-V', '--verbose', action='store_true')
    parser.add_argument(
        '-S', '--search', action='store_true', help='auto discover projects')
    parser.add_argument(
        '-A', '--all', action='store_true', help='use all projects')
    parser.add_argument(
        '-T', '--tag', action='append', help='use projects with tag')
    parser.add_argument('-C', '--work-dir', action='store')
    parser.add_argument('-X', '--exclude-dir', action='append')

    argcomplete.autocomplete(parser)

    args, argv = parser.parse_known_args()

    try:
        main_(args, argv)
    except CitError as e:
        logger.error(CLR_FAIL + e.args[0] + CLR_ENDC)


if __name__ == '__main__':
    main()
