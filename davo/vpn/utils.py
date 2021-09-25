import glob
import os
import random

import davo.common


def get_account(conf, account_name=None):
    if not account_name:
        account_name = conf.get('default_account', 'default')

    if account_name not in conf.get('accounts', {}):
        raise davo.common.errors.Error(
            'Unknown account: `{}`'.format(account_name))

    return conf['accounts'][account_name]


def create_temp_file(content, prefix='pf'):
    path = '/tmp/{}{}'.format(prefix, int(random.random() * 10 ** 6))
    os.system('echo "%s" > %s' % (content, path))
    return path


def remove_temp_file():
    for f in glob.glob('/tmp/tmp_pf*'):
        os.remove(f)
