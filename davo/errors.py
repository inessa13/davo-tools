__all__ = (
    'BaseError',
    'UserError',
    'Error',
    'NotImpl',
)


class BaseError(RuntimeError):
    pass


class UserError(BaseError):
    pass


class Error(BaseError):
    pass


class NotImpl(BaseError):
    pass
