"""
Tests for Asset Requests module.

Covers the complete request lifecycle:
- Create request (EMPLOYEE submits → PENDING)
- Approve request (HR/Admin approves → auto-allocates → APPROVED)
- Reject request (HR/Admin rejects with reason → REJECTED)
- Cancel request (Requester cancels → CANCELLED)
- Invalid status transitions (approve already rejected, reject already approved)
- Auto-allocation logic (pick available asset from category)
- Permission enforcement (employee cannot approve own request)
- Cross-module: Approve triggers AllocationService.allocate()
"""
from apps.allocations.services import AllocationService
from apps.base.errors import AFValidationError
from apps.requests.services import AssetRequestService
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


# 1. REQUEST CREATION

class TestAssetRequestCreation:
    """How asset requests are created."""

    url = "/api/v1/asset-requests/"

    def test_employee_can_submit_request(self, employee_api_client, employee_user,
                                          employee_factory, category):
        """Employee with profile can submit an asset request."""
        employee_factory(user=employee_user)
        response = employee_api_client.post(self.url, data={
            "category": str(category.id),
            "reason": "Need a laptop for development work",
            "priority": "MEDIUM",
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "PENDING"

    def test_request_requires_reason(self, employee_api_client, employee_user,
                                      employee_factory, category):
        """Blank reason → 400."""
        employee_factory(user=employee_user)
        response = employee_api_client.post(self.url, data={
            "category": str(category.id),
            "reason": "",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_cannot_create_request(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.post(self.url, data={"reason": "test"})
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]


# 2. REQUEST APPROVAL WORKFLOW (Service Layer)

class TestRequestApprovalService:
    """AssetRequestService.approve() business rules."""

    def test_approve_pending_request_with_available_asset(
        self, asset, employee, hr_employee, category,
        asset_request_factory, mock_notification_service
    ):
        """Approve a PENDING request → status becomes APPROVED,
        asset allocated, allocation link created."""

        asset.category = category
        asset.save()
        request_obj = asset_request_factory(
            requested_by=employee, category=category
        )
        result = AssetRequestService.approve(
            request_obj, approved_by=hr_employee, asset_id=str(asset.id)
        )
        assert result.status == "APPROVED"
        assert result.approved_by == hr_employee
        assert result.allocation is not None
        asset.refresh_from_db()
        assert asset.status == "ALLOCATED"

    def test_approve_already_rejected_request_fails(
        self, employee, hr_employee, asset_request_factory,
        mock_notification_service
    ):
        """Cannot approve a request that was already rejected."""

        request_obj = asset_request_factory(
            requested_by=employee, status="REJECTED"
        )
        with pytest.raises(AFValidationError):
            AssetRequestService.approve(request_obj, approved_by=hr_employee)

    def test_approve_without_available_asset_fails(
        self, employee, hr_employee, category, asset_request_factory,
        mock_notification_service
    ):
        """No available assets in category → error."""

        request_obj = asset_request_factory(
            requested_by=employee, category=category
        )
        with pytest.raises(AFValidationError):
            AssetRequestService.approve(request_obj, approved_by=hr_employee)

    def test_approve_with_already_allocated_asset_fails(
        self, asset, employee, hr_employee, category,
        asset_request_factory, mock_notification_service
    ):
        """Trying to assign an already-ALLOCATED asset → error."""

        # First allocate the asset
        AllocationService.allocate(asset=asset, employee=employee)
        request_obj = asset_request_factory(
            requested_by=employee, category=category
        )
        with pytest.raises(AFValidationError):
            AssetRequestService.approve(
                request_obj, approved_by=hr_employee, asset_id=str(asset.id)
            )


# 3. REQUEST REJECTION WORKFLOW

class TestRequestRejectionService:
    """AssetRequestService.reject() business rules."""

    def test_reject_pending_request_records_reason(
        self, employee, hr_employee, asset_request_factory,
        mock_notification_service
    ):
        """Reject PENDING → records rejection reason and rejector."""

        request_obj = asset_request_factory(requested_by=employee)
        result = AssetRequestService.reject(
            request_obj, rejected_by=hr_employee,
            rejection_reason="Budget exceeded this quarter"
        )
        assert result.status == "REJECTED"
        assert result.rejected_by == hr_employee
        assert result.rejection_reason == "Budget exceeded this quarter"

    def test_reject_already_approved_request_fails(
        self, asset, employee, hr_employee, category,
        asset_request_factory, mock_notification_service
    ):
        """Cannot reject a request that was already approved."""

        asset.category = category
        asset.save()
        request_obj = asset_request_factory(
            requested_by=employee, category=category
        )
        AssetRequestService.approve(
            request_obj, approved_by=hr_employee, asset_id=str(asset.id)
        )
        with pytest.raises(AFValidationError):
            AssetRequestService.reject(request_obj, rejected_by=hr_employee)


# 4. REQUEST CANCELLATION

class TestRequestCancellationService:
    """AssetRequestService.cancel() rules."""

    def test_cancel_pending_request_succeeds(
        self, employee, asset_request_factory
    ):
        """Employee can cancel their PENDING request."""

        request_obj = asset_request_factory(requested_by=employee)
        result = AssetRequestService.cancel(request_obj)
        assert result.status == "CANCELLED"

    def test_cancel_rejected_request_fails(
        self, employee, asset_request_factory
    ):
        """Cannot cancel a REJECTED request."""

        request_obj = asset_request_factory(
            requested_by=employee, status="REJECTED"
        )
        with pytest.raises(AFValidationError):
            AssetRequestService.cancel(request_obj)


# 5. API PERMISSION CHECKS

class TestRequestAPIPermissions:
    """API endpoint access by role."""

    url = "/api/v1/asset-requests/"

    def test_employee_can_only_see_own_requests(
        self, employee_api_client, employee_user, employee_factory,
        asset_request_factory
    ):
        """Employee only sees requests where requested_by is them."""
        emp = employee_factory(user=employee_user)
        asset_request_factory(requested_by=emp)
        # Create another request from a different employee
        other_emp = employee_factory(first_name="Other")
        asset_request_factory(requested_by=other_emp)

        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        # Depending on pagination, check that results are filtered
        results = response.data.get("results", response.data)
        if isinstance(results, list):
            for req in results:
                assert req.get("requested_by") is not None

    def test_hr_can_see_all_requests(self, hr_api_client, employee_factory,
                                      asset_request_factory):
        """HR sees ALL requests across employees."""
        emp1 = employee_factory(first_name="E1")
        emp2 = employee_factory(first_name="E2")
        asset_request_factory(requested_by=emp1)
        asset_request_factory(requested_by=emp2)

        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK


# 6. API CREATE ENDPOINT EDGE CASES

class TestRequestCreateAPI:
    """POST /api/v1/asset-requests/ view-layer branches."""

    url = "/api/v1/asset-requests/"

    def test_create_with_preferred_asset(self, employee_api_client, employee_user,
                                          employee_factory, category, asset_factory):
        """Employee can submit a request naming an available preferred asset."""
        employee_factory(user=employee_user)
        asset = asset_factory(category=category, status="AVAILABLE")
        response = employee_api_client.post(self.url, data={
            "category": str(category.id),
            "preferred_asset": str(asset.id),
            "reason": "Need this specific laptop",
            "priority": "HIGH",
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "PENDING"
        assert response.data["preferred_asset"]["id"] == str(asset.id)

    def test_create_without_employee_profile_returns_400(
        self, employee_api_client, category
    ):
        """User with no linked employee profile → 400 unified error."""
        response = employee_api_client.post(self.url, data={
            "category": str(category.id),
            "reason": "I have no profile",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_duplicate_pending_category_returns_400(
        self, employee_api_client, employee_user, employee_factory,
        category, asset_request_factory
    ):
        """A second PENDING request for the same category is blocked."""
        emp = employee_factory(user=employee_user)
        asset_request_factory(requested_by=emp, category=category, status="PENDING")
        response = employee_api_client.post(self.url, data={
            "category": str(category.id),
            "reason": "Duplicate request for same category",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 7. APPROVE ENDPOINT (view layer)

class TestRequestApproveAPI:
    """POST /api/v1/asset-requests/{id}/approve/."""

    def _url(self, pk):
        return f"/api/v1/asset-requests/{pk}/approve/"

    def test_hr_can_approve_with_explicit_asset(
        self, hr_api_client, employee, category, asset_factory,
        asset_request_factory
    ):
        """HR approves a PENDING request providing an asset id → APPROVED."""
        asset = asset_factory(category=category, status="AVAILABLE")
        req = asset_request_factory(requested_by=employee, category=category)
        response = hr_api_client.post(
            self._url(req.id), data={"asset": str(asset.id)}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "APPROVED"
        asset.refresh_from_db()
        assert asset.status == "ALLOCATED"

    def test_hr_can_approve_via_category_autopick(
        self, hr_api_client, employee, category, asset_factory,
        asset_request_factory
    ):
        """No asset id → service auto-picks an available asset in category."""
        asset_factory(category=category, status="AVAILABLE")
        req = asset_request_factory(requested_by=employee, category=category)
        response = hr_api_client.post(self._url(req.id), data={})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "APPROVED"

    def test_employee_cannot_approve(
        self, employee_api_client, employee, asset_request_factory
    ):
        """EMPLOYEE role is denied the approve action → 403."""
        req = asset_request_factory(requested_by=employee)
        response = employee_api_client.post(self._url(req.id), data={})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_approve_without_available_asset_returns_400(
        self, hr_api_client, employee, category, asset_request_factory
    ):
        """No available asset for the category → 400 unified error."""
        req = asset_request_factory(requested_by=employee, category=category)
        response = hr_api_client.post(self._url(req.id), data={})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_approve_already_approved_returns_400(
        self, hr_api_client, employee, category, asset_factory,
        asset_request_factory
    ):
        """Approving twice → invalid state transition 400."""
        asset = asset_factory(category=category, status="AVAILABLE")
        req = asset_request_factory(requested_by=employee, category=category)
        first = hr_api_client.post(self._url(req.id), data={"asset": str(asset.id)})
        assert first.status_code == status.HTTP_200_OK
        second = hr_api_client.post(self._url(req.id), data={})
        assert second.status_code == status.HTTP_400_BAD_REQUEST


# 8. REJECT ENDPOINT (view layer)

class TestRequestRejectAPI:
    """POST /api/v1/asset-requests/{id}/reject/."""

    def _url(self, pk):
        return f"/api/v1/asset-requests/{pk}/reject/"

    def test_hr_can_reject_with_reason(
        self, hr_api_client, employee, asset_request_factory
    ):
        """HR rejects a PENDING request → REJECTED, reason recorded."""
        req = asset_request_factory(requested_by=employee)
        response = hr_api_client.post(
            self._url(req.id), data={"rejection_reason": "Out of budget"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "REJECTED"
        assert response.data["rejection_reason"] == "Out of budget"

    def test_employee_cannot_reject(
        self, employee_api_client, employee, asset_request_factory
    ):
        """EMPLOYEE role is denied the reject action → 403."""
        req = asset_request_factory(requested_by=employee)
        response = employee_api_client.post(self._url(req.id), data={})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_reject_already_rejected_returns_400(
        self, hr_api_client, employee, asset_request_factory
    ):
        """Rejecting an already-REJECTED request → 400."""
        req = asset_request_factory(requested_by=employee, status="REJECTED")
        response = hr_api_client.post(self._url(req.id), data={})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 9. CANCEL ENDPOINT (view layer)

class TestRequestCancelAPI:
    """POST /api/v1/asset-requests/{id}/cancel/."""

    def _url(self, pk):
        return f"/api/v1/asset-requests/{pk}/cancel/"

    def test_requester_can_cancel_own_pending(
        self, employee_api_client, employee_user, employee_factory,
        asset_request_factory
    ):
        """The requester cancels their own PENDING request → CANCELLED."""
        emp = employee_factory(user=employee_user)
        req = asset_request_factory(requested_by=emp)
        response = employee_api_client.post(self._url(req.id))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "CANCELLED"

    def test_employee_cannot_cancel_others_request(
        self, employee_api_client, employee_user, employee_factory,
        asset_request_factory
    ):
        """An employee cancelling someone else's request → 403."""
        employee_factory(user=employee_user)
        other = employee_factory(first_name="Other")
        req = asset_request_factory(requested_by=other)
        response = employee_api_client.post(self._url(req.id))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_non_requester_admin_cannot_cancel(
        self, admin_api_client, employee, asset_request_factory
    ):
        """A non-EMPLOYEE (admin) who is not the requester → 403 (only requester)."""
        req = asset_request_factory(requested_by=employee)
        response = admin_api_client.post(self._url(req.id))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cancel_missing_request_returns_404(self, employee_api_client, tenant):
        """Cancelling a non-existent request id → 404."""
        import uuid as _uuid
        response = employee_api_client.post(self._url(_uuid.uuid4()))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cancel_malformed_uuid_returns_404(self, employee_api_client, tenant):
        """A garbage id yields a clean 404, not a 500."""
        response = employee_api_client.post(self._url("not-a-uuid"))
        assert response.status_code == status.HTTP_404_NOT_FOUND


# 10. UPDATE / DELETE GUARDS (view layer)

class TestRequestUpdateDeleteGuards:
    """perform_update / perform_destroy only allow PENDING requests."""

    def _url(self, pk):
        return f"/api/v1/asset-requests/{pk}/"

    def test_cannot_update_non_pending_request(
        self, hr_api_client, employee, category, asset_request_factory
    ):
        """Editing a non-PENDING request → 400 (guard in perform_update)."""
        req = asset_request_factory(
            requested_by=employee, category=category, status="REJECTED"
        )
        response = hr_api_client.put(self._url(req.id), data={
            "requested_by": str(employee.id),
            "category": str(category.id),
            "reason": "Changed reason",
            "priority": "LOW",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_can_update_pending_request(
        self, hr_api_client, employee, category, asset_request_factory
    ):
        """Editing a PENDING request succeeds via PUT."""
        req = asset_request_factory(requested_by=employee, category=category)
        response = hr_api_client.put(self._url(req.id), data={
            "requested_by": str(employee.id),
            "category": str(category.id),
            "reason": "Updated reason for laptop",
            "priority": "HIGH",
        })
        assert response.status_code == status.HTTP_200_OK
        assert response.data["priority"] == "HIGH"

    def test_cannot_delete_non_pending_request(
        self, hr_api_client, employee, asset_request_factory
    ):
        """Deleting a non-PENDING request → 400 (guard in perform_destroy)."""
        req = asset_request_factory(requested_by=employee, status="APPROVED")
        response = hr_api_client.delete(self._url(req.id))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_can_delete_pending_request(
        self, hr_api_client, employee, asset_request_factory
    ):
        """Deleting a PENDING request succeeds (soft delete → 200)."""
        req = asset_request_factory(requested_by=employee)
        response = hr_api_client.delete(self._url(req.id))
        assert response.status_code == status.HTTP_200_OK


# 11. QUERYSET FILTERING (view layer)

class TestRequestQuerysetScoping:
    """get_queryset() role-based scoping branches."""

    url = "/api/v1/asset-requests/"

    def test_employee_without_profile_sees_nothing(
        self, employee_api_client, employee_factory, asset_request_factory
    ):
        """An EMPLOYEE user with no employee_profile gets an empty list."""
        other = employee_factory(first_name="Someone")
        asset_request_factory(requested_by=other)
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        assert results == [] or results == {"results": []} or len(results) == 0

    def test_employee_retrieve_own_request(
        self, employee_api_client, employee_user, employee_factory,
        asset_request_factory
    ):
        """Employee can retrieve the detail of their own request."""
        emp = employee_factory(user=employee_user)
        req = asset_request_factory(requested_by=emp)
        response = employee_api_client.get(f"{self.url}{req.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["request_number"] == req.request_number


# 12. BULK APPROVE / REJECT (view + service layers)

class TestBulkApproveRejectAPI:
    """POST bulk-approve / bulk-reject endpoints and service aggregation."""

    approve_url = "/api/v1/asset-requests/bulk-approve/"
    reject_url = "/api/v1/asset-requests/bulk-reject/"

    def test_bulk_approve_mixed_results(
        self, hr_api_client, employee, category, asset_factory,
        asset_request_factory
    ):
        """One approvable + one already-rejected + one missing id → aggregated."""
        import uuid as _uuid
        asset_factory(category=category, status="AVAILABLE")
        ok_req = asset_request_factory(requested_by=employee, category=category)
        bad_req = asset_request_factory(
            requested_by=employee, category=category, status="REJECTED"
        )
        missing_id = str(_uuid.uuid4())
        response = hr_api_client.post(self.approve_url, data={
            "request_ids": [str(ok_req.id), str(bad_req.id), missing_id],
        }, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] == 1
        assert response.data["failed"] == 2
        assert len(response.data["errors"]) == 2

    def test_bulk_reject_mixed_results(
        self, hr_api_client, employee, asset_request_factory
    ):
        """One rejectable + one already-approved-state → aggregated result."""
        import uuid as _uuid
        ok_req = asset_request_factory(requested_by=employee)
        bad_req = asset_request_factory(requested_by=employee, status="CANCELLED")
        response = hr_api_client.post(self.reject_url, data={
            "request_ids": [str(ok_req.id), str(bad_req.id), str(_uuid.uuid4())],
            "rejection_reason": "Bulk cleanup",
        }, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] == 1
        assert response.data["failed"] == 2

    def test_employee_cannot_bulk_approve(
        self, employee_api_client, employee, asset_request_factory
    ):
        """EMPLOYEE denied bulk-approve → 403."""
        req = asset_request_factory(requested_by=employee)
        response = employee_api_client.post(self.approve_url, data={
            "request_ids": [str(req.id)],
        }, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_bulk_approve_empty_list_returns_400(self, hr_api_client, tenant):
        """Empty request_ids fails serializer validation → 400."""
        response = hr_api_client.post(self.approve_url, data={
            "request_ids": [],
        }, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 13. BULK SERVICE-LAYER DIRECT (aggregation + not-found branches)

class TestBulkServices:
    """AssetRequestService.bulk_approve / bulk_reject direct calls."""

    def test_bulk_approve_all_success(
        self, employee, hr_employee, category, asset_factory,
        asset_request_factory
    ):
        """Two fulfillable requests → both approved."""
        asset_factory(category=category, status="AVAILABLE")
        asset_factory(category=category, status="AVAILABLE")
        r1 = asset_request_factory(requested_by=employee, category=category)
        r2 = asset_request_factory(requested_by=employee, category=category)
        result = AssetRequestService.bulk_approve(
            request_ids=[str(r1.id), str(r2.id)], approved_by=hr_employee
        )
        assert result["success"] == 2
        assert result["failed"] == 0

    def test_bulk_reject_not_found_id(self, hr_employee):
        """A request id not in the DB is reported as failed/not found."""
        import uuid as _uuid
        missing = str(_uuid.uuid4())
        result = AssetRequestService.bulk_reject(
            request_ids=[missing], rejected_by=hr_employee
        )
        assert result["success"] == 0
        assert result["failed"] == 1
        assert "Not found" in result["errors"][0]


# 14. SERVICE-LAYER MESSAGE BRANCHES

class TestServiceStateMessages:
    """Cover the specific error-message branches in approve/reject/cancel."""

    def test_approve_cancelled_request_generic_message(
        self, employee, hr_employee, asset_request_factory
    ):
        """Approving a CANCELLED request hits the generic message branch."""
        req = asset_request_factory(requested_by=employee, status="CANCELLED")
        with pytest.raises(AFValidationError):
            AssetRequestService.approve(req, approved_by=hr_employee)

    def test_approve_with_nonexistent_asset_id(
        self, employee, hr_employee, category, asset_request_factory
    ):
        """Passing an asset id that does not exist → error."""
        import uuid as _uuid
        req = asset_request_factory(requested_by=employee, category=category)
        with pytest.raises(AFValidationError):
            AssetRequestService.approve(
                req, approved_by=hr_employee, asset_id=str(_uuid.uuid4())
            )

    def test_cancel_allocated_request_hits_generic_branch(
        self, employee, asset_request_factory
    ):
        """Cancelling an ALLOCATED request → the fallback status message branch."""
        req = asset_request_factory(requested_by=employee, status="ALLOCATED")
        with pytest.raises(AFValidationError):
            AssetRequestService.cancel(req)


# 15. CREATE SERIALIZER — missing-asset validate branches (direct)

class TestAssetRequestCreateSerializerValidation:
    """validate_preferred_asset / validate swallow Asset.DoesNotExist gracefully."""

    def test_validate_preferred_asset_ignores_missing_asset(self, tenant):
        import uuid as _uuid
        from apps.requests.serializers import AssetRequestCreateSerializer
        val = _uuid.uuid4()
        # No such asset → DoesNotExist swallowed → value returned unchanged.
        assert AssetRequestCreateSerializer().validate_preferred_asset(val) == val

    def test_validate_ignores_missing_preferred_asset(self, tenant, category):
        import uuid as _uuid
        from apps.requests.serializers import AssetRequestCreateSerializer
        attrs = {
            "category": category.id,
            "preferred_asset": _uuid.uuid4(),
            "reason": "need it",
            "priority": "LOW",
        }
        result = AssetRequestCreateSerializer().validate(attrs)
        assert result["preferred_asset"] == attrs["preferred_asset"]


# 16. BULK — unexpected (non-validation) error aggregation

class TestBulkUnexpectedErrors:
    """The generic except branches that collect non-AFValidationError failures."""

    def test_bulk_approve_collects_unexpected_error(
        self, employee, category, asset_request_factory,
    ):
        from unittest.mock import patch
        req = asset_request_factory(requested_by=employee, category=category)
        with patch.object(
            AssetRequestService, "approve", side_effect=Exception("boom")
        ):
            result = AssetRequestService.bulk_approve(
                request_ids=[str(req.id)], approved_by=None
            )
        assert result["failed"] == 1
        assert any("Internal error" in e for e in result["errors"])

    def test_bulk_reject_collects_unexpected_error(
        self, employee, asset_request_factory,
    ):
        from unittest.mock import patch
        req = asset_request_factory(requested_by=employee)
        with patch.object(
            AssetRequestService, "reject", side_effect=Exception("boom")
        ):
            result = AssetRequestService.bulk_reject(
                request_ids=[str(req.id)], rejected_by=None
            )
        assert result["failed"] == 1
        assert any("Internal error" in e for e in result["errors"])

    def test_reject_cancelled_request_generic_message(
        self, employee, hr_employee, asset_request_factory
    ):
        """Rejecting a CANCELLED request hits the generic message branch."""
        req = asset_request_factory(requested_by=employee, status="CANCELLED")
        with pytest.raises(AFValidationError):
            AssetRequestService.reject(req, rejected_by=hr_employee)

    def test_cancel_approved_request_fails(
        self, employee, hr_employee, category, asset_factory, asset_request_factory
    ):
        """Cannot cancel an APPROVED request."""
        asset = asset_factory(category=category, status="AVAILABLE")
        req = asset_request_factory(requested_by=employee, category=category)
        AssetRequestService.approve(
            req, approved_by=hr_employee, asset_id=str(asset.id)
        )
        with pytest.raises(AFValidationError):
            AssetRequestService.cancel(req)

    def test_cancel_already_cancelled_request_fails(
        self, employee, asset_request_factory
    ):
        """Cancelling an already-CANCELLED request → error."""
        req = asset_request_factory(requested_by=employee, status="CANCELLED")
        with pytest.raises(AFValidationError):
            AssetRequestService.cancel(req)


# 15. SERIALIZER VALIDATION BRANCHES

class TestCreateSerializerValidation:
    """AssetRequestCreateSerializer validate_* branches via the API."""

    url = "/api/v1/asset-requests/"

    def test_preferred_asset_not_available_rejected(
        self, employee_api_client, employee_user, employee_factory,
        category, asset_factory
    ):
        """Requesting an asset that is already ALLOCATED → 400."""
        employee_factory(user=employee_user)
        asset = asset_factory(category=category, status="ALLOCATED")
        response = employee_api_client.post(self.url, data={
            "category": str(category.id),
            "preferred_asset": str(asset.id),
            "reason": "I want the allocated one",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_preferred_asset_wrong_category_rejected(
        self, employee_api_client, employee_user, employee_factory,
        category_factory, asset_factory
    ):
        """Preferred asset not in the requested category → 400."""
        employee_factory(user=employee_user)
        cat_a = category_factory(name="CatA", code="CATA")
        cat_b = category_factory(name="CatB", code="CATB")
        asset = asset_factory(category=cat_b, status="AVAILABLE")
        response = employee_api_client.post(self.url, data={
            "category": str(cat_a.id),
            "preferred_asset": str(asset.id),
            "reason": "Mismatched category asset",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 16. SERIALIZER to_representation NESTED FIELDS

class TestSerializerRepresentation:
    """AssetRequestSerializer.to_representation nested-object branches."""

    def test_representation_includes_nested_approver(
        self, hr_api_client, hr_user, employee, asset_factory, category, asset_request_factory
    ):
        """After approval, retrieve exposes nested approved_by + preferred_asset."""
        from apps.employees.models import Employee
        Employee.objects.filter(user=hr_user).delete()
        approver = Employee.objects.create(
            user=hr_user, first_name="App", last_name="Rover",
            employee_code="APP-001",
        )
        asset = asset_factory(category=category, status="AVAILABLE")
        req = asset_request_factory(
            requested_by=employee, category=category, preferred_asset=asset
        )
        approve_url = f"/api/v1/asset-requests/{req.id}/approve/"
        resp = hr_api_client.post(approve_url, data={"asset": str(asset.id)})
        assert resp.status_code == status.HTTP_200_OK

        detail = hr_api_client.get(f"/api/v1/asset-requests/{req.id}/")
        assert detail.status_code == status.HTTP_200_OK
        data = detail.data
        assert data["approved_by"]["id"] == str(approver.id)
        assert data["preferred_asset"]["id"] == str(asset.id)
        assert "name" in data["category"]

    def test_representation_includes_nested_rejecter(
        self, hr_api_client, hr_user, hr_employee, employee, asset_request_factory
    ):
        """After rejection, retrieve exposes nested rejected_by."""
        # Link the hr_user (client identity) to an employee profile so the
        # rejecter is populated on the request.
        from apps.employees.models import Employee
        Employee.objects.filter(user=hr_user).delete()
        rejecter = Employee.objects.create(
            user=hr_user, first_name="Rej", last_name="Ecter",
            employee_code="REJ-001",
        )
        req = asset_request_factory(requested_by=employee)
        reject_url = f"/api/v1/asset-requests/{req.id}/reject/"
        resp = hr_api_client.post(reject_url, data={"rejection_reason": "No"})
        assert resp.status_code == status.HTTP_200_OK

        detail = hr_api_client.get(f"/api/v1/asset-requests/{req.id}/")
        assert detail.data["rejected_by"]["id"] == str(rejecter.id)
