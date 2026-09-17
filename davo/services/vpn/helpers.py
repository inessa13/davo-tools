import davo.utils

from . import handlers, utils


def connect(account_name=None):
    contents, _user_path, _project_path = davo.utils.conf.load_davo_config()
    conf = contents.get("vpn", {})
    if not isinstance(conf, dict):
        raise davo.errors.UserError("Invalid vpn: expected a mapping")
    if not conf:
        raise davo.errors.UserError("Missing vpn configuration")
    if not isinstance(conf.get("accounts", {}), dict):
        raise davo.errors.UserError("Invalid vpn.accounts: expected a mapping")

    kp = davo.utils.conf.load_kp(conf["keepass_db_path"])
    conf = davo.utils.conf.fix_config_secrets(kp, conf, mask=False)

    account = utils.get_account(conf, account_name)
    if account.get("handler") == "openvpn":
        handlers.connect_openvpn(account)

    elif account.get("handler") == "openvpn_otp":
        handlers.connect_openvpn_otp(account)

    elif account.get("handler") == "openconnect":
        handlers.connect_openconnect(account)

    elif account.get("handler") == "openconnect_sudo":
        handlers.connect_openconnect_sudo(account)

    elif account.get("handler") == "openconnect_sudo_2fa":
        handlers.connect_openconnect_sudo_2fa(account)

    else:
        raise davo.errors.Error(
            "Unknown handler: {}".format(account.get("handler"))
        )
