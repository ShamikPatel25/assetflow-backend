import uuid
from django.db import transaction
from django.utils import timezone

from apps.allocations.models import AssetAllocation
from apps.assets.models import Asset
from apps.base.errors import AFValidationError, error_codes
from apps.notifications.services import NotificationService


class AllocationService:
    """Business logic for asset allocation, return, and transfer."""

    @staticmethod
    def allocate(asset, employee, assigned_by=None, expected_return_date=None, remarks=None):
        """Allocate an available asset to an employee."""
        if asset.status != Asset.Status.AVAILABLE:
            raise AFValidationError(
                "Asset is not available for allocation.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        if not employee.is_active:
            raise AFValidationError(
                "Cannot allocate to an inactive or exited employee.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )

        with transaction.atomic():
            allocation = AssetAllocation.objects.create(
                allocation_number=f"ALLOC-{uuid.uuid4().hex[:8].upper()}",
                asset=asset,
                employee=employee,
                assigned_by=assigned_by,
                allocated_at=timezone.now(),
                expected_return_date=expected_return_date,
                remarks=remarks,
                status=AssetAllocation.Status.ACTIVE,
            )

            asset.status = Asset.Status.ALLOCATED
            asset.current_owner = employee
            asset.current_allocation = allocation
            asset.save(update_fields=[
                "status", "current_owner", "current_allocation", "updated_at",
            ])

        NotificationService.notify_asset_allocated(allocation)

        return allocation

    @staticmethod
    def return_asset(allocation, return_condition=None, remarks=None):
        """Return an allocated asset."""
        if allocation.status != AssetAllocation.Status.ACTIVE:
            raise AFValidationError(
                "Only active allocations can be returned.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        with transaction.atomic():
            allocation.status = AssetAllocation.Status.RETURNED
            allocation.returned_at = timezone.now()
            allocation.return_condition = return_condition
            if remarks:
                allocation.remarks = remarks
            allocation.save(update_fields=[
                "status", "returned_at", "return_condition", "remarks", "updated_at",
            ])

            asset = allocation.asset
            asset.status = Asset.Status.AVAILABLE
            asset.current_owner = None
            asset.current_allocation = None
            asset.save(update_fields=[
                "status", "current_owner", "current_allocation", "updated_at",
            ])

        NotificationService.notify_asset_returned(allocation)

        return allocation

    @staticmethod
    def cancel_allocation(allocation, remarks):
        """Cancel an active allocation (admin / HR use-case, e.g. wrong assignment)."""
        if allocation.status != AssetAllocation.Status.ACTIVE:
            raise AFValidationError(
                "Only active allocations can be cancelled.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        with transaction.atomic():
            allocation.status = AssetAllocation.Status.CANCELLED
            allocation.remarks = remarks
            allocation.save(update_fields=["status", "remarks", "updated_at"])

            asset = allocation.asset
            asset.status = Asset.Status.AVAILABLE
            asset.current_owner = None
            asset.current_allocation = None
            asset.save(update_fields=[
                "status", "current_owner", "current_allocation", "updated_at",
            ])

        return allocation

    @classmethod
    def transfer_asset(cls, allocation, new_employee, assigned_by=None, return_condition=None, expected_return_date=None, remarks=None):
        """Transfer an active allocation directly to a new employee."""
        if allocation.status != AssetAllocation.Status.ACTIVE:
            raise AFValidationError(
                "Only active allocations can be transferred.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )
            
        if not new_employee.is_active:
            raise AFValidationError(
                "Cannot transfer to an inactive or exited employee.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )
            
        if allocation.employee == new_employee:
            raise AFValidationError(
                "Cannot transfer asset to the same employee.",
                app_code=error_codes.DATA_VALIDATION_FAILED,
            )

        with transaction.atomic():
            # 1. Return the current allocation
            allocation.status = AssetAllocation.Status.RETURNED
            allocation.returned_at = timezone.now()
            if return_condition:
                allocation.return_condition = return_condition
            if remarks:
                allocation.remarks = f"Transferred to {new_employee.get_full_name()} - {remarks}"
            else:
                allocation.remarks = f"Transferred to {new_employee.get_full_name()}"
            allocation.save(update_fields=[
                "status", "returned_at", "return_condition", "remarks", "updated_at",
            ])

            asset = allocation.asset

            # 2. Allocate to new employee
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

        # Notifications
        NotificationService.notify_asset_returned(allocation)
        NotificationService.notify_asset_allocated(new_allocation)

        return new_allocation
