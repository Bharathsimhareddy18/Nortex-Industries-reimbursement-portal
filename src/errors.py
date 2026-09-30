"""One error type for every business-rule failure, so code in src never has to import FastAPI."""


class AppError(Exception):
    """A rule was broken. main.py turns it into an HTTP response with the same status code and message."""

    def __init__(self, status: int, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details or []
