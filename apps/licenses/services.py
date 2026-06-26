from django.db import transaction
from django.utils import timezone

from apps.base.errors import AFValidationError, error_codes
from apps.licenses.models import SoftwareLicense, LicenseAssignment


class LicenseService:
    """Business logic for license assignment and revocation."""

    @staticmethod
    def assign(license_obj, employee, asset=None, assigned_by=None):
        if license_obj.status != SoftwareLicense.Status.ACTIVE:
            raise AFValidationError(
                "Cannot assign seats from an inactive license.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        if license_obj.available_seats <= 0:
            raise AFValidationError(
                "No available seats for this license.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )

        with transaction.atomic():
            assignment = LicenseAssignment.objects.create(
                license=license_obj,
                employee=employee,
                asset=asset,
                assigned_by=assigned_by,
                status=LicenseAssignment.Status.ACTIVE,
            )

        return assignment

    @staticmethod
    def revoke(assignment):
        if assignment.status != LicenseAssignment.Status.ACTIVE:
            raise AFValidationError(
                "Only active assignments can be revoked.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        with transaction.atomic():
            assignment.status = LicenseAssignment.Status.REVOKED
            assignment.revoked_at = timezone.now()
            assignment.save(update_fields=["status", "revoked_at", "updated_at"])

        return assignment
