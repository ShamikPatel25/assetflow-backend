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


# 1. UNIFIED ERROR SHAPE ACROSS MODULES

class TestErrorContract:
    """the normalized error body is identical across error types."""

    def test_unauthenticated_error_is_unified(self, api_client, tenant):
        """No JWT → 401/403 with {"message","code"}, code=PERMISSION_DENIED."""
        response = api_client.get("/api/v1/assets/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN
        )
        _assert_unified_error(response.data)
        assert response.data["code"] == codes.PERMISSION_DENIED

    def test_invalid_login_returns_clean_message(self, api_client, tenant,
                                                 tenant_user_factory):
        """Bad credentials → 400 with a clear, flat message (no list)."""
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
        """Fetching a non-existent asset → 404 with a readable message."""
        response = admin_api_client.get(f"/api/v1/assets/{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        _assert_unified_error(response.data)
        assert response.data["message"].lower().endswith("not found.")
        assert response.data["code"] == codes.RECORD_NOT_FOUND

    def test_malformed_uuid_is_unified_not_500(self, admin_api_client):
        """A garbage id must yield a clean 404, never a 500 crash."""
        response = admin_api_client.get("/api/v1/assets/not-a-real-uuid/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        _assert_unified_error(response.data)

    def test_permission_denied_on_write_is_unified(self, employee_api_client):
        """Employee writing to an admin-only endpoint → 403 unified body."""
        response = employee_api_client.post("/api/v1/asset-categories/", data={
            "name": "Hacked Category",
            "code": "HACK",
            "category_type": "HARDWARE",
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN
        _assert_unified_error(response.data)
        assert response.data["code"] == codes.PERMISSION_DENIED

    def test_validation_error_is_flattened_to_sentence(self, admin_api_client):
        """Missing required fields → 400 with a flat string message,
        never a {field: [..]} dict."""
        response = admin_api_client.post("/api/v1/asset-categories/", data={})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        _assert_unified_error(response.data)
        assert response.data["code"] in (
            codes.DATA_VALIDATION_FAILED, codes.RECORD_ALREADY_EXIST
        )


# 2. CONSISTENCY: SAME ERROR TYPE → SAME SHAPE ACROSS DIFFERENT MODULES

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
        """404 from every module has the same keys + code."""
        for template in self.NOT_FOUND_ENDPOINTS:
            url = template.format(id=uuid.uuid4())
            response = admin_api_client.get(url)
            assert response.status_code == status.HTTP_404_NOT_FOUND, url
            _assert_unified_error(response.data)
            assert response.data["code"] == codes.RECORD_NOT_FOUND, url

    def test_unauthenticated_shape_is_identical_everywhere(self, api_client, tenant):
        """401/403 from every module has the same keys + code."""
        for template in self.NOT_FOUND_ENDPOINTS:
            url = template.format(id=uuid.uuid4())
            response = api_client.get(url)
            assert response.status_code in (
                status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN
            ), url
            _assert_unified_error(response.data)
            assert response.data["code"] == codes.PERMISSION_DENIED, url


# 3. REAL BUSINESS LIFECYCLE (service layer, valid data + invalid data)

class TestAssetAllocationLifecycle:
    """Integration: the real allocate → return → re-use lifecycle,
    proving valid data flows through and invalid data raises the RIGHT base code."""

    def test_full_allocate_and_return_cycle(self, asset, employee, hr_employee):
        """Allocate an available asset, then return it — asset ends
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
        """Double-allocation → INVALID_STATUS_TRANSITION code."""
        from apps.allocations.services import AllocationService
        from apps.base.errors import AFValidationError

        AllocationService.allocate(asset=asset, employee=employee)
        with pytest.raises(AFValidationError) as exc:
            AllocationService.allocate(asset=asset, employee=hr_employee)
        assert exc.value.detail["code"] == codes.INVALID_STATUS_TRANSITION

    def test_cannot_allocate_to_inactive_employee(self, asset, employee):
        """Allocating to an exited employee → DATA_VALIDATION_FAILED."""
        from apps.allocations.services import AllocationService
        from apps.base.errors import AFValidationError

        employee.is_active = False
        employee.save(update_fields=["is_active"])
        with pytest.raises(AFValidationError) as exc:
            AllocationService.allocate(asset=asset, employee=employee)
        assert exc.value.detail["code"] == codes.DATA_VALIDATION_FAILED

    def test_cannot_return_already_returned_allocation(self, asset, employee):
        """Returning twice → INVALID_STATUS_TRANSITION."""
        from apps.allocations.services import AllocationService
        from apps.base.errors import AFValidationError

        allocation = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.return_asset(allocation)
        with pytest.raises(AFValidationError) as exc:
            AllocationService.return_asset(allocation)
        assert exc.value.detail["code"] == codes.INVALID_STATUS_TRANSITION


class TestLicenseSeatLifecycle:
    """Integration: license seat assignment respects capacity."""

    def test_assign_and_revoke_seat(self, license_factory, employee):
        """Assign a seat then revoke it (valid happy path)."""
        from apps.licenses.services import LicenseService
        from apps.licenses.models import LicenseAssignment

        lic = license_factory(total_seats=2)
        assignment = LicenseService.assign(lic, employee)
        assert assignment.status == LicenseAssignment.Status.ACTIVE

        LicenseService.revoke(assignment)
        assignment.refresh_from_db()
        assert assignment.status == LicenseAssignment.Status.REVOKED

    def test_cannot_exceed_seat_capacity(self, license_factory, employee_factory):
        """Assigning past total_seats → DATA_VALIDATION_FAILED."""
        from apps.licenses.services import LicenseService
        from apps.base.errors import AFValidationError

        lic = license_factory(total_seats=1)
        LicenseService.assign(lic, employee_factory(first_name="Seat1"))
        with pytest.raises(AFValidationError) as exc:
            LicenseService.assign(lic, employee_factory(first_name="Seat2"))
        assert exc.value.detail["code"] == codes.DATA_VALIDATION_FAILED


# 4. REGRESSIONS (bugs found during the real-data walkthrough)

class TestNotificationRegressions:
    """Incidents may have a null asset — notifications must not crash on it."""

    def test_incident_reported_without_asset_does_not_crash(
        self, incident_factory, hr_user
    ):
        """Reporting an incident with no linked asset must notify
        HR without raising AttributeError (was a 500 in production)."""
        from apps.notifications.services import NotificationService
        from apps.notifications.models import Notification

        incident = incident_factory(asset=None)
        NotificationService.notify_incident_reported(incident)  # must not raise
        note = Notification.objects.filter(recipient=hr_user).first()
        assert note is not None
        assert note.payload["asset_id"] is None

    def test_incident_updated_without_asset_does_not_crash(self, incident_factory):
        """Resolving/closing an assetless incident must not crash."""
        from apps.notifications.services import NotificationService
        from apps.notifications.models import Notification

        incident = incident_factory(asset=None, status="RESOLVED")
        NotificationService.notify_incident_updated(incident)  # must not raise
        recipient = incident.reported_by.user
        note = Notification.objects.filter(recipient=recipient).first()
        assert note is not None
        assert note.payload["asset_id"] is None


# 5. BASE SERIALIZER MIXINS (field filtering, audit display, unique_together)

class TestBaseSerializerFieldFiltering:
    """BaseModelSerializer field filtering + audit-field display, exercised
    through the concrete AssetSerializer."""

    def _asset(self, asset_factory, category):
        return asset_factory(name="Filtered Laptop", category=category)

    def test_allowed_fields_restricts_output(self, asset_factory, category, tenant):
        """allowed_fields drops every declared field except id + the requested
        ones. (The concrete AssetSerializer.to_representation re-injects a couple
        of computed keys, so we assert the declared-field pruning, not equality.)"""
        from apps.assets.serializers import AssetSerializer

        asset = self._asset(asset_factory, category)
        data = AssetSerializer(asset, allowed_fields=["name", "status"]).data
        assert "id" in data and "name" in data and "status" in data
        # Fields that were pruned by allowed_fields and NOT re-added downstream.
        for pruned in ("brand", "serial_number", "purchase_cost", "condition"):
            assert pruned not in data

    def test_remove_fields_drops_named_fields(self, asset_factory, category, tenant):
        """remove_fields pops the named fields but keeps the rest."""
        from apps.assets.serializers import AssetSerializer

        asset = self._asset(asset_factory, category)
        data = AssetSerializer(asset, remove_fields=["currency", "brand"]).data
        assert "currency" not in data
        assert "brand" not in data
        assert "name" in data

    def test_remove_audit_strips_audit_fields(self, asset_factory, category, tenant):
        """remove_audit=True drops created_at/updated_at/created_by/... but keeps id."""
        from apps.assets.serializers import AssetSerializer

        asset = self._asset(asset_factory, category)
        data = AssetSerializer(asset, remove_audit=True).data
        assert "id" in data
        for f in ("created_at", "updated_at", "created_by", "updated_by",
                  "is_active", "is_deleted"):
            assert f not in data

    def test_created_by_rendered_as_display(
        self, asset_factory, category, tenant, hr_user
    ):
        """created_by is replaced by a human-readable display via get_user_display."""
        from apps.assets.serializers import AssetSerializer

        asset = self._asset(asset_factory, category)
        asset.created_by = hr_user
        asset.save(update_fields=["created_by"])
        data = AssetSerializer(asset).data
        # hr_user has no name → falls back to email.
        assert data["created_by"] == hr_user.email

    def test_is_fake_false_with_real_view_context(self):
        """is_fake reflects the view's is_fake_view flag (False for a real view)."""
        from apps.base.serializers import BaseSerializer

        class _View:
            is_fake_view = False

        ser = BaseSerializer(context={"view": _View()})
        assert ser.is_fake is False

    def test_is_fake_true_without_view(self):
        """No view in context → treated as a fake (schema) request."""
        from apps.base.serializers import BaseSerializer

        ser = BaseSerializer(context={})
        assert ser.is_fake is True

    def test_request_property_returns_context_request(self):
        from apps.base.serializers import BaseSerializer

        sentinel = object()
        ser = BaseSerializer(context={"request": sentinel})
        assert ser.request is sentinel


class TestBaseSerializerAuditDisplayResilience:
    """to_representation must not crash if the audit-display lookup errors."""

    def test_display_error_is_swallowed(self, asset_factory, category, hr_user, tenant):
        from unittest.mock import patch
        from apps.assets.serializers import AssetSerializer

        asset = asset_factory(name="Resilient", category=category)
        asset.created_by = hr_user
        asset.save(update_fields=["created_by"])
        with patch(
            "apps.base.serializers.get_user_display", side_effect=Exception("boom")
        ):
            data = AssetSerializer(asset).data  # must not raise
        assert "created_by" in data


class TestFlexibleDateField:
    """FlexibleDateField coerces empty strings to None."""

    def test_empty_string_becomes_none(self):
        from apps.base.serializers import FlexibleDateField
        assert FlexibleDateField().to_internal_value("") is None

    def test_valid_date_still_parses(self):
        import datetime
        from apps.base.serializers import FlexibleDateField
        assert FlexibleDateField().to_internal_value("2025-01-15") == datetime.date(2025, 1, 15)


class TestBaseModelSerializerUniqueTogether:
    """BaseModelSerializer.is_valid runs unique_together validation and raises
    a flattened AFValidationError. AssetCategory has no unique_together, so we
    define a tiny serializer bound to a model that does."""

    def _make_serializer(self):
        from apps.base.serializers import BaseModelSerializer
        from apps.assets.models import AssetCategory
        from rest_framework import serializers as drf_serializers

        class _CatSerializer(BaseModelSerializer):
            # Give this serializer a (name, code) unique_together contract even
            # though the model doesn't declare one, to exercise the code path.
            name = drf_serializers.CharField()
            code = drf_serializers.CharField()

            class Meta:
                model = AssetCategory
                fields = ("id", "name", "code")

        return _CatSerializer

    def test_valid_data_passes(self, tenant):
        Ser = self._make_serializer()
        ser = Ser(data={"name": "Cameras", "code": "CAM"})
        assert ser.is_valid() is True

    def test_missing_required_field_raises_af_validation_error(self, tenant):
        from apps.base.errors import AFValidationError
        Ser = self._make_serializer()
        ser = Ser(data={"code": "CAM"})  # missing name
        with pytest.raises(AFValidationError):
            ser.is_valid(raise_exception=True)

    def test_unique_together_violation_raises_already_exist(
        self, tenant, category_factory
    ):
        """When Meta declares unique_together and a matching row exists,
        is_valid raises AFValidationError(RECORD_ALREADY_EXIST)."""
        from apps.base.serializers import BaseModelSerializer
        from apps.assets.models import AssetCategory
        from apps.base.errors import AFValidationError
        from apps.base.errors import error_codes as ec
        from rest_framework import serializers as drf_serializers

        existing = category_factory(name="Printers", code="PRN")

        class _UniqueSerializer(BaseModelSerializer):
            name = drf_serializers.CharField()

            class Meta:
                model = AssetCategory
                fields = ("id", "name")

        # Inject an artificial unique_together on the model _meta for this test.
        model_meta = AssetCategory._meta
        original = getattr(model_meta, "unique_together", ())
        model_meta.unique_together = (("name",),)
        try:
            ser = _UniqueSerializer(data={"name": existing.name})
            with pytest.raises(AFValidationError) as exc:
                ser.is_valid(raise_exception=True)
            assert exc.value.detail["code"] == ec.RECORD_ALREADY_EXIST, str(exc.value.detail)
        finally:
            model_meta.unique_together = original


# 6. BASE VIEWSET BEHAVIOUR (soft-delete, already-deleted, audit hooks)

class TestCRUDViewSetDestroy:
    """CRUDViewSet.destroy soft-deletes, reports already-deleted, and 404s."""

    URL = "/api/v1/asset-categories/"

    def test_destroy_soft_deletes(self, admin_api_client, category_factory, tenant):
        cat = category_factory(name="Deletable", code="DEL")
        response = admin_api_client.delete(f"{self.URL}{cat.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert "deleted successfully" in response.data["message"].lower()
        cat.refresh_from_db()
        assert cat.is_deleted is True

    def test_destroy_already_deleted_returns_400(
        self, admin_api_client, category_factory, tenant
    ):
        """Deleting an already soft-deleted row → 400 'already deleted'."""
        cat = category_factory(name="Gone", code="GONE")
        cat.is_deleted = True
        cat.save(update_fields=["is_deleted"])
        response = admin_api_client.delete(f"{self.URL}{cat.id}/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already deleted" in response.data["message"].lower()

    def test_destroy_missing_returns_404(self, admin_api_client, tenant):
        response = admin_api_client.delete(f"{self.URL}{uuid.uuid4()}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.data["message"].lower()

    def test_destroy_malformed_id_returns_404(self, admin_api_client, tenant):
        """A non-uuid pk on destroy is handled as not-found, not a 500."""
        response = admin_api_client.delete(f"{self.URL}not-a-uuid/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestBaseViewSetAuditHooks:
    """perform_create / perform_update stamp audit fields and log actions."""

    URL = "/api/v1/asset-categories/"

    def test_create_stamps_created_by_and_logs(
        self, admin_api_client, org_admin_user, tenant, mock_audit_log
    ):
        response = admin_api_client.post(
            self.URL,
            data={"name": "Audited", "code": "AUD", "category_type": "HARDWARE"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        from apps.assets.models import AssetCategory
        cat = AssetCategory.objects.get(code="AUD")
        assert cat.created_by_id == org_admin_user.id
        assert mock_audit_log.called

    def test_update_stamps_updated_by_and_logs(
        self, admin_api_client, org_admin_user, category_factory, tenant, mock_audit_log
    ):
        cat = category_factory(name="Old", code="UPD")
        response = admin_api_client.put(
            f"{self.URL}{cat.id}/",
            data={"name": "New Name", "code": "UPD", "category_type": "HARDWARE"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        cat.refresh_from_db()
        assert cat.name == "New Name"
        assert cat.updated_by_id == org_admin_user.id
        assert mock_audit_log.called


class TestBaseViewSetUnhandledResponse:
    """unhandled_response formats 500s and re-raises Http404."""

    def test_generic_exception_becomes_500_body(self):
        from apps.base.views import BaseViewSet

        vs = BaseViewSet()
        vs.kwargs = {}
        resp = vs.unhandled_response(RuntimeError("boom"), function_name="thing")
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "message" in resp.data

    def test_http404_is_reraised(self):
        from django.http import Http404
        from apps.base.views import BaseViewSet

        vs = BaseViewSet()
        vs.kwargs = {"pk": "abc"}
        with pytest.raises(Http404):
            vs.unhandled_response(Http404("nope"), function_name="thing")


# 7. BASE UTILITIES — functions, soft-delete queryset

class TestBaseFunctions:
    def test_extract_nested_fields_splits_dunder(self):
        from apps.base.functions import extract_nested_fields
        assert extract_nested_fields(["name", "dept__name", "dept__code"]) == {
            "name": [], "dept": ["name", "code"],
        }


class TestSoftDeleteQuerySet:
    def test_deleted_returns_only_soft_deleted(self, category_factory, tenant):
        from apps.assets.models import AssetCategory
        live = category_factory(name="Live", code="LIVEX")
        gone = category_factory(name="Gone", code="GONEX")
        gone.is_deleted = True
        gone.save(update_fields=["is_deleted"])
        deleted_ids = set(AssetCategory.objects.deleted().values_list("id", flat=True))
        assert gone.id in deleted_ids
        assert live.id not in deleted_ids


# 8. BASE PERMISSIONS — anonymous denial branches

class TestBasePermissionsAnonymous:
    """The `not authenticated → False` guard in each mixed permission."""

    def _req(self, method="POST"):
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request
        from django.contrib.auth.models import AnonymousUser
        req = Request(getattr(APIRequestFactory(), method.lower())("/"))
        req.user = AnonymousUser()
        return req

    def test_org_admin_or_hr_denies_anonymous(self):
        from apps.base.permissions import IsOrgAdminOrHR
        assert IsOrgAdminOrHR().has_permission(self._req(), None) is False

    def test_org_admin_or_readonly_denies_anonymous(self):
        from apps.base.permissions import IsOrgAdminOrReadOnly
        assert IsOrgAdminOrReadOnly().has_permission(self._req(), None) is False

    def test_org_admin_or_hr_or_readonly_denies_anonymous(self):
        from apps.base.permissions import IsOrgAdminOrHROrReadOnly
        assert IsOrgAdminOrHROrReadOnly().has_permission(self._req(), None) is False


# 9. CUSTOM ORDERING FILTER (wired globally in DEFAULT_FILTER_BACKENDS)

class TestCustomOrderingFilterAPI:
    url = "/api/v1/assets/"

    def test_ordering_by_valid_field(self, hr_api_client, asset):
        assert hr_api_client.get(f"{self.url}?ordering=name").status_code == status.HTTP_200_OK

    def test_ordering_descending(self, hr_api_client, asset):
        assert hr_api_client.get(f"{self.url}?ordering=-name").status_code == status.HTTP_200_OK

    def test_ordering_unknown_field_falls_back_to_default(self, hr_api_client, asset):
        assert hr_api_client.get(f"{self.url}?ordering=bogusfield").status_code == status.HTTP_200_OK


# 10. NESTED FIELD-FILTERING (BaseSerializer allowed/remove with dotted paths)

class TestNestedFieldFiltering:
    """The nested branches of _apply_allowed_fields / _apply_removed_fields."""

    def _serializer(self):
        from apps.base.serializers import BaseModelSerializer
        from apps.assets.models import Asset, AssetCategory

        class CatSer(BaseModelSerializer):
            class Meta:
                model = AssetCategory
                fields = ("id", "name", "code")

        class AssetSer(BaseModelSerializer):
            category = CatSer()

            class Meta:
                model = Asset
                fields = ("id", "name", "category")

        return AssetSer

    def test_allowed_fields_prunes_nested(self, asset_factory, category, tenant):
        Ser = self._serializer()
        asset = asset_factory(name="N", category=category)
        data = Ser(asset, allowed_fields=["name", "category__name"]).data
        assert "name" in data
        assert "name" in data["category"]
        assert "code" not in data["category"]

    def test_remove_fields_prunes_nested(self, asset_factory, category, tenant):
        Ser = self._serializer()
        asset = asset_factory(name="N", category=category)
        data = Ser(asset, remove_fields=["category__code"]).data
        assert "code" not in data["category"]
        assert "name" in data["category"]

    def test_remove_fields_ignores_unknown_parent(self, asset_factory, category, tenant):
        """A nested remove path whose parent field doesn't exist is skipped."""
        Ser = self._serializer()
        asset = asset_factory(name="N", category=category)
        data = Ser(asset, remove_fields=["ghost__child"]).data
        assert "name" in data  # nothing blew up; unknown parent ignored


# 11. BASE VIEWSET helpers — is_fake_view + get_serializer(serializer_class=)

class TestBaseViewSetHelpers:
    def test_is_fake_view_defaults_false(self):
        from apps.base.views import BaseViewSet
        assert BaseViewSet().is_fake_view is False

    def test_get_serializer_honours_serializer_class_kwarg(self):
        from apps.base.views import BaseViewSet
        from apps.assets.serializers import AssetCategorySerializer
        vs = BaseViewSet()
        vs.request = None
        vs.format_kwarg = None
        ser = vs.get_serializer(serializer_class=AssetCategorySerializer)
        assert isinstance(ser, AssetCategorySerializer)


# 12. _check_unique_together — the real fallback path (not DB-unique shadowed)

class TestCheckUniqueTogetherFallback:
    """AssetCategory.name/category_type are individually non-unique, so the
    combined check runs through _check_unique_together instead of a DB validator."""

    def _combo_serializer(self):
        from apps.base.serializers import BaseModelSerializer
        from apps.assets.models import AssetCategory
        from rest_framework import serializers as drf

        class ComboSer(BaseModelSerializer):
            name = drf.CharField()
            category_type = drf.CharField()

            class Meta:
                model = AssetCategory
                fields = ("id", "name", "category_type")
                # Disable DRF's auto UniqueTogetherValidator so the custom
                # _check_unique_together fallback is the code path under test.
                validators = []

        return ComboSer

    def test_combined_duplicate_raises_already_exist(self, category_factory, tenant):
        from apps.assets.models import AssetCategory
        from apps.base.errors import AFValidationError, error_codes as ec

        category_factory(name="ComboX", code="CMBX", category_type="HARDWARE")
        meta = AssetCategory._meta
        original = meta.unique_together
        meta.unique_together = (("name", "category_type"),)
        try:
            ser = self._combo_serializer()(data={
                "name": "ComboX", "category_type": "HARDWARE",
            })
            with pytest.raises(AFValidationError) as exc:
                ser.is_valid(raise_exception=True)
            assert exc.value.detail["code"] == ec.RECORD_ALREADY_EXIST
        finally:
            meta.unique_together = original

    def test_no_existing_combo_is_valid(self, tenant):
        from apps.assets.models import AssetCategory

        meta = AssetCategory._meta
        original = meta.unique_together
        meta.unique_together = (("name", "category_type"),)
        try:
            ser = self._combo_serializer()(data={
                "name": "FreshName", "category_type": "SOFTWARE",
            })
            assert ser.is_valid() is True  # ObjectDoesNotExist branch
        finally:
            meta.unique_together = original

    def test_incomplete_unique_set_is_skipped(self, tenant):
        from apps.base.serializers import BaseModelSerializer
        from apps.assets.models import AssetCategory
        from rest_framework import serializers as drf

        class PartialSer(BaseModelSerializer):
            name = drf.CharField()

            class Meta:
                model = AssetCategory
                fields = ("id", "name")

        meta = AssetCategory._meta
        original = meta.unique_together
        meta.unique_together = (("name", "code"),)  # 'code' not in the payload
        try:
            ser = PartialSer(data={"name": "SoloName"})
            assert ser.is_valid() is True  # len(lookup) != len(field_set) → continue
        finally:
            meta.unique_together = original


# ===========================================================================
# Platform glue: authentication / pagination / permissions / error internals
#
# These exercise the small defensive branches the API-level tests don't reach
# (bad tokens, inactive users, schema-doc params, non-DRF exceptions).
# ===========================================================================

class TestTenantJWTAuthentication:
    """TenantJWTAuthentication.get_user() resolves users per active schema."""

    def _auth(self):
        from apps.base.authentication import TenantJWTAuthentication
        return TenantJWTAuthentication()

    def _claim(self):
        from rest_framework_simplejwt.settings import api_settings
        return api_settings.USER_ID_CLAIM

    def test_token_without_user_claim_is_invalid(self, tenant):
        from rest_framework_simplejwt.exceptions import InvalidToken
        with pytest.raises(InvalidToken):
            self._auth().get_user({})  # no user_id claim

    def test_unknown_user_in_tenant_is_rejected(self, tenant):
        from rest_framework_simplejwt.exceptions import AuthenticationFailed
        with pytest.raises(AuthenticationFailed):
            self._auth().get_user({self._claim(): str(uuid.uuid4())})

    def test_inactive_user_is_rejected(self, tenant, tenant_user_factory):
        from rest_framework_simplejwt.exceptions import AuthenticationFailed
        user = tenant_user_factory(is_active=False)
        with pytest.raises(AuthenticationFailed):
            self._auth().get_user({self._claim(): str(user.id)})

    def test_active_user_is_returned(self, tenant, tenant_user_factory):
        user = tenant_user_factory(is_active=True)
        resolved = self._auth().get_user({self._claim(): str(user.id)})
        assert resolved.id == user.id

    def test_public_schema_uses_accounts_user_model(self, public_tenant):
        """On the public schema the resolver targets the accounts.User table."""
        from rest_framework_simplejwt.exceptions import AuthenticationFailed
        # No such platform user -> DoesNotExist -> AuthenticationFailed,
        # but only after taking the public-schema (UserModel = User) branch.
        with pytest.raises(AuthenticationFailed):
            self._auth().get_user({self._claim(): str(uuid.uuid4())})


class TestTenantJWTAuthenticationScheme:
    def test_security_definition_is_bearer_jwt(self):
        from apps.base.authentication import TenantJWTAuthenticationScheme
        scheme = TenantJWTAuthenticationScheme(target=None)
        assert scheme.get_security_definition(auto_schema=None) == {
            "type": "http", "scheme": "bearer", "bearerFormat": "JWT",
        }


class TestCustomPagination:
    def _paginator(self):
        from apps.base.pagination import CustomPageNumberPagination
        return CustomPageNumberPagination()

    def test_pagination_disabled_returns_none(self):
        from types import SimpleNamespace
        request = SimpleNamespace(query_params={"pagination": "0"})
        assert self._paginator().paginate_queryset([1, 2, 3], request) is None

    def test_schema_exposes_pagination_toggle_param(self):
        params = self._paginator().get_schema_operation_parameters(view=None)
        names = {p["name"] for p in params}
        assert "pagination" in names


class TestPermissionClasses:
    """Direct checks on the permission classes not wired into the covered views."""

    def _req(self, *, authenticated=True, method="GET", **user_attrs):
        from types import SimpleNamespace
        user = SimpleNamespace(is_authenticated=authenticated, **user_attrs)
        return SimpleNamespace(user=user, method=method)

    def test_is_super_admin(self):
        from apps.base.permissions import IsSuperAdmin
        perm = IsSuperAdmin()
        assert perm.has_permission(self._req(is_superuser=True), None) is True
        assert perm.has_permission(self._req(is_superuser=False), None) is False
        assert perm.has_permission(self._req(authenticated=False, is_superuser=True), None) is False

    def test_is_org_admin_or_readonly(self):
        from apps.base.permissions import IsOrgAdminOrReadOnly
        perm = IsOrgAdminOrReadOnly()
        # Safe method -> always allowed
        assert perm.has_permission(self._req(method="GET", role="EMPLOYEE"), None) is True
        # Write -> only ORGANIZATION_ADMIN
        assert perm.has_permission(self._req(method="POST", role="ORGANIZATION_ADMIN"), None) is True
        assert perm.has_permission(self._req(method="POST", role="HR_MANAGER"), None) is False
        # Unauthenticated -> denied
        assert perm.has_permission(self._req(authenticated=False, method="GET"), None) is False


class TestErrorHelperInternals:
    """Low-level helpers behind the unified error contract."""

    def test_flatten_field_error(self):
        from apps.base.errors.handlers import _flatten_message
        assert _flatten_message({"email": ["is required"]}) == "email - is required"

    def test_flatten_empty_dict_falls_back(self):
        from apps.base.errors.handlers import _flatten_message, error_default_message
        assert _flatten_message({}) == error_default_message()

    def test_flatten_empty_list_falls_back(self):
        from apps.base.errors.handlers import _flatten_message, error_default_message
        assert _flatten_message([]) == error_default_message()

    def test_handler_passes_through_non_drf_exception(self):
        from apps.base.errors.handlers import api_exception_handler
        # A plain Python exception isn't DRF-handled -> handler returns None
        assert api_exception_handler(ValueError("boom"), {}) is None

    def test_validation_error_without_app_code_logs_and_defaults(self):
        from apps.base.errors import AFValidationError
        exc = AFValidationError("something broke")  # no app_code
        assert exc.detail["message"] == "something broke"

    def test_message_helper_builds_body(self):
        from apps.base.errors.messages import message
        body = message(codes.RECORD_NOT_FOUND)
        assert body["code"] == codes.RECORD_NOT_FOUND
        assert isinstance(body["message"], str) and body["message"]
