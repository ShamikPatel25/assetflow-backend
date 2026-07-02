"""
Error-contract test suite (base module).

The base module owns the project-wide exception handler
(apps.base.errors.handlers.api_exception_handler). These tests assert the
CONTRACT that every module inherits from it: no matter which app raises the
error, the client always receives the same body shape::

    {"message": "<human sentence>", "code": <int>}

and never Django/DRF's default shape-shifting payloads
(``{"detail": ...}``, ``{"field": [...]}``, ``["msg"]``).
"""
import uuid

import pytest
from rest_framework import status

from apps.base.errors import error_codes as codes

pytestmark = pytest.mark.django_db


def _assert_unified_error(body):
    """Every error body must be exactly {"message": str, "code": int}."""
    assert isinstance(body, dict), f"error body must be a dict, got {type(body)}"
    assert "message" in body, f"missing 'message' key: {body}"
    assert "code" in body, f"missing 'code' key: {body}"
    assert isinstance(body["message"], str) and body["message"], "message must be a non-empty string"
    assert isinstance(body["code"], int), "code must be an int"
    # Django/DRF default keys must NOT leak through.
    assert "detail" not in body, f"raw DRF 'detail' leaked: {body}"
    assert "non_field_errors" not in body, f"raw 'non_field_errors' leaked: {body}"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. UNIFIED ERROR SHAPE ACROSS MODULES
# ═══════════════════════════════════════════════════════════════════════════════

class TestErrorContract:
    """Black-box: the normalized error body is identical across error types."""

    def test_unauthenticated_error_is_unified(self, api_client, tenant):
        """TC-ERR-01: No JWT → 401/403 with {"message","code"}, code=PERMISSION_DENIED."""
        response = api_client.get("/api/v1/assets/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN
        )
        _assert_unified_error(response.data)
        assert response.data["code"] == codes.PERMISSION_DENIED

    def test_invalid_login_returns_clean_message(self, api_client, tenant,
                                                 tenant_user_factory):
        """TC-ERR-02: Bad credentials → 400 with a clear, flat message (no list)."""
        tenant_user_factory(email="real@test.local", password="correct-pass")
        response = api_client.post("/api/v1/auth/login/", data={
            "email": "real@test.local",
            "password": "wrong-pass",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        _assert_unified_error(response.data)
        assert response.data["message"] == "Invalid email or password."
        assert response.data["code"] == codes.DATA_VALIDATION_FAILED

    def test_not_found_is_unified(self, admin_api_client):
        """TC-ERR-03: Fetching a non-existent asset → 404 with a readable message."""
        response = admin_api_client.get(f"/api/v1/assets/{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        _assert_unified_error(response.data)
        assert response.data["message"].lower().endswith("not found.")
        assert response.data["code"] == codes.RECORD_NOT_FOUND

    def test_malformed_uuid_is_unified_not_500(self, admin_api_client):
        """TC-ERR-04: A garbage id must yield a clean 404, never a 500 crash."""
        response = admin_api_client.get("/api/v1/assets/not-a-real-uuid/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        _assert_unified_error(response.data)

    def test_permission_denied_on_write_is_unified(self, employee_api_client):
        """TC-ERR-05: Employee writing to an admin-only endpoint → 403 unified body."""
        response = employee_api_client.post("/api/v1/asset-categories/", data={
            "name": "Hacked Category",
            "code": "HACK",
            "category_type": "HARDWARE",
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN
        _assert_unified_error(response.data)
        assert response.data["code"] == codes.PERMISSION_DENIED

    def test_validation_error_is_flattened_to_sentence(self, admin_api_client):
        """TC-ERR-06: Missing required fields → 400 with a flat string message,
        never a {field: [..]} dict."""
        response = admin_api_client.post("/api/v1/asset-categories/", data={})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        _assert_unified_error(response.data)
        assert response.data["code"] in (
            codes.DATA_VALIDATION_FAILED, codes.RECORD_ALREADY_EXIST
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CONSISTENCY: SAME ERROR TYPE → SAME SHAPE ACROSS DIFFERENT MODULES
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrossModuleConsistency:
    """The same failure mode must look identical no matter which module serves it."""

    NOT_FOUND_ENDPOINTS = [
        "/api/v1/assets/{id}/",
        "/api/v1/asset-categories/{id}/",
        "/api/v1/employees/{id}/",
        "/api/v1/allocations/{id}/",
        "/api/v1/incidents/{id}/",
        "/api/v1/licenses/{id}/",
    ]

    def test_not_found_shape_is_identical_everywhere(self, admin_api_client):
        """TC-XM-01: 404 from every module has the same keys + code."""
        for template in self.NOT_FOUND_ENDPOINTS:
            url = template.format(id=uuid.uuid4())
            response = admin_api_client.get(url)
            assert response.status_code == status.HTTP_404_NOT_FOUND, url
            _assert_unified_error(response.data)
            assert response.data["code"] == codes.RECORD_NOT_FOUND, url

    def test_unauthenticated_shape_is_identical_everywhere(self, api_client, tenant):
        """TC-XM-02: 401/403 from every module has the same keys + code."""
        for template in self.NOT_FOUND_ENDPOINTS:
            url = template.format(id=uuid.uuid4())
            response = api_client.get(url)
            assert response.status_code in (
                status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN
            ), url
            _assert_unified_error(response.data)
            assert response.data["code"] == codes.PERMISSION_DENIED, url


# ═══════════════════════════════════════════════════════════════════════════════
# 3. REAL BUSINESS LIFECYCLE (service layer, valid data + invalid data)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAssetAllocationLifecycle:
    """White-box integration: the real allocate → return → re-use lifecycle,
    proving valid data flows through and invalid data raises the RIGHT base code."""

    def test_full_allocate_and_return_cycle(self, asset, employee, hr_employee):
        """TC-LIFE-01: Allocate an available asset, then return it — asset ends
        up AVAILABLE and reusable, allocation state tracked at each step."""
        from apps.allocations.services import AllocationService
        from apps.assets.models import Asset
        from apps.allocations.models import AssetAllocation

        assert asset.status == Asset.Status.AVAILABLE

        # Valid: allocate to an active employee.
        allocation = AllocationService.allocate(
            asset=asset, employee=employee, assigned_by=hr_employee
        )
        asset.refresh_from_db()
        assert asset.status == Asset.Status.ALLOCATED
        assert asset.current_owner == employee
        assert allocation.status == AssetAllocation.Status.ACTIVE

        # Valid: return it — asset becomes AVAILABLE again.
        AllocationService.return_asset(allocation, return_condition="GOOD")
        asset.refresh_from_db()
        allocation.refresh_from_db()
        assert asset.status == Asset.Status.AVAILABLE
        assert asset.current_owner is None
        assert allocation.status == AssetAllocation.Status.RETURNED

    def test_cannot_allocate_already_allocated_asset(self, asset, employee, hr_employee):
        """TC-LIFE-02: Double-allocation → INVALID_STATUS_TRANSITION code."""
        from apps.allocations.services import AllocationService
        from apps.base.errors import AFValidationError

        AllocationService.allocate(asset=asset, employee=employee)
        with pytest.raises(AFValidationError) as exc:
            AllocationService.allocate(asset=asset, employee=hr_employee)
        assert exc.value.detail["code"] == codes.INVALID_STATUS_TRANSITION

    def test_cannot_allocate_to_inactive_employee(self, asset, employee):
        """TC-LIFE-03: Allocating to an exited employee → DATA_VALIDATION_FAILED."""
        from apps.allocations.services import AllocationService
        from apps.base.errors import AFValidationError

        employee.is_active = False
        employee.save(update_fields=["is_active"])
        with pytest.raises(AFValidationError) as exc:
            AllocationService.allocate(asset=asset, employee=employee)
        assert exc.value.detail["code"] == codes.DATA_VALIDATION_FAILED

    def test_cannot_return_already_returned_allocation(self, asset, employee):
        """TC-LIFE-04: Returning twice → INVALID_STATUS_TRANSITION."""
        from apps.allocations.services import AllocationService
        from apps.base.errors import AFValidationError

        allocation = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.return_asset(allocation)
        with pytest.raises(AFValidationError) as exc:
            AllocationService.return_asset(allocation)
        assert exc.value.detail["code"] == codes.INVALID_STATUS_TRANSITION


class TestLicenseSeatLifecycle:
    """White-box integration: license seat assignment respects capacity."""

    def test_assign_and_revoke_seat(self, license_factory, employee):
        """TC-LIFE-05: Assign a seat then revoke it (valid happy path)."""
        from apps.licenses.services import LicenseService
        from apps.licenses.models import LicenseAssignment

        lic = license_factory(total_seats=2)
        assignment = LicenseService.assign(lic, employee)
        assert assignment.status == LicenseAssignment.Status.ACTIVE

        LicenseService.revoke(assignment)
        assignment.refresh_from_db()
        assert assignment.status == LicenseAssignment.Status.REVOKED

    def test_cannot_exceed_seat_capacity(self, license_factory, employee_factory):
        """TC-LIFE-06: Assigning past total_seats → DATA_VALIDATION_FAILED."""
        from apps.licenses.services import LicenseService
        from apps.base.errors import AFValidationError

        lic = license_factory(total_seats=1)
        LicenseService.assign(lic, employee_factory(first_name="Seat1"))
        with pytest.raises(AFValidationError) as exc:
            LicenseService.assign(lic, employee_factory(first_name="Seat2"))
        assert exc.value.detail["code"] == codes.DATA_VALIDATION_FAILED


# ═══════════════════════════════════════════════════════════════════════════════
# 4. REGRESSIONS (bugs found during the real-data walkthrough)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationRegressions:
    """Incidents may have a null asset — notifications must not crash on it."""

    def test_incident_reported_without_asset_does_not_crash(
        self, incident_factory, hr_user
    ):
        """TC-REG-01: Reporting an incident with no linked asset must notify
        HR without raising AttributeError (was a 500 in production)."""
        from apps.notifications.services import NotificationService
        from apps.notifications.models import Notification

        incident = incident_factory(asset=None)
        NotificationService.notify_incident_reported(incident)  # must not raise
        note = Notification.objects.filter(recipient=hr_user).first()
        assert note is not None
        assert note.payload["asset_id"] is None

    def test_incident_updated_without_asset_does_not_crash(self, incident_factory):
        """TC-REG-02: Resolving/closing an assetless incident must not crash."""
        from apps.notifications.services import NotificationService
        from apps.notifications.models import Notification

        incident = incident_factory(asset=None, status="RESOLVED")
        NotificationService.notify_incident_updated(incident)  # must not raise
        recipient = incident.reported_by.user
        note = Notification.objects.filter(recipient=recipient).first()
        assert note is not None
        assert note.payload["asset_id"] is None
