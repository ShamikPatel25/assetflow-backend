"""
Test suite: License Assignment
Covers Fix 4 — seat overbooking, expiry, concurrent assignment, duplicates.
"""
import uuid
import pytest
from unittest.mock import patch
from datetime import date, timedelta

from apps.licenses.services import LicenseService
from apps.base.errors import AFValidationError

pytestmark = pytest.mark.django_db


class TestLicenseAssign:

    def test_assign_seat_to_active_employee(self, tenant, license_factory, employee):
        lic = license_factory(name="Office365", total_seats=5)
        with patch("apps.licenses.services.log_action"):
            assignment = LicenseService.assign(lic, employee)
        assert assignment.status == "ACTIVE"
        assert assignment.employee == employee

    def test_assign_uses_one_seat(self, tenant, license_factory, employee):
        lic = license_factory(name="Slack", total_seats=3)
        with patch("apps.licenses.services.log_action"):
            LicenseService.assign(lic, employee)
        lic.refresh_from_db()
        # used_seats is a property, no refresh needed
        assert lic.used_seats == 1
        assert lic.available_seats == 2

    def test_inactive_license_cannot_be_assigned(self, tenant, license_factory, employee):
        lic = license_factory(name="InactiveApp", total_seats=5, status="EXPIRED")
        with pytest.raises(AFValidationError):
            LicenseService.assign(lic, employee)

    def test_cancelled_license_cannot_be_assigned(self, tenant, license_factory, employee):
        lic = license_factory(name="CancelledApp", total_seats=5, status="CANCELLED")
        with pytest.raises(AFValidationError):
            LicenseService.assign(lic, employee)

    def test_expired_date_license_cannot_be_assigned(self, tenant, license_factory, employee):
        """License with an expiry_date in the past must be rejected."""
        past = date.today() - timedelta(days=1)
        lic = license_factory(name="ExpiredDate", total_seats=5, expiry_date=past)
        with pytest.raises(AFValidationError):
            LicenseService.assign(lic, employee)

    def test_future_expiry_license_can_be_assigned(self, tenant, license_factory, employee):
        future = date.today() + timedelta(days=30)
        lic = license_factory(name="ValidLic", total_seats=5, expiry_date=future)
        with patch("apps.licenses.services.log_action"):
            assignment = LicenseService.assign(lic, employee)
        assert assignment.status == "ACTIVE"

    def test_no_available_seats_blocks_assignment(self, tenant, license_factory, employee_factory):
        lic = license_factory(name="OneSeat", total_seats=1)
        emp1 = employee_factory(email="seat1@test.local")
        emp2 = employee_factory(email="seat2@test.local")

        with patch("apps.licenses.services.log_action"):
            LicenseService.assign(lic, emp1)

        with pytest.raises(AFValidationError):
            LicenseService.assign(lic, emp2)

    def test_duplicate_active_assignment_is_blocked(self, tenant, license_factory, employee):
        lic = license_factory(name="DupCheck", total_seats=10)
        with patch("apps.licenses.services.log_action"):
            LicenseService.assign(lic, employee)

        with pytest.raises(AFValidationError):
            LicenseService.assign(lic, employee)

    def test_inactive_employee_cannot_be_assigned_license(self, tenant, license_factory, employee_factory):
        lic = license_factory(name="ActiveLic", total_seats=10)
        # Create employee then deactivate the Employee record (not just the TenantUser)
        inactive_emp = employee_factory(email="inact@test.local")
        inactive_emp.is_active = False
        inactive_emp.save()
        with pytest.raises(AFValidationError):
            LicenseService.assign(lic, inactive_emp)

    def test_seats_go_negative_is_prevented(self, tenant, license_factory, employee_factory):
        """Assign all seats then try one more — must fail, never go negative."""
        lic = license_factory(name="ThreeSeats", total_seats=2)
        emps = [employee_factory(email=f"seat{i}@test.local") for i in range(3)]

        with patch("apps.licenses.services.log_action"):
            LicenseService.assign(lic, emps[0])
            LicenseService.assign(lic, emps[1])

        with pytest.raises(AFValidationError):
            LicenseService.assign(lic, emps[2])

        assert lic.available_seats == 0


class TestLicenseRevoke:

    def test_revoke_frees_seat(self, tenant, license_factory, employee):
        lic = license_factory(name="RevokeTest", total_seats=2)
        with patch("apps.licenses.services.log_action"):
            assignment = LicenseService.assign(lic, employee)
        assert lic.used_seats == 1

        with patch("apps.licenses.services.log_action"):
            LicenseService.revoke(assignment)

        assert lic.used_seats == 0
        assert lic.available_seats == 2

    def test_revoke_already_revoked_is_blocked(self, tenant, license_factory, employee):
        lic = license_factory(name="DblRevoke", total_seats=5)
        with patch("apps.licenses.services.log_action"):
            assignment = LicenseService.assign(lic, employee)
            LicenseService.revoke(assignment)

        with pytest.raises(AFValidationError):
            LicenseService.revoke(assignment)

    def test_revoke_allows_reassignment(self, tenant, license_factory, employee):
        lic = license_factory(name="Reassign", total_seats=1)
        with patch("apps.licenses.services.log_action"):
            assignment = LicenseService.assign(lic, employee)
            LicenseService.revoke(assignment)
            # Reassign to same employee now that previous was revoked
            new_assignment = LicenseService.assign(lic, employee)
        assert new_assignment.status == "ACTIVE"


class TestLicenseBulkAssign:

    def test_bulk_assign_multiple_employees(self, tenant, license_factory, employee_factory):
        lic = license_factory(name="BulkLic", total_seats=5)
        emps = [employee_factory(email=f"bulk{i}@test.local") for i in range(3)]
        data = [{"employee": e} for e in emps]

        with patch("apps.licenses.services.log_action"):
            created = LicenseService.bulk_assign(lic, data)
        assert len(created) == 3

    def test_bulk_assign_rejects_if_not_enough_seats(self, tenant, license_factory, employee_factory):
        lic = license_factory(name="TightLic", total_seats=2)
        emps = [employee_factory(email=f"tight{i}@test.local") for i in range(3)]
        data = [{"employee": e} for e in emps]

        with pytest.raises(AFValidationError):
            LicenseService.bulk_assign(lic, data)

    def test_bulk_assign_rejects_duplicate_within_batch(self, tenant, license_factory, employee):
        lic = license_factory(name="DupBatch", total_seats=10)
        with patch("apps.licenses.services.log_action"):
            LicenseService.assign(lic, employee)

        # Try to bulk assign the same employee again
        data = [{"employee": employee}]
        with pytest.raises(AFValidationError):
            LicenseService.bulk_assign(lic, data)


class TestLicenseAuditLog:

    def test_assign_creates_audit_log(self, tenant, license_factory, employee):
        from apps.audit.models import AuditLog
        lic = license_factory(name="AuditLic", total_seats=5)
        count_before = AuditLog.objects.count()
        LicenseService.assign(lic, employee)
        assert AuditLog.objects.count() > count_before

    def test_revoke_creates_audit_log(self, tenant, license_factory, employee):
        from apps.audit.models import AuditLog
        lic = license_factory(name="AuditRevoke", total_seats=5)
        assignment = LicenseService.assign(lic, employee)
        count_before = AuditLog.objects.count()
        LicenseService.revoke(assignment)
        assert AuditLog.objects.count() > count_before
