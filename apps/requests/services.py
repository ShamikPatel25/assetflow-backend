import uuid
from django.db import transaction
from django.utils import timezone

from apps.requests.models import AssetRequest
from apps.base.errors import AFValidationError, error_codes


class AssetRequestService:
    """Business logic for asset request workflow."""

    @staticmethod
    def create_request(employee, category=None, preferred_asset=None,
                       reason="", priority="MEDIUM"):
        request_obj = AssetRequest.objects.create(
            request_number=f"REQ-{uuid.uuid4().hex[:8].upper()}",
            requested_by=employee,
            category=category,
            preferred_asset=preferred_asset,
            reason=reason,
            priority=priority,
            status=AssetRequest.Status.PENDING,
        )
        return request_obj

    @staticmethod
    def approve(request_obj, approved_by):
        if request_obj.status != AssetRequest.Status.PENDING:
            raise AFValidationError(
                "Only pending requests can be approved.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        with transaction.atomic():
            request_obj.status = AssetRequest.Status.APPROVED
            request_obj.approved_by = approved_by
            request_obj.approved_at = timezone.now()
            request_obj.save(update_fields=[
                "status", "approved_by", "approved_at", "updated_at",
            ])

        return request_obj

    @staticmethod
    def reject(request_obj, rejected_by, rejection_reason=""):
        if request_obj.status != AssetRequest.Status.PENDING:
            raise AFValidationError(
                "Only pending requests can be rejected.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        with transaction.atomic():
            request_obj.status = AssetRequest.Status.REJECTED
            request_obj.rejected_by = rejected_by
            request_obj.rejected_at = timezone.now()
            request_obj.rejection_reason = rejection_reason
            request_obj.save(update_fields=[
                "status", "rejected_by", "rejected_at",
                "rejection_reason", "updated_at",
            ])

        return request_obj

    @staticmethod
    def cancel(request_obj):
        if request_obj.status not in (
            AssetRequest.Status.PENDING,
            AssetRequest.Status.APPROVED,
        ):
            raise AFValidationError(
                "This request cannot be cancelled.",
                app_code=error_codes.INVALID_STATUS_TRANSITION,
            )

        request_obj.status = AssetRequest.Status.CANCELLED
        request_obj.save(update_fields=["status", "updated_at"])
        return request_obj
