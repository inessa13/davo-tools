class BaseError(RuntimeError):
    pass


class UserError(BaseError):
    pass


class Error(BaseError):
    pass


class NotImpl(BaseError):
    pass
