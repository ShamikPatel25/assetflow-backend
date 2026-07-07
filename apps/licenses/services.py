from django.db import transaction
from django.utils import timezone

from apps.base.errors import AFValidationError, error_codes
from apps.licenses.models import SoftwareLicense, LicenseAssignment


class LicenseService:
    """Business logic for license assignment and revocation."""

    @staticmethod
    def assign(license_obj, employee, assigned_by=None, created_by=None):
        """
        Assign a license seat to an employee.
        The seat follows the employee's identity — no hardware asset linkage.
        """
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

        if LicenseAssignment.objects.filter(
            license=license_obj,
            employee=employee,
            status=LicenseAssignment.Status.ACTIVE,
            is_deleted=False
        ).exists():
            raise AFValidationError(
                f"{employee.get_full_name()} already has an active assignment for this license.",
                app_code=error_codes.RECORD_ALREADY_EXIST,
            )

        with transaction.atomic():
            assignment = LicenseAssignment.objects.create(
                license=license_obj,
                employee=employee,
                assigned_by=assigned_by,
                status=LicenseAssignment.Status.ACTIVE,
                created_by=created_by,
                updated_by=created_by,
            )

        return assignment

    @staticmethod
    def revoke(assignment, updated_by=None):
        if assignment.status != LicenseAssignment.Status.ACTIVE:
            raise AFValidationError(
                "Only active assignments can be revoked.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        with transaction.atomic():
            assignment.status = LicenseAssignment.Status.REVOKED
            assignment.revoked_at = timezone.now()
            if updated_by:
                assignment.updated_by = updated_by
            assignment.save(update_fields=["status", "revoked_at", "updated_at", "updated_by"])

        return assignment

    @staticmethod
    def bulk_assign(license_obj, assignments_data, assigned_by=None, created_by=None):
        """
        Bulk-assign license seats to multiple employees.
        Each item in assignments_data needs only an 'employee' key.
        """
        if license_obj.status != SoftwareLicense.Status.ACTIVE:
            raise AFValidationError(
                "Cannot assign seats from an inactive license.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        if license_obj.available_seats < len(assignments_data):
            raise AFValidationError(
                f"Not enough available seats. Required: {len(assignments_data)}, Available: {license_obj.available_seats}.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )

        employee_ids = [item["employee"].id for item in assignments_data]

        # Check for existing active assignments for these employees
        existing_assignments = set(LicenseAssignment.objects.filter(
            license=license_obj,
            employee_id__in=employee_ids,
            status=LicenseAssignment.Status.ACTIVE,
            is_deleted=False
        ).values_list("employee_id", flat=True))

        new_assignments = []
        with transaction.atomic():
            for item in assignments_data:
                employee = item["employee"]
                if employee.id in existing_assignments:
                    raise AFValidationError(
                        f"{employee.get_full_name()} already has an active assignment for this license.",
                        app_code=error_codes.RECORD_ALREADY_EXIST,
                    )

                new_assignments.append(LicenseAssignment(
                    license=license_obj,
                    employee=employee,
                    assigned_by=assigned_by,
                    status=LicenseAssignment.Status.ACTIVE,
                    created_by=created_by,
                    updated_by=created_by,
                ))

            if new_assignments:
                created_assignments = LicenseAssignment.objects.bulk_create(new_assignments)
                return created_assignments

            return []
