import os

import pexpect
import pyotp

import davo.utils

from . import utils

C_OPENCONNECT = (
    '{{ echo \'{}\' ; echo \'{}\' ; }} | sudo openconnect --user={}'
    ' --authgroup={} {} --passwd-on-stdin --no-dtls'
    ' --script=/home/davo/Dropbox/etc/vpnc-script'
)
C_OPENCONNECT_SUDO = (
    'sudo openconnect --user={}'
    ' --authgroup={} {} --passwd-on-stdin --no-dtls'
    ' --script=/home/davo/Dropbox/etc/vpnc-script'
)
C_OPENVPN = (
    'sudo openvpn --config {} --auth-user-pass {} --auth-retry interact'
    ' --verb 0 --auth-nocache'
)


def connect_openconnect(account):
    otp = pyotp.TOTP(account['otp_secret']).now()
    print('Connecting to `{}`'.format(account['auth_group']))
    cmd = C_OPENCONNECT.format(
        account['password'], otp, account['user'], account['auth_group'],
        account['url'])
    print(cmd.replace(account['password'], '***'))
    os.system(cmd)


def connect_openconnect_sudo(account):
    print('Connecting to `{}`'.format(account['auth_group']))
    cmd = C_OPENCONNECT_SUDO.format(
        account['user'], account['auth_group'], account['url'])
    print(cmd)

    otp = pyotp.TOTP(account['otp_secret']).now()
    sudo = davo.utils.conf.load_kr_kp_pass()

    ch = pexpect.spawn(cmd)
    ch.expect('\[sudo\] ', timeout=1)
    ch.sendline(sudo)
    ch.sendline(account['password'])
    ch.sendline(otp)
    ch.interact()


def connect_openvpn_otp(account):
    otp = pyotp.TOTP(account['otp_secret']).now()

    pass_file = utils.create_temp_file('{}\n{}'.format(
        account['user'], account['password']))
    cmd = C_OPENVPN.format(account['openvpn_conf_path'], pass_file)
    print(cmd.replace(account['password'], '***'))

    sudo = davo.utils.conf.load_kr_kp_pass()

    try:
        ch = pexpect.spawn(cmd)
        ch.expect('\[sudo\] password for', timeout=1)
        ch.sendline(sudo)
        ch.expect('Enter Google Authenticator Code ', timeout=10)
    finally:
        utils.remove_temp_file()

    ch.sendline(otp)
    ch.interact()


def connect_openvpn(account):
    pass_file = utils.create_temp_file('{}\n{}'.format(
        account['user'], account['password']))
    cmd = C_OPENVPN.format(account['openvpn_conf_path'], pass_file)

    sudo = davo.utils.conf.load_kr_kp_pass()

    try:
        ch = pexpect.spawn(cmd)
        ch.expect('\[sudo\] password for', timeout=1)
        ch.sendline(sudo)
    finally:
        utils.remove_temp_file()
    ch.interact()
