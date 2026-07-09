import uuid
from django.db import transaction
from django.utils import timezone

from apps.allocations.models import AssetAllocation
from apps.assets.models import Asset
from apps.base.errors import AFValidationError, error_codes
from apps.notifications.services import NotificationService
from apps.audit.services import log_action


class AllocationService:
    """Business logic for asset allocation, return, and transfer."""

    @staticmethod
    def _validate_asset_for_allocation(asset):
        """
        Shared validation: raise AFValidationError if the asset cannot be
        allocated/transferred right now.

        Called INSIDE a transaction AFTER acquiring a select_for_update lock
        on the asset row, so the status read is fresh and consistent.
        """
        invalid_statuses = {
            Asset.Status.ALLOCATED: "Asset is already allocated to someone.",
            Asset.Status.IN_MAINTENANCE: "Asset is currently in maintenance and cannot be allocated.",
            Asset.Status.LOST: "Asset is marked as lost and cannot be allocated.",
            Asset.Status.RETIRED: "Asset has been retired and cannot be allocated.",
            Asset.Status.DAMAGED: "Asset is damaged and cannot be allocated.",
        }
        msg = invalid_statuses.get(asset.status)
        if msg:
            raise AFValidationError(msg, app_code=error_codes.INVALID_STATUS_TRANSITION)

        if asset.condition == Asset.Condition.DAMAGED:
            raise AFValidationError(
                "Asset condition is DAMAGED and cannot be allocated.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )

    @staticmethod
    def _check_no_open_incidents(asset):
        """
        Block transfer/allocation if the asset has OPEN or IN_PROGRESS incidents.
        """
        from apps.incidents.models import Incident
        has_open = asset.incidents.filter(
            status__in=[Incident.Status.OPEN, Incident.Status.IN_PROGRESS],
            is_deleted=False,
        ).exists()
        if has_open:
            raise AFValidationError(
                "Asset has open or in-progress incidents. Resolve them before proceeding.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )

    @staticmethod
    def allocate(asset, employee, assigned_by=None, expected_return_date=None, remarks=None):
        """Allocate an available asset to an employee."""
        if not employee.is_active:
            raise AFValidationError(
                "Cannot allocate to an inactive or exited employee.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )

        with transaction.atomic():
            # Acquire a row-level lock to prevent concurrent allocation races
            locked_asset = Asset.objects.select_for_update().get(pk=asset.pk)

            # Re-validate AFTER acquiring the lock (state may have changed)
            AllocationService._validate_asset_for_allocation(locked_asset)

            allocation = AssetAllocation.objects.create(
                allocation_number=f"ALLOC-{uuid.uuid4().hex[:8].upper()}",
                asset=locked_asset,
                employee=employee,
                assigned_by=assigned_by,
                allocated_at=timezone.now(),
                expected_return_date=expected_return_date,
                remarks=remarks,
                status=AssetAllocation.Status.ACTIVE,
            )

            locked_asset.status = Asset.Status.ALLOCATED
            locked_asset.current_owner = employee
            locked_asset.current_allocation = allocation
            locked_asset.save(update_fields=[
                "status", "current_owner", "current_allocation", "updated_at",
            ])

        NotificationService.notify_asset_allocated(allocation)

        log_action(
            user=getattr(assigned_by, "user", None) if assigned_by else None,
            action="ALLOCATE",
            module="ALLOCATION",
            object_type="AssetAllocation",
            object_id=allocation.id,
            object_repr=str(allocation),
            new_data={
                "asset": str(allocation.asset_id),
                "employee": str(allocation.employee_id),
                "status": allocation.status,
            },
        )

        return allocation

    @staticmethod
    def return_asset(allocation, return_condition=None, remarks=None):
        """Return an allocated asset."""
        with transaction.atomic():
            # Lock the allocation row first to prevent concurrent returns
            locked_allocation = AssetAllocation.objects.select_for_update().get(
                pk=allocation.pk
            )

            if locked_allocation.status != AssetAllocation.Status.ACTIVE:
                raise AFValidationError(
                    "Only active allocations can be returned.",
                    app_code=error_codes.INVALID_STATUS_TRANSITION,
                )

            locked_allocation.status = AssetAllocation.Status.RETURNED
            locked_allocation.returned_at = timezone.now()
            locked_allocation.return_condition = return_condition
            if remarks:
                locked_allocation.remarks = remarks
            locked_allocation.save(update_fields=[
                "status", "returned_at", "return_condition", "remarks", "updated_at",
            ])

            # Lock asset row before updating denormalized fields
            asset = Asset.objects.select_for_update().get(pk=locked_allocation.asset_id)
            asset.status = Asset.Status.AVAILABLE
            asset.current_owner = None
            asset.current_allocation = None
            asset.save(update_fields=[
                "status", "current_owner", "current_allocation", "updated_at",
            ])

        NotificationService.notify_asset_returned(locked_allocation)

        log_action(
            action="RETURN",
            module="ALLOCATION",
            object_type="AssetAllocation",
            object_id=locked_allocation.id,
            object_repr=str(locked_allocation),
            new_data={
                "asset": str(locked_allocation.asset_id),
                "employee": str(locked_allocation.employee_id),
                "return_condition": locked_allocation.return_condition,
                "status": locked_allocation.status,
            },
        )

        return locked_allocation

    @staticmethod
    def cancel_allocation(allocation, remarks):
        """Cancel an active allocation (admin / HR use-case, e.g. wrong assignment)."""
        with transaction.atomic():
            locked_allocation = AssetAllocation.objects.select_for_update().get(
                pk=allocation.pk
            )

            if locked_allocation.status != AssetAllocation.Status.ACTIVE:
                raise AFValidationError(
                    "Only active allocations can be cancelled.",
                    app_code=error_codes.INVALID_STATUS_TRANSITION,
                )

            locked_allocation.status = AssetAllocation.Status.CANCELLED
            locked_allocation.remarks = remarks
            locked_allocation.save(update_fields=["status", "remarks", "updated_at"])

            asset = Asset.objects.select_for_update().get(pk=locked_allocation.asset_id)
            asset.status = Asset.Status.AVAILABLE
            asset.current_owner = None
            asset.current_allocation = None
            asset.save(update_fields=[
                "status", "current_owner", "current_allocation", "updated_at",
            ])

        log_action(
            action="CANCEL",
            module="ALLOCATION",
            object_type="AssetAllocation",
            object_id=locked_allocation.id,
            object_repr=str(locked_allocation),
            new_data={
                "asset": str(locked_allocation.asset_id),
                "employee": str(locked_allocation.employee_id),
                "remarks": remarks,
                "status": locked_allocation.status,
            },
        )

        return locked_allocation

    @classmethod
    def transfer_asset(
        cls,
        allocation,
        new_employee,
        assigned_by=None,
        return_condition=None,
        expected_return_date=None,
        remarks=None,
    ):
        """Transfer an active allocation directly to a new employee."""
        if not new_employee.is_active:
            raise AFValidationError(
                "Cannot transfer to an inactive or exited employee.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )

        with transaction.atomic():
            locked_allocation = AssetAllocation.objects.select_for_update().get(
                pk=allocation.pk
            )

            if locked_allocation.status != AssetAllocation.Status.ACTIVE:
                raise AFValidationError(
                    "Only active allocations can be transferred.",
                    app_code=error_codes.INVALID_STATUS_TRANSITION,
                )

            if locked_allocation.employee == new_employee:
                raise AFValidationError(
                    "Cannot transfer asset to the same employee.",
                    app_code=error_codes.DATA_VALIDATION_FAILED,
                )

            # Lock the asset row too
            asset = Asset.objects.select_for_update().get(pk=locked_allocation.asset_id)

            # Block transfer if there are open/in-progress incidents
            cls._check_no_open_incidents(asset)

            # 1. Close the current allocation
            locked_allocation.status = AssetAllocation.Status.RETURNED
            locked_allocation.returned_at = timezone.now()
            if return_condition:
                locked_allocation.return_condition = return_condition
            if remarks:
                locked_allocation.remarks = f"Transferred to {new_employee.get_full_name()} - {remarks}"
            else:
                locked_allocation.remarks = f"Transferred to {new_employee.get_full_name()}"
            locked_allocation.save(update_fields=[
                "status", "returned_at", "return_condition", "remarks", "updated_at",
            ])

            # 2. Create new allocation
            new_allocation = AssetAllocation.objects.create(
                allocation_number=f"ALLOC-{uuid.uuid4().hex[:8].upper()}",
                asset=asset,
                employee=new_employee,
                assigned_by=assigned_by,
                allocated_at=timezone.now(),
                expected_return_date=expected_return_date,
                remarks=remarks,
                status=AssetAllocation.Status.ACTIVE,
            )

            asset.status = Asset.Status.ALLOCATED
            asset.current_owner = new_employee
            asset.current_allocation = new_allocation
            asset.save(update_fields=[
                "status", "current_owner", "current_allocation", "updated_at",
            ])

        # Notifications after successful transaction
        NotificationService.notify_asset_returned(locked_allocation)
        NotificationService.notify_asset_allocated(new_allocation)

        log_action(
            user=getattr(assigned_by, "user", None) if assigned_by else None,
            action="TRANSFER",
            module="ALLOCATION",
            object_type="AssetAllocation",
            object_id=new_allocation.id,
            object_repr=str(new_allocation),
            new_data={
                "asset": str(new_allocation.asset_id),
                "from_employee": str(locked_allocation.employee_id),
                "to_employee": str(new_allocation.employee_id),
                "status": new_allocation.status,
            },
        )

        return new_allocation
