"""Stable protocol errors shared by core and adapters."""


class GameError(Exception):
    def __init__(self, code, message, status=400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details

    def as_dict(self):
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}
