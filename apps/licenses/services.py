from django.db import transaction
from django.utils import timezone

from apps.base.errors import AFValidationError, error_codes
from apps.licenses.models import SoftwareLicense, LicenseAssignment
from apps.audit.services import log_action


class LicenseService:
    """Business logic for license assignment and revocation."""

    @staticmethod
    def _validate_license_assignable(license_obj):
        """
        Validate that a license is in a state that allows new assignments.
        Called inside a select_for_update block so reads are fresh.
        """
        if license_obj.status != SoftwareLicense.Status.ACTIVE:
            raise AFValidationError(
                "Cannot assign seats from an inactive license.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        # Check expiry (only relevant if expiry_date is set)
        if license_obj.expiry_date:
            from django.utils import timezone as tz
            today = tz.now().date()
            if license_obj.expiry_date < today:
                raise AFValidationError(
                    "Cannot assign seats from an expired license.",
                    app_code=error_codes.INVALID_STATUS_TRANSITION,
                )

    @staticmethod
    def assign(license_obj, employee, assigned_by=None, created_by=None):
        """
        Assign a license seat to an employee.

        Uses select_for_update on the parent SoftwareLicense row to prevent
        concurrent overbooking when two requests race for the last seat.
        """
        if not employee.is_active:
            raise AFValidationError(
                "Cannot assign a license to an inactive or exited employee.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )

        with transaction.atomic():
            # Lock the license row so concurrent requests queue up here
            locked_license = SoftwareLicense.objects.select_for_update().get(
                pk=license_obj.pk
            )

            # Re-validate status and expiry AFTER acquiring the lock
            LicenseService._validate_license_assignable(locked_license)

            # Check duplicate assignment INSIDE the lock
            if LicenseAssignment.objects.filter(
                license=locked_license,
                employee=employee,
                status=LicenseAssignment.Status.ACTIVE,
                is_deleted=False,
            ).exists():
                raise AFValidationError(
                    f"{employee.get_full_name()} already has an active assignment for this license.",
                    app_code=error_codes.RECORD_ALREADY_EXIST,
                )

            # Recompute available seats AFTER lock (not from the caller's stale view)
            used_seats = LicenseAssignment.objects.filter(
                license=locked_license,
                status=LicenseAssignment.Status.ACTIVE,
                is_deleted=False,
            ).count()
            available = locked_license.total_seats - used_seats

            if available <= 0:
                raise AFValidationError(
                    "No available seats for this license.",
                    app_code=error_codes.DATA_VALIDATION_FAILED,
                )

            assignment = LicenseAssignment.objects.create(
                license=locked_license,
                employee=employee,
                assigned_by=assigned_by,
                status=LicenseAssignment.Status.ACTIVE,
                created_by=created_by,
                updated_by=created_by,
            )

        log_action(
            user=created_by,
            action="ASSIGN",
            module="LICENSE",
            object_type="LicenseAssignment",
            object_id=assignment.id,
            object_repr=str(assignment),
            new_data={
                "license": str(assignment.license_id),
                "employee": str(assignment.employee_id),
                "status": assignment.status,
            },
        )

        return assignment

    @staticmethod
    def revoke(assignment, updated_by=None):
        with transaction.atomic():
            locked_assignment = LicenseAssignment.objects.select_for_update().get(
                pk=assignment.pk
            )

            if locked_assignment.status != LicenseAssignment.Status.ACTIVE:
                raise AFValidationError(
                    "Only active assignments can be revoked.",
                    app_code=error_codes.INVALID_STATUS_TRANSITION,
                )

            locked_assignment.status = LicenseAssignment.Status.REVOKED
            locked_assignment.revoked_at = timezone.now()
            if updated_by:
                locked_assignment.updated_by = updated_by
            locked_assignment.save(update_fields=["status", "revoked_at", "updated_at", "updated_by"])

        log_action(
            user=updated_by,
            action="REVOKE",
            module="LICENSE",
            object_type="LicenseAssignment",
            object_id=locked_assignment.id,
            object_repr=str(locked_assignment),
            new_data={
                "license": str(locked_assignment.license_id),
                "employee": str(locked_assignment.employee_id),
                "status": locked_assignment.status,
            },
        )

        return locked_assignment

    @staticmethod
    def bulk_assign(license_obj, assignments_data, assigned_by=None, created_by=None):
        """
        Bulk-assign license seats to multiple employees.
        Each item in assignments_data needs only an 'employee' key.

        Uses select_for_update on the parent license to prevent concurrent
        overbooking across bulk assignments.
        """
        if not assignments_data:
            return []

        with transaction.atomic():
            # Lock the license row for the entire bulk operation
            locked_license = SoftwareLicense.objects.select_for_update().get(
                pk=license_obj.pk
            )

            # Re-validate status and expiry AFTER lock
            LicenseService._validate_license_assignable(locked_license)

            # Recompute available seats inside the lock
            used_seats = LicenseAssignment.objects.filter(
                license=locked_license,
                status=LicenseAssignment.Status.ACTIVE,
                is_deleted=False,
            ).count()
            available = locked_license.total_seats - used_seats

            if available < len(assignments_data):
                raise AFValidationError(
                    f"Not enough available seats. Required: {len(assignments_data)}, Available: {available}.",
                    app_code=error_codes.DATA_VALIDATION_FAILED,
                )

            employee_ids = [item["employee"].id for item in assignments_data]

            # Validate no inactive employees
            for item in assignments_data:
                if not item["employee"].is_active:
                    raise AFValidationError(
                        f"Cannot assign license to inactive employee {item['employee'].get_full_name()}.",
                        app_code=error_codes.DATA_VALIDATION_FAILED,
                    )

            # Check for existing active assignments for these employees
            existing_assignments = set(
                LicenseAssignment.objects.filter(
                    license=locked_license,
                    employee_id__in=employee_ids,
                    status=LicenseAssignment.Status.ACTIVE,
                    is_deleted=False,
                ).values_list("employee_id", flat=True)
            )

            new_assignments = []
            for item in assignments_data:
                employee = item["employee"]
                if employee.id in existing_assignments:
                    raise AFValidationError(
                        f"{employee.get_full_name()} already has an active assignment for this license.",
                        app_code=error_codes.RECORD_ALREADY_EXIST,
                    )

                new_assignments.append(LicenseAssignment(
                    license=locked_license,
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
