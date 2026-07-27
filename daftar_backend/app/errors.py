class ApiError(Exception):
    """Base class for domain errors that should surface as a clean JSON error response
    instead of a stack trace. Route handlers raise these; app.errorhandler catches them."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFoundError(ApiError):
    def __init__(self, message: str = "یافت نشد."):
        super().__init__(message, 404)


class ValidationError(ApiError):
    def __init__(self, message: str):
        super().__init__(message, 400)


class AuthError(ApiError):
    def __init__(self, message: str = "ورود نامعتبر است."):
        super().__init__(message, 401)


class ForbiddenError(ApiError):
    def __init__(self, message: str = "شما دسترسی لازم برای این عملیات را ندارید."):
        super().__init__(message, 403)
