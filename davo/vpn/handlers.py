import os

import pexpect

from . import utils

C_OPENCONNECT = (
    '{ echo \'%s\' ; echo \'%s\' ; } | sudo openconnect --user=%s'
    ' --authgroup=%s %s --passwd-on-stdin'
)
C_OPENVPN = (
    'openvpn --config {} --auth-user-pass {} --auth-retry interact --verb 0'
    ' --auth-nocache'
)


def connect_openconnect(account):
    user, pwd, otp = utils.load_account_secrets(account)
    print('Connecting to `%s`'.format(account['auth_group']))
    os.system(C_OPENCONNECT % (
        pwd, otp, user, account['auth_group'], account['url']))


def connect_openvpn(account):
    user, pwd, otp = utils.load_account_secrets(account)

    pass_file = utils.create_temp_file('%s\n%s' % (user, pwd))
    try:
        ch = pexpect.spawn(
            C_OPENVPN.format(account['openvpn_conf_path'], pass_file))
        ch.expect('Enter Google Authenticator Code ')
    finally:
        utils.remove_temp_file()

    ch.sendline(otp)
    ch.interact()
