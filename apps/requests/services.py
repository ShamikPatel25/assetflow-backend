from django.db import transaction
from django.utils import timezone

from apps.requests.models import AssetRequest
from django.conf import settings
from apps.base.errors import AFValidationError
from apps.base.utils import generate_reference_number
from apps.allocations.services import AllocationService
from apps.assets.models import Asset
from apps.notifications.services import NotificationService
from apps.audit.services import log_action


class AssetRequestService:
    """Business logic for asset request workflow."""

    @staticmethod
    def create_request(employee, category=None, preferred_asset=None,
                       reason="", priority="MEDIUM", created_by=None):
        request_obj = AssetRequest.objects.create(
            request_number=generate_reference_number(settings.REF_PREFIX_REQUEST),
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
        with transaction.atomic():
            # Acquire row lock BEFORE checking status to prevent approve/cancel races
            locked_req = AssetRequest.objects.select_for_update().get(pk=request_obj.pk)

            if locked_req.status != AssetRequest.Status.PENDING:
                if locked_req.status == AssetRequest.Status.CANCELLED:
                    msg = "This request has been cancelled and cannot be approved."
                elif locked_req.status == AssetRequest.Status.REJECTED:
                    msg = "This request is already rejected."
                elif locked_req.status == AssetRequest.Status.APPROVED:
                    msg = "This request is already approved."
                elif locked_req.status == AssetRequest.Status.ALLOCATED:
                    msg = "This request has already been fulfilled."
                else:
                    msg = f"Cannot approve request with status {locked_req.status}."
                raise AFValidationError(msg)

            asset_to_allocate = None
            if asset_id:
                # Lock the specific asset row too
                try:
                    asset_to_allocate = Asset.objects.select_for_update().get(pk=asset_id)
                except Asset.DoesNotExist:
                    raise AFValidationError("Provided asset does not exist.")
            else:
                # Find and lock an available asset in the requested category
                if locked_req.category:
                    asset_to_allocate = (
                        Asset.objects.select_for_update(skip_locked=True)
                        .filter(
                            category=locked_req.category,
                            status=Asset.Status.AVAILABLE,
                            is_deleted=False,
                        )
                        .first()
                    )

            if not asset_to_allocate:
                raise AFValidationError(
                    "No available assets found to fulfill this request."
                )

            if asset_to_allocate.status != Asset.Status.AVAILABLE:
                raise AFValidationError(
                    "The selected asset is not available for allocation."
                )

            locked_req.status = AssetRequest.Status.APPROVED
            locked_req.approved_by = approved_by
            locked_req.approved_at = timezone.now()

            # AllocationService.allocate() already runs inside its own atomic
            # block and calls select_for_update on the asset — safe to nest.
            allocation = AllocationService.allocate(
                asset=asset_to_allocate,
                employee=locked_req.requested_by,
                assigned_by=approved_by,
                remarks=notes or f"Generated from Request {locked_req.request_number}",
            )

            locked_req.allocation = allocation
            locked_req.updated_by = updated_by

            locked_req.save(update_fields=[
                "status", "approved_by", "approved_at", "updated_at", "allocation", "updated_by"
            ])

        NotificationService.notify_request_approved(locked_req)

        log_action(
            user=updated_by,
            action="APPROVE",
            module="ASSET_REQUEST",
            object_type="AssetRequest",
            object_id=locked_req.id,
            object_repr=str(locked_req),
            new_data={
                "status": locked_req.status,
                "approved_by": str(locked_req.approved_by_id) if locked_req.approved_by_id else None,
            },
        )

        return locked_req

    @staticmethod
    def reject(request_obj, rejected_by, rejection_reason="", updated_by=None):
        with transaction.atomic():
            locked_req = AssetRequest.objects.select_for_update().get(pk=request_obj.pk)

            if locked_req.status != AssetRequest.Status.PENDING:
                if locked_req.status == AssetRequest.Status.CANCELLED:
                    msg = "This request has been cancelled and cannot be rejected."
                elif locked_req.status == AssetRequest.Status.REJECTED:
                    msg = "This request is already rejected."
                elif locked_req.status == AssetRequest.Status.APPROVED:
                    msg = "This request is already approved and cannot be rejected."
                elif locked_req.status == AssetRequest.Status.ALLOCATED:
                    msg = "This request has already been fulfilled."
                else:
                    msg = f"Cannot reject request with status {locked_req.status}."
                raise AFValidationError(msg)

            locked_req.status = AssetRequest.Status.REJECTED
            locked_req.rejected_by = rejected_by
            locked_req.rejected_at = timezone.now()
            locked_req.rejection_reason = rejection_reason
            locked_req.updated_by = updated_by
            locked_req.save(update_fields=[
                "status", "rejected_by", "rejected_at",
                "rejection_reason", "updated_at", "updated_by"
            ])

        NotificationService.notify_request_rejected(locked_req)

        log_action(
            user=updated_by,
            action="REJECT",
            module="ASSET_REQUEST",
            object_type="AssetRequest",
            object_id=locked_req.id,
            object_repr=str(locked_req),
            new_data={
                "status": locked_req.status,
                "rejection_reason": rejection_reason,
            },
        )

        return locked_req

    @staticmethod
    def cancel(request_obj, updated_by=None):
        with transaction.atomic():
            locked_req = AssetRequest.objects.select_for_update().get(pk=request_obj.pk)

            if locked_req.status != AssetRequest.Status.PENDING:
                if locked_req.status == AssetRequest.Status.REJECTED:
                    msg = "This request is already rejected."
                elif locked_req.status == AssetRequest.Status.CANCELLED:
                    msg = "This request is already cancelled."
                elif locked_req.status == AssetRequest.Status.APPROVED:
                    msg = "This request is already approved and cannot be cancelled."
                elif locked_req.status == AssetRequest.Status.ALLOCATED:
                    msg = "This request has already been fulfilled and cannot be cancelled."
                else:
                    msg = f"Cannot cancel request with status {locked_req.status}."
                raise AFValidationError(msg)

            locked_req.status = AssetRequest.Status.CANCELLED
            locked_req.updated_by = updated_by
            locked_req.save(update_fields=["status", "updated_at", "updated_by"])

        log_action(
            user=updated_by,
            action="CANCEL",
            module="ASSET_REQUEST",
            object_type="AssetRequest",
            object_id=locked_req.id,
            object_repr=str(locked_req),
            new_data={"status": locked_req.status},
        )

        return locked_req

    @staticmethod
    def _bulk_transition(request_ids, action_fn):
        """
        Shared loop skeleton for bulk_approve and bulk_reject.

        Args:
            request_ids: Iterable of request UUID/str IDs.
            action_fn:   Callable(req_obj) → performs the transition.

        Returns:
            dict with keys "success", "failed", "errors".
        """
        success_count = 0
        failed_count = 0
        errors = []

        requests = AssetRequest.objects.filter(id__in=request_ids)
        request_map = {str(req.id): req for req in requests}

        for req_id in request_ids:
            req_str = str(req_id)
            if req_str not in request_map:
                failed_count += 1
                errors.append(f"Request {req_str}: Not found.")
                continue

            req_obj = request_map[req_str]
            try:
                action_fn(req_obj)
                success_count += 1
            except AFValidationError as e:
                failed_count += 1
                errors.append(f"Request {req_obj.request_number}: {e.detail.get('message', str(e))}")
            except Exception as e:
                failed_count += 1
                errors.append(f"Request {req_obj.request_number}: Internal error - {str(e)}")

        return {"success": success_count, "failed": failed_count, "errors": errors}

    @staticmethod
    def bulk_approve(request_ids, approved_by, notes="", updated_by=None):
        return AssetRequestService._bulk_transition(
            request_ids,
            lambda req_obj: AssetRequestService.approve(
                req_obj, approved_by=approved_by, notes=notes, updated_by=updated_by
            ),
        )

    @staticmethod
    def bulk_reject(request_ids, rejected_by, rejection_reason="", updated_by=None):
        return AssetRequestService._bulk_transition(
            request_ids,
            lambda req_obj: AssetRequestService.reject(
                req_obj,
                rejected_by=rejected_by,
                rejection_reason=rejection_reason,
                updated_by=updated_by,
            ),
        )
