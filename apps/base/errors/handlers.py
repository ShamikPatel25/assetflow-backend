"""
Project-wide DRF exception handler.

Every API error — whether raised as an ``AFValidationError``, a raw DRF
``serializers.ValidationError``, a framework ``NotFound`` / ``PermissionDenied``,
or an authentication failure — is normalized into one consistent body::

    {"message": "<human readable sentence>", "code": <app error code>}

This removes Django/DRF's default, shape-shifting error payloads
(``{"field": ["msg"]}``, ``["msg"]``, ``{"detail": "msg"}``) so that clients
always parse the same structure regardless of which module raised the error.
"""
from rest_framework import status as http_status
from rest_framework.views import exception_handler as drf_exception_handler

from . import error_codes as codes

# HTTP status -> app error code, so the code field is meaningful even for
# errors raised by the framework itself (auth, throttling, 404, ...).
_STATUS_TO_CODE = {
    http_status.HTTP_400_BAD_REQUEST: codes.DATA_VALIDATION_FAILED,
    http_status.HTTP_401_UNAUTHORIZED: codes.PERMISSION_DENIED,
    http_status.HTTP_403_FORBIDDEN: codes.PERMISSION_DENIED,
    http_status.HTTP_404_NOT_FOUND: codes.RECORD_NOT_FOUND,
    http_status.HTTP_409_CONFLICT: codes.RECORD_ALREADY_EXIST,
}


def _flatten_message(data):
    """Reduce any DRF error payload into a single readable sentence."""
    if isinstance(data, dict):
        # Already normalized ({"message": "..."}).
        if "message" in data and not isinstance(data["message"], (list, dict)):
            return str(data["message"])
        # DRF's generic {"detail": "..."}.
        if "detail" in data and not isinstance(data["detail"], (list, dict)):
            return str(data["detail"])
        # Field errors: {"email": ["msg"]} -> "email - msg".
        for field, value in data.items():
            msg = _flatten_message(value)
            if field in ("non_field_errors", "detail"):
                return msg
            return f"{field} - {msg}"
        return error_default_message()
    if isinstance(data, (list, tuple)):
        return _flatten_message(data[0]) if data else error_default_message()
    return str(data)


def error_default_message():
    return "Data validation failed."


def api_exception_handler(exc, context):
    """DRF ``EXCEPTION_HANDLER`` entry point."""
    response = drf_exception_handler(exc, context)
    if response is None:
        # Not a DRF-handled exception; let it bubble to the 500 path
        # (BaseViewSet.unhandled_response handles the viewset case).
        return None

    data = response.data
    existing_code = data.get("code") if isinstance(data, dict) else None

    message = _flatten_message(data)
    code = (
        existing_code
        if existing_code is not None
        else _STATUS_TO_CODE.get(response.status_code, codes.NO_CODE)
    )

    response.data = {"message": message, "code": code}
    return response
