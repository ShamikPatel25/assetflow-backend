import uuid
from django.db import transaction
from django.utils import timezone

from apps.requests.models import AssetRequest
from apps.base.errors import AFValidationError
from apps.allocations.services import AllocationService
from apps.assets.models import Asset
from apps.notifications.services import NotificationService


class AssetRequestService:
    """Business logic for asset request workflow."""

    @staticmethod
    def create_request(employee, category=None, preferred_asset=None,
                       reason="", priority="MEDIUM", created_by=None):
        request_obj = AssetRequest.objects.create(
            request_number=f"REQ-{uuid.uuid4().hex[:8].upper()}",
            requested_by=employee,
            category=category,
            preferred_asset=preferred_asset,
            reason=reason,
            priority=priority,
            status=AssetRequest.Status.PENDING,
            created_by=created_by,
        )

        NotificationService.notify_request_submitted(request_obj)

        return request_obj

    @staticmethod
    def approve(request_obj, approved_by, asset_id=None, notes="", updated_by=None):
        if request_obj.status != AssetRequest.Status.PENDING:
            if request_obj.status == AssetRequest.Status.REJECTED:
                msg = "This request is already rejected."
            elif request_obj.status == AssetRequest.Status.APPROVED:
                msg = "This request is already approved."
            else:
                msg = f"Cannot approve request with status {request_obj.status}."
            raise AFValidationError(msg)


        asset_to_allocate = None
        if asset_id:
            try:
                asset_to_allocate = Asset.objects.get(pk=asset_id)
            except Asset.DoesNotExist:
                raise AFValidationError("Provided asset does not exist.")
        else:
            # Try to find an available asset in the requested category
            if request_obj.category:
                asset_to_allocate = Asset.objects.filter(
                    category=request_obj.category,
                    status=Asset.Status.AVAILABLE
                ).first()

        if not asset_to_allocate:
            raise AFValidationError("No available assets found to fulfill this request.")
            
        if asset_to_allocate.status != Asset.Status.AVAILABLE:
            raise AFValidationError("The selected asset is not available for allocation.")

        with transaction.atomic():
            request_obj.status = AssetRequest.Status.APPROVED
            request_obj.approved_by = approved_by
            request_obj.approved_at = timezone.now()
            
            # Create the allocation
            allocation = AllocationService.allocate(
                asset=asset_to_allocate,
                employee=request_obj.requested_by,
                assigned_by=approved_by,
                remarks=notes or f"Generated from Request {request_obj.request_number}"
            )
            
            request_obj.allocation = allocation
            
            request_obj.updated_by = updated_by
            
            request_obj.save(update_fields=[
                "status", "approved_by", "approved_at", "updated_at", "allocation", "updated_by"
            ])

        NotificationService.notify_request_approved(request_obj)

        return request_obj

    @staticmethod
    def reject(request_obj, rejected_by, rejection_reason="", updated_by=None):
        if request_obj.status != AssetRequest.Status.PENDING:
            if request_obj.status == AssetRequest.Status.REJECTED:
                msg = "This request is already rejected."
            elif request_obj.status == AssetRequest.Status.APPROVED:
                msg = "This request is already approved."
            else:
                msg = f"Cannot reject request with status {request_obj.status}."
            raise AFValidationError(msg)

        with transaction.atomic():
            request_obj.status = AssetRequest.Status.REJECTED
            request_obj.rejected_by = rejected_by
            request_obj.rejected_at = timezone.now()
            request_obj.rejection_reason = rejection_reason
            request_obj.updated_by = updated_by
            request_obj.save(update_fields=[
                "status", "rejected_by", "rejected_at",
                "rejection_reason", "updated_at", "updated_by"
            ])

        NotificationService.notify_request_rejected(request_obj)

        return request_obj

    @staticmethod
    def cancel(request_obj, updated_by=None):
        if request_obj.status != AssetRequest.Status.PENDING:
            if request_obj.status == AssetRequest.Status.REJECTED:
                msg = "This request is already rejected."
            elif request_obj.status == AssetRequest.Status.CANCELLED:
                msg = "This request is already cancelled."
            elif request_obj.status == AssetRequest.Status.APPROVED:
                msg = "This request is already approved and cannot be cancelled."
            else:
                msg = f"Cannot cancel request with status {request_obj.status}."
            raise AFValidationError(msg)

        request_obj.status = AssetRequest.Status.CANCELLED
        request_obj.updated_by = updated_by
        request_obj.save(update_fields=["status", "updated_at", "updated_by"])
        return request_obj
