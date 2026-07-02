import logging

from rest_framework import status
from rest_framework.exceptions import APIException

from .error_codes import NO_CODE, DATA_VALIDATION_FAILED
from .messages import error_messages

logger = logging.getLogger(__name__)


class AFValidationError(APIException):
    """Raised when business-level validation fails."""

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail=None, code=None, app_code=None):
        super().__init__(detail, code)
        self.app_code = app_code or NO_CODE

        if app_code and app_code != DATA_VALIDATION_FAILED:
            resolved = error_messages.get(app_code)
        else:
            resolved = detail or "Data validation failed."

        if not app_code:
            logger.error("Validation Error: %s", detail)

        self.detail = {"message": resolved}
        if self.app_code != NO_CODE:
            self.detail["code"] = self.app_code
