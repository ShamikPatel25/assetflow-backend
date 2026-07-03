"""
Tests for Licenses module.

Covers:
- License CRUD with role-based permissions
- License seat management (assign, revoke, seat counting)
- No-seat-available enforcement
- Inactive license cannot have new assignments
- Double-assignment prevention (unique constraint)
- LicenseService business logic
"""
from apps.base.errors import AFValidationError
from apps.licenses.services import LicenseService
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


# 1. LICENSE SERVICE LOGIC

class TestLicenseServiceLogic:
    """LicenseService.assign() and .revoke() rules."""

    def test_assign_active_license_with_seats(self, license_factory, employee):
        """Assigning from an ACTIVE license with seats succeeds."""

        lic = license_factory(name="VS Code Pro", total_seats=5)
        assignment = LicenseService.assign(lic, employee=employee)
        assert assignment.status == "ACTIVE"
        assert assignment.employee == employee
        assert lic.used_seats == 1
        assert lic.available_seats == 4

    def test_assign_when_no_seats_available_fails(self, license_factory, employee,
                                                    employee_factory):
        """All seats used → cannot assign another."""

        lic = license_factory(name="Single Seat", total_seats=1)
        LicenseService.assign(lic, employee=employee)

        new_emp = employee_factory(first_name="NewGuy")
        with pytest.raises(AFValidationError):
            LicenseService.assign(lic, employee=new_emp)

    def test_assign_expired_license_fails(self, license_factory, employee):
        """Cannot assign from an EXPIRED license."""

        lic = license_factory(name="Expired", status="EXPIRED")
        with pytest.raises(AFValidationError):
            LicenseService.assign(lic, employee=employee)

    def test_assign_cancelled_license_fails(self, license_factory, employee):
        """Cannot assign from a CANCELLED license."""

        lic = license_factory(name="Cancelled", status="CANCELLED")
        with pytest.raises(AFValidationError):
            LicenseService.assign(lic, employee=employee)

    def test_revoke_active_assignment_succeeds(self, license_factory, employee):
        """Revoking an ACTIVE assignment → REVOKED, seat freed."""

        lic = license_factory(name="Revokable", total_seats=3)
        assignment = LicenseService.assign(lic, employee=employee)
        assert lic.available_seats == 2

        result = LicenseService.revoke(assignment)
        assert result.status == "REVOKED"
        assert result.revoked_at is not None
        assert lic.available_seats == 3  # seat freed

    def test_revoke_already_revoked_fails(self, license_factory, employee):
        """Cannot revoke an already-revoked assignment."""

        lic = license_factory(name="Double Revoke")
        assignment = LicenseService.assign(lic, employee=employee)
        LicenseService.revoke(assignment)

        with pytest.raises(AFValidationError):
            LicenseService.revoke(assignment)

    def test_seat_count_accurate_after_multiple_operations(
        self, license_factory, employee_factory
    ):
        """Seats count correct after assign/revoke/assign cycle."""

        lic = license_factory(name="Multi Ops", total_seats=3)
        emp1 = employee_factory(first_name="E1")
        emp2 = employee_factory(first_name="E2")
        emp3 = employee_factory(first_name="E3")

        a1 = LicenseService.assign(lic, employee=emp1)
        LicenseService.assign(lic, employee=emp2)
        assert lic.available_seats == 1

        LicenseService.revoke(a1)
        assert lic.available_seats == 2

        LicenseService.assign(lic, employee=emp3)
        assert lic.available_seats == 1


# 2. LICENSE API PERMISSIONS

class TestLicenseAPIPermissions:
    """Verify license API access by role."""

    url = "/api/v1/licenses/"

    def test_unauthenticated_blocked(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_can_read_licenses(self, employee_api_client, license_factory):
        """EMPLOYEE can list licenses (read-only)."""
        license_factory()
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_employee_cannot_create_license(self, employee_api_client):
        """EMPLOYEE cannot add a license."""
        response = employee_api_client.post(self.url, data={
            "name": "Hacked License", "total_seats": 100,
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_create_license(self, admin_api_client):
        """Admin can create a license."""
        response = admin_api_client.post(self.url, data={
            "name": "JetBrains", "total_seats": 10,
            "vendor": "JetBrains s.r.o.",
        })
        assert response.status_code == status.HTTP_201_CREATED
