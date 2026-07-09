from . import error_codes as codes


class ErrorMessageDict(dict):
    def get(self, key, default=None):
        default = default or "Something went wrong."
        return super().get(key, default)


error_messages = ErrorMessageDict({
    codes.DATA_VALIDATION_FAILED: "Data validation failed.",
    codes.RECORD_ALREADY_EXIST: "Record already exists.",
    codes.RECORD_NOT_FOUND: "Record not found.",
    codes.PERMISSION_DENIED: "You do not have permission to perform this action.",
    codes.INVALID_STATUS_TRANSITION: "Invalid status transition.",
})

def message(code):
    """Helper to return a dict with code and message."""
    return {"code": code, "message": error_messages.get(code)}
