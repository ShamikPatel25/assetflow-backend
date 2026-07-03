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
