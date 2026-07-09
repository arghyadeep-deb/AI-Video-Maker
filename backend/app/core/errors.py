"""Domain error types mapped to the `{error: {code, message, hint?}}` envelope
(specs/03-design/09-api-endpoints.md) by handlers registered in app.main.
"""


class AppError(Exception):
    code = "error"

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class NotFoundError(AppError):
    code = "not_found"

    def __init__(self, message: str = "Not found"):
        super().__init__(message)


class ForbiddenError(AppError):
    code = "forbidden"

    def __init__(self, message: str = "Forbidden"):
        super().__init__(message)


class UnauthorizedError(AppError):
    code = "unauthorized"

    def __init__(self, message: str = "Not authenticated"):
        super().__init__(message)
