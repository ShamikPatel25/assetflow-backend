"""
Test suite: Soft Delete Side Effects
Covers Fix 9 — soft-deleted employees/assets do not participate in workflows.
"""
import uuid
import pytest
from unittest.mock import patch

from apps.allocations.services import AllocationService
from apps.licenses.services import LicenseService
from apps.base.errors import AFValidationError

pytestmark = pytest.mark.django_db


class TestSoftDeletedEmployeeInAllocations:

    def test_soft_deleted_employee_cannot_receive_allocation(
        self, tenant, asset, employee_factory
    ):
        emp = employee_factory(email="softdel@test.local", is_active=True)
        # Soft-delete
        emp.is_deleted = True
        emp.is_active = False
        emp.save()

        with pytest.raises(AFValidationError) as exc_info:
            with patch("apps.allocations.services.NotificationService"):
                AllocationService.allocate(asset=asset, employee=emp)
        assert "inactive" in str(exc_info.value.detail).lower()

    def test_soft_deleted_employee_cannot_receive_license(
        self, tenant, license_factory, employee_factory
    ):
        lic = license_factory(name="SoftDelLic", total_seats=5)
        emp = employee_factory(email="softdel2@test.local", is_active=True)
        emp.is_deleted = True
        emp.is_active = False
        emp.save()

        with pytest.raises(AFValidationError) as exc_info:
            LicenseService.assign(lic, emp)
        assert "inactive" in str(exc_info.value.detail).lower()

    def test_existing_allocation_history_preserved_after_soft_delete(
        self, tenant, asset, employee, allocation_factory
    ):
        """Soft-deleting employee doesn't remove historical allocation records."""
        from apps.allocations.models import AssetAllocation
        alloc = allocation_factory(asset=asset, employee=employee)

        employee.is_deleted = True
        employee.save()

        # Historical record still queryable via all_objects
        assert AssetAllocation.all_objects.filter(id=alloc.id).exists()


class TestSoftDeletedAssetInAllocations:

    def test_soft_deleted_asset_excluded_from_active_queryset(
        self, tenant, asset_factory, category
    ):
        """
        The SoftDeleteQuerySet manager exposes .active() to exclude deleted records.
        The API layer (BaseViewMixin) calls .active() automatically, so deleted objects
        are invisible through the API. Direct ORM access requires explicit .active().
        """
        from apps.assets.models import Asset
        asset = asset_factory(name="ToDelete", category=category)
        asset.is_deleted = True
        asset.save()

        # .active() excludes deleted objects
        assert not Asset.objects.active().filter(id=asset.id).exists()
        # all_objects includes deleted objects
        assert Asset.all_objects.filter(id=asset.id).exists()

    def test_soft_deleted_employee_excluded_from_active_queryset(
        self, tenant, employee_factory
    ):
        """Deleted employees are excluded by .active() and visible via all_objects."""
        from apps.employees.models import Employee
        emp = employee_factory(email="del_emp@test.local")
        emp.is_deleted = True
        emp.save()

        assert not Employee.objects.active().filter(id=emp.id).exists()
        assert Employee.all_objects.filter(id=emp.id).exists()


class TestSoftDeletedAssetAPIVisibility:

    def test_api_hides_deleted_assets(self, tenant, admin_api_client, asset_factory, category):
        asset = asset_factory(name="VisCheck", category=category)
        asset.is_deleted = True
        asset.save()

        resp = admin_api_client.get("/api/v1/assets/")
        asset_ids = [str(a["id"]) for a in resp.data.get("results", [])]
        assert str(asset.id) not in asset_ids

    def test_api_hides_deleted_employees(self, tenant, admin_api_client, employee_factory):
        emp = employee_factory(email="del_visible@test.local")
        emp.is_deleted = True
        emp.save()

        resp = admin_api_client.get("/api/v1/employees/")
        emp_ids = [str(e["id"]) for e in resp.data.get("results", [])]
        assert str(emp.id) not in emp_ids
