class BaseError(RuntimeError):
    pass


class UserError(BaseError):
    pass


class NotImpl(BaseError, NotImplemented):
    pass
