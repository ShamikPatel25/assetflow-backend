"""
Test suite: Asset Allocation
Covers Fix 2+5 — race conditions, asset condition/status guardrails.
"""
import uuid
import pytest
from unittest.mock import patch
from django.db import connection
from rest_framework import status

from apps.allocations.services import AllocationService
from apps.base.errors import AFValidationError

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# 1. Duplicate / double allocation
# ---------------------------------------------------------------------------

class TestAllocationDuplicate:

    def test_duplicate_allocation_is_blocked(self, tenant, asset, employee, mock_notification_service):
        """Same asset cannot be allocated to two employees at the same time."""
        from apps.employees.models import TenantUser, Employee as Emp
        user2 = TenantUser(email="emp2@test.local", role="EMPLOYEE", is_active=True)
        user2.set_password("x")
        user2.save()
        emp2 = Emp.objects.create(user=user2, first_name="B", employee_code=f"EMP-{uuid.uuid4().hex[:6]}")

        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            AllocationService.allocate(asset=asset, employee=employee)

        # Asset is now ALLOCATED — second allocation must fail
        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"), \
                 patch("apps.allocations.services.log_action"):
                AllocationService.allocate(asset=asset, employee=emp2)

    def test_returned_asset_can_be_reallocated(self, tenant, asset, employee, admin_employee):
        """After return, the asset becomes available again."""
        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)
            AllocationService.return_asset(allocation=alloc, return_condition="GOOD")

        asset.refresh_from_db()
        assert asset.status == "AVAILABLE"
        assert asset.current_owner is None

        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc2 = AllocationService.allocate(asset=asset, employee=admin_employee)

        assert alloc2.status == "ACTIVE"


# ---------------------------------------------------------------------------
# 2. Asset status/condition guardrails
# ---------------------------------------------------------------------------

class TestAllocationGuardrails:

    def test_damaged_asset_cannot_be_allocated(self, tenant, asset_factory, category, employee):
        asset = asset_factory(name="Damaged", category=category, status="AVAILABLE", condition="DAMAGED")
        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"):
                AllocationService.allocate(asset=asset, employee=employee)

    def test_in_maintenance_asset_cannot_be_allocated(self, tenant, asset_factory, category, employee):
        asset = asset_factory(name="InMaint", category=category, status="IN_MAINTENANCE", condition="GOOD")
        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"):
                AllocationService.allocate(asset=asset, employee=employee)

    def test_lost_asset_cannot_be_allocated(self, tenant, asset_factory, category, employee):
        asset = asset_factory(name="Lost", category=category, status="LOST", condition="GOOD")
        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"):
                AllocationService.allocate(asset=asset, employee=employee)

    def test_retired_asset_cannot_be_allocated(self, tenant, asset_factory, category, employee):
        asset = asset_factory(name="Retired", category=category, status="RETIRED", condition="GOOD")
        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"):
                AllocationService.allocate(asset=asset, employee=employee)

    def test_already_allocated_asset_cannot_be_allocated(self, tenant, asset_factory, category, employee):
        asset = asset_factory(name="Alloc", category=category, status="ALLOCATED", condition="GOOD")
        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"):
                AllocationService.allocate(asset=asset, employee=employee)

    def test_inactive_employee_cannot_receive_allocation(self, tenant, asset, employee_factory):
        """Employee.is_active=False blocks allocation."""
        inactive_emp = employee_factory(email="inactive_emp@test.local")
        inactive_emp.is_active = False
        inactive_emp.save()
        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"):
                AllocationService.allocate(asset=asset, employee=inactive_emp)


# ---------------------------------------------------------------------------
# 3. Transfer guardrails
# ---------------------------------------------------------------------------

class TestTransferGuardrails:

    def test_transfer_blocked_for_open_incident(
        self, tenant, asset, employee, admin_employee, incident_factory
    ):
        """Transfer must be blocked if the asset has an OPEN incident."""
        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)

        incident_factory(asset=asset, reported_by=employee, status="OPEN")

        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"), \
                 patch("apps.allocations.services.log_action"):
                AllocationService.transfer_asset(
                    allocation=alloc,
                    new_employee=admin_employee,
                )

    def test_transfer_blocked_for_in_progress_incident(
        self, tenant, asset, employee, admin_employee, incident_factory
    ):
        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)

        incident_factory(asset=asset, reported_by=employee, status="IN_PROGRESS")

        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"), \
                 patch("apps.allocations.services.log_action"):
                AllocationService.transfer_asset(
                    allocation=alloc,
                    new_employee=admin_employee,
                )

    def test_transfer_allowed_when_no_open_incidents(
        self, tenant, asset, employee, admin_employee, incident_factory
    ):
        """Transfer works when incident is RESOLVED."""
        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)

        incident_factory(asset=asset, reported_by=employee, status="RESOLVED")

        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            new_alloc = AllocationService.transfer_asset(
                allocation=alloc,
                new_employee=admin_employee,
            )

        assert new_alloc.employee == admin_employee

    def test_transfer_to_same_employee_is_blocked(self, tenant, asset, employee):
        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)

        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"), \
                 patch("apps.allocations.services.log_action"):
                AllocationService.transfer_asset(allocation=alloc, new_employee=employee)

    def test_transfer_to_inactive_employee_is_blocked(self, tenant, asset, employee, employee_factory):
        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)

        inactive_emp = employee_factory(email="inactive2@test.local")
        inactive_emp.is_active = False
        inactive_emp.save()

        with pytest.raises(AFValidationError):
            with patch("apps.allocations.services.NotificationService"), \
                 patch("apps.allocations.services.log_action"):
                AllocationService.transfer_asset(allocation=alloc, new_employee=inactive_emp)


# ---------------------------------------------------------------------------
# 4. Return and cancel
# ---------------------------------------------------------------------------

class TestReturnAndCancel:

    def test_return_updates_asset_status(self, tenant, asset, employee):
        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)
            AllocationService.return_asset(allocation=alloc, return_condition="GOOD")

        asset.refresh_from_db()
        assert asset.status == "AVAILABLE"
        assert asset.current_owner is None
        assert asset.current_allocation is None

    def test_cancel_updates_asset_status(self, tenant, asset, employee):
        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)
            AllocationService.cancel_allocation(allocation=alloc, remarks="Test cancel")

        asset.refresh_from_db()
        assert asset.status == "AVAILABLE"
        assert asset.current_owner is None

    def test_return_non_active_allocation_is_blocked(self, tenant, asset, employee):
        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)
            AllocationService.return_asset(allocation=alloc, return_condition="GOOD")

        # Try to return it again — must raise
        with pytest.raises(AFValidationError):
            AllocationService.return_asset(allocation=alloc, return_condition="GOOD")

    def test_cancel_non_active_allocation_is_blocked(self, tenant, asset, employee):
        with patch("apps.allocations.services.NotificationService"), \
             patch("apps.allocations.services.log_action"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)
            AllocationService.cancel_allocation(allocation=alloc, remarks="Cancel")

        with pytest.raises(AFValidationError):
            AllocationService.cancel_allocation(allocation=alloc, remarks="Cancel again")


# ---------------------------------------------------------------------------
# 5. Audit log created on allocation actions
# ---------------------------------------------------------------------------

class TestAllocationAuditLog:

    def test_allocation_creates_audit_log(self, tenant, asset, employee):
        from apps.audit.models import AuditLog
        count_before = AuditLog.objects.count()
        with patch("apps.allocations.services.NotificationService"):
            AllocationService.allocate(asset=asset, employee=employee)
        assert AuditLog.objects.count() > count_before

    def test_return_creates_audit_log(self, tenant, asset, employee):
        from apps.audit.models import AuditLog
        with patch("apps.allocations.services.NotificationService"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)
        count_before = AuditLog.objects.count()
        with patch("apps.allocations.services.NotificationService"):
            AllocationService.return_asset(allocation=alloc, return_condition="GOOD")
        assert AuditLog.objects.count() > count_before

    def test_cancel_creates_audit_log(self, tenant, asset, employee):
        from apps.audit.models import AuditLog
        with patch("apps.allocations.services.NotificationService"):
            alloc = AllocationService.allocate(asset=asset, employee=employee)
        count_before = AuditLog.objects.count()
        AllocationService.cancel_allocation(allocation=alloc, remarks="Test")
        assert AuditLog.objects.count() > count_before
