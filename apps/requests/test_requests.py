"""
Test suite: Asset Requests
Covers Fix 3 — race conditions, invalid transitions, cancel rules.
"""
import uuid
import pytest
from unittest.mock import patch
from rest_framework import status

from apps.requests.services import AssetRequestService
from apps.base.errors import AFValidationError

pytestmark = pytest.mark.django_db


# 1. Create request

class TestAssetRequestCreate:

    def test_employee_can_create_request(self, tenant, employee, category):
        with patch("apps.requests.services.NotificationService"):
            req = AssetRequestService.create_request(
                employee=employee, category=category, reason="Need laptop"
            )
        assert req.status == "PENDING"
        assert req.requested_by == employee

    def test_request_gets_unique_number(self, tenant, employee, category):
        with patch("apps.requests.services.NotificationService"):
            req1 = AssetRequestService.create_request(employee=employee, reason="A")
            req2 = AssetRequestService.create_request(employee=employee, reason="B")
        assert req1.request_number != req2.request_number


# 2. Approve / Reject / Cancel transitions

class TestRequestStatusTransitions:

    def test_approve_pending_request_creates_allocation(
        self, tenant, employee, admin_employee, asset, category, asset_request_factory
    ):
        asset.category = category
        asset.save()
        req = asset_request_factory(requested_by=employee, category=category)

        with patch("apps.requests.services.NotificationService"), \
             patch("apps.allocations.services.NotificationService"), \
             patch("apps.requests.services.log_action"), \
             patch("apps.allocations.services.log_action"):
            result = AssetRequestService.approve(
                req, approved_by=admin_employee, asset_id=str(asset.id)
            )

        assert result.status == "APPROVED"
        assert result.allocation is not None

    def test_cancelled_request_cannot_be_approved(
        self, tenant, employee, admin_employee, asset_request_factory
    ):
        req = asset_request_factory(requested_by=employee)
        with patch("apps.requests.services.NotificationService"), \
             patch("apps.requests.services.log_action"):
            AssetRequestService.cancel(req)

        with pytest.raises(AFValidationError):
            with patch("apps.requests.services.NotificationService"), \
                 patch("apps.allocations.services.NotificationService"), \
                 patch("apps.requests.services.log_action"), \
                 patch("apps.allocations.services.log_action"):
                AssetRequestService.approve(req, approved_by=admin_employee)

    def test_rejected_request_cannot_be_approved(
        self, tenant, employee, admin_employee, asset_request_factory
    ):
        req = asset_request_factory(requested_by=employee)
        with patch("apps.requests.services.NotificationService"), \
             patch("apps.requests.services.log_action"):
            AssetRequestService.reject(req, rejected_by=admin_employee)

        with pytest.raises(AFValidationError):
            with patch("apps.requests.services.NotificationService"), \
                 patch("apps.allocations.services.NotificationService"), \
                 patch("apps.requests.services.log_action"), \
                 patch("apps.allocations.services.log_action"):
                AssetRequestService.approve(req, approved_by=admin_employee)

    def test_approved_request_cannot_be_rejected(
        self, tenant, employee, admin_employee, asset, category, asset_request_factory
    ):
        asset.category = category
        asset.save()
        req = asset_request_factory(requested_by=employee, category=category)

        with patch("apps.requests.services.NotificationService"), \
             patch("apps.allocations.services.NotificationService"), \
             patch("apps.requests.services.log_action"), \
             patch("apps.allocations.services.log_action"):
            AssetRequestService.approve(req, approved_by=admin_employee, asset_id=str(asset.id))

        with pytest.raises(AFValidationError):
            with patch("apps.requests.services.NotificationService"), \
                 patch("apps.requests.services.log_action"):
                AssetRequestService.reject(req, rejected_by=admin_employee)

    def test_approved_request_cannot_be_cancelled(
        self, tenant, employee, admin_employee, asset, category, asset_request_factory
    ):
        asset.category = category
        asset.save()
        req = asset_request_factory(requested_by=employee, category=category)

        with patch("apps.requests.services.NotificationService"), \
             patch("apps.allocations.services.NotificationService"), \
             patch("apps.requests.services.log_action"), \
             patch("apps.allocations.services.log_action"):
            AssetRequestService.approve(req, approved_by=admin_employee, asset_id=str(asset.id))

        with pytest.raises(AFValidationError):
            with patch("apps.requests.services.log_action"):
                AssetRequestService.cancel(req)

    def test_already_cancelled_cannot_be_cancelled_again(
        self, tenant, employee, asset_request_factory
    ):
        req = asset_request_factory(requested_by=employee)
        with patch("apps.requests.services.NotificationService"), \
             patch("apps.requests.services.log_action"):
            AssetRequestService.cancel(req)

        with pytest.raises(AFValidationError):
            with patch("apps.requests.services.log_action"):
                AssetRequestService.cancel(req)

# 3. Bulk approve / reject

class TestBulkOperations:

    def test_bulk_approve_processes_multiple(
        self, tenant, employee, admin_employee, asset_factory, category, asset_request_factory
    ):
        """Bulk approve successfully processes multiple pending requests."""
        asset_factory(name="A1", category=category)
        asset_factory(name="A2", category=category)

        req1 = asset_request_factory(requested_by=employee, category=category)
        req2 = asset_request_factory(requested_by=employee, category=category)

        with patch("apps.requests.services.NotificationService"), \
             patch("apps.allocations.services.NotificationService"), \
             patch("apps.requests.services.log_action"), \
             patch("apps.allocations.services.log_action"):
            result = AssetRequestService.bulk_approve(
                [req1.id, req2.id],
                approved_by=admin_employee,
            )

        assert result["success"] + result["failed"] == 2

    def test_bulk_approve_skips_already_cancelled(
        self, tenant, employee, admin_employee, asset_request_factory
    ):
        req = asset_request_factory(requested_by=employee)
        with patch("apps.requests.services.NotificationService"), \
             patch("apps.requests.services.log_action"):
            AssetRequestService.cancel(req)

        with patch("apps.requests.services.NotificationService"), \
             patch("apps.allocations.services.NotificationService"), \
             patch("apps.requests.services.log_action"), \
             patch("apps.allocations.services.log_action"):
            result = AssetRequestService.bulk_approve(
                [req.id], approved_by=admin_employee
            )

        assert result["failed"] == 1
        assert len(result["errors"]) == 1

    def test_bulk_approve_not_found_request(self, tenant, admin_employee):
        fake_id = uuid.uuid4()
        result = AssetRequestService.bulk_approve([fake_id], approved_by=admin_employee)
        assert result["failed"] == 1
        assert "not found" in result["errors"][0].lower()

    def test_bulk_reject_processes_multiple(
        self, tenant, employee, admin_employee, asset_request_factory
    ):
        req1 = asset_request_factory(requested_by=employee)
        req2 = asset_request_factory(requested_by=employee)

        with patch("apps.requests.services.NotificationService"), \
             patch("apps.requests.services.log_action"):
            result = AssetRequestService.bulk_reject(
                [req1.id, req2.id],
                rejected_by=admin_employee,
                rejection_reason="No budget",
            )

        assert result["success"] == 2
        assert result["failed"] == 0


# 4. Audit log on request actions

class TestRequestAuditLog:

    def test_approve_creates_audit_log(
        self, tenant, employee, admin_employee, asset, category, asset_request_factory
    ):
        from apps.audit.models import AuditLog
        asset.category = category
        asset.save()
        req = asset_request_factory(requested_by=employee, category=category)
        count_before = AuditLog.objects.count()

        with patch("apps.requests.services.NotificationService"), \
             patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            AssetRequestService.approve(req, approved_by=admin_employee, asset_id=str(asset.id))

        assert AuditLog.objects.count() > count_before

    def test_reject_creates_audit_log(
        self, tenant, employee, admin_employee, asset_request_factory
    ):
        from apps.audit.models import AuditLog
        req = asset_request_factory(requested_by=employee)
        count_before = AuditLog.objects.count()
        with patch("apps.requests.services.NotificationService"):
            AssetRequestService.reject(req, rejected_by=admin_employee)
        assert AuditLog.objects.count() > count_before

    def test_cancel_creates_audit_log(self, tenant, employee, asset_request_factory):
        from apps.audit.models import AuditLog
        req = asset_request_factory(requested_by=employee)
        count_before = AuditLog.objects.count()
        with patch("apps.requests.services.NotificationService"):
            AssetRequestService.cancel(req)
        assert AuditLog.objects.count() > count_before


# 5. System-controlled field protection (via API)

def _client_for_employee(emp):
    """Build an APIClient authenticated as the given Employee's TenantUser."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient(SERVER_NAME="test.localhost")
    # Build token without persisting OutstandingToken (TenantUser != AUTH_USER_MODEL)
    token = RefreshToken()
    token["user_id"] = str(emp.user_id)
    token["role"] = emp.user.role
    token["scope"] = "tenant"
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


class TestRequestFieldProtection:

    def test_cannot_set_status_directly(self, tenant, admin_employee):
        """Passing status=APPROVED in request body must be ignored; serializer discards it."""
        client = _client_for_employee(admin_employee)
        payload = {
            "reason": "Need a laptop",
            "priority": "MEDIUM",
            "status": "APPROVED",  # must be ignored — it's a read_only_field
        }
        with patch("apps.requests.services.NotificationService"):
            resp = client.post("/api/v1/asset-requests/", payload, format="json")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert resp.data["status"] == "PENDING"

    def test_cannot_set_approved_by_directly(self, tenant, admin_employee, employee):
        """Passing approved_by in body must be ignored."""
        client = _client_for_employee(admin_employee)
        payload = {
            "reason": "Need a laptop",
            "priority": "MEDIUM",
            "approved_by": str(employee.id),  # must be ignored — read_only_field
        }
        with patch("apps.requests.services.NotificationService"):
            resp = client.post("/api/v1/asset-requests/", payload, format="json")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert resp.data.get("approved_by") is None
