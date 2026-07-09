"""
Tests for Licenses module.

Covers:
- License CRUD with role-based permissions
- License seat management (assign, revoke, seat counting)
- No-seat-available enforcement
- Inactive license cannot have new assignments
- Double-assignment prevention (unique constraint)
- LicenseService business logic
- Soft-delete cascade: deleting a license revokes all its assignments
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

    def test_license_follows_employee_not_asset(self, license_factory, employee):
        """
        License assignment has NO asset field.
        The seat is tied to the employee's identity — asset changes don't affect it.
        """
        from apps.licenses.models import LicenseAssignment
        lic = license_factory(name="MS365", total_seats=5)
        assignment = LicenseService.assign(lic, employee=employee)

        assert not hasattr(assignment, "asset") or not hasattr(
            LicenseAssignment._meta.get_fields,
            "asset"
        )
        # Confirm the model has no asset field
        field_names = [f.name for f in LicenseAssignment._meta.get_fields()]
        assert "asset" not in field_names


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


# 3. ASSIGN / REVOKE API ACTIONS

class TestLicenseAssignRevokeEndpoints:
    """{id}/assign/ and {id}/revoke/ actions."""

    base_url = "/api/v1/licenses/"

    def test_hr_can_assign_license(self, hr_api_client, license_factory, employee):
        """POST assign/ → 201 with nested license + employee. No asset field."""
        lic = license_factory(name="Figma", total_seats=3)
        response = hr_api_client.post(f"{self.base_url}{lic.id}/assign/", data={
            "employee": str(employee.id),
        }, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "ACTIVE"
        assert response.data["license"]["name"] == "Figma"
        assert response.data["employee"]["id"] == employee.id
        # asset field must not appear in the response
        assert "asset" not in response.data

    def test_assign_populates_assigned_by(
        self, hr_api_client, hr_user, license_factory, employee, employee_factory,
    ):
        """Caller with employee profile fills assigned_by."""
        assigner = employee_factory(user=hr_user, first_name="HR", last_name="Boss")
        lic = license_factory(name="Slack", total_seats=2)
        response = hr_api_client.post(f"{self.base_url}{lic.id}/assign/", data={
            "employee": str(employee.id),
        }, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["assigned_by"]["id"] == assigner.id

    def test_assign_duplicate_for_same_employee_returns_400(
        self, hr_api_client, license_factory, employee,
    ):
        """A second active assignment for the same employee → service raises → 400."""
        lic = license_factory(name="Dup", total_seats=5)
        LicenseService.assign(lic, employee=employee)
        response = hr_api_client.post(f"{self.base_url}{lic.id}/assign/", data={
            "employee": str(employee.id),
        }, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_employee_cannot_assign(self, employee_api_client, license_factory, employee):
        lic = license_factory(name="NoPerm", total_seats=2)
        response = employee_api_client.post(f"{self.base_url}{lic.id}/assign/", data={
            "employee": str(employee.id),
        }, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hr_can_revoke_license(self, hr_api_client, license_factory, employee):
        """POST revoke/ → 200 REVOKED."""
        lic = license_factory(name="Revoke Me", total_seats=2)
        assignment = LicenseService.assign(lic, employee=employee)
        response = hr_api_client.post(f"{self.base_url}{lic.id}/revoke/", data={
            "assignment": str(assignment.id),
        }, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "REVOKED"

    def test_revoke_already_revoked_returns_400(
        self, hr_api_client, license_factory, employee,
    ):
        lic = license_factory(name="RR", total_seats=2)
        assignment = LicenseService.assign(lic, employee=employee)
        LicenseService.revoke(assignment)
        response = hr_api_client.post(f"{self.base_url}{lic.id}/revoke/", data={
            "assignment": str(assignment.id),
        }, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 3b. BULK ASSIGN — POST /licenses/{id}/bulk-assign/

class TestLicenseBulkAssign:
    base_url = "/api/v1/licenses/"

    def test_hr_bulk_assigns_to_multiple(
        self, hr_api_client, license_factory, employee_factory,
    ):
        e1 = employee_factory(first_name="B1")
        e2 = employee_factory(first_name="B2")
        lic = license_factory(name="BulkOK", total_seats=5)
        response = hr_api_client.post(f"{self.base_url}{lic.id}/bulk-assign/", data=[
            {"employee": str(e1.id)}, {"employee": str(e2.id)},
        ], format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data) == 2

    def test_bulk_assign_not_enough_seats(
        self, hr_api_client, license_factory, employee_factory,
    ):
        e1 = employee_factory(first_name="S1")
        e2 = employee_factory(first_name="S2")
        lic = license_factory(name="Tight", total_seats=1)
        response = hr_api_client.post(f"{self.base_url}{lic.id}/bulk-assign/", data=[
            {"employee": str(e1.id)}, {"employee": str(e2.id)},
        ], format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_assign_duplicate_active_rejected(
        self, hr_api_client, license_factory, employee,
    ):
        lic = license_factory(name="DupBulk", total_seats=5)
        LicenseService.assign(lic, employee=employee)
        response = hr_api_client.post(f"{self.base_url}{lic.id}/bulk-assign/", data=[
            {"employee": str(employee.id)},
        ], format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_assign_inactive_license_rejected(
        self, hr_api_client, license_factory, employee_factory,
    ):
        e1 = employee_factory(first_name="I1")
        lic = license_factory(name="Inactive", total_seats=5, status="EXPIRED")
        response = hr_api_client.post(f"{self.base_url}{lic.id}/bulk-assign/", data=[
            {"employee": str(e1.id)},
        ], format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_assign_empty_list_returns_empty(
        self, hr_api_client, license_factory,
    ):
        """An empty payload assigns nothing and returns an empty list."""
        lic = license_factory(name="BulkNone", total_seats=2)
        response = hr_api_client.post(f"{self.base_url}{lic.id}/bulk-assign/", data=[],
                                      format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data == []


# 4. MODEL

class TestLicenseAssignmentModel:
    def test_assignment_str(self, license_factory, employee):
        lic = license_factory(name="StrLic")
        assignment = LicenseService.assign(lic, employee=employee)
        assert "StrLic" in str(assignment)


# 5. SOFT-DELETE CASCADE — deleting a license must revoke its assignments

class TestLicenseSoftDeleteCascade:
    """
    When a SoftwareLicense is soft-deleted via the API, every ACTIVE
    assignment on that license must be automatically REVOKED in the same
    transaction. Assignments that are already REVOKED or EXPIRED must
    be left untouched (idempotency).
    """
    base_url = "/api/v1/licenses/"

    def test_delete_license_revokes_all_active_assignments(
        self, admin_api_client, license_factory, employee_factory,
    ):
        """DELETE /licenses/{id}/ → active assignments become REVOKED."""
        from apps.licenses.models import LicenseAssignment

        e1 = employee_factory(first_name="U1")
        e2 = employee_factory(first_name="U2")
        lic = license_factory(name="DeleteMe", total_seats=5)

        a1 = LicenseService.assign(lic, employee=e1)
        a2 = LicenseService.assign(lic, employee=e2)

        response = admin_api_client.delete(f"{self.base_url}{lic.id}/")
        assert response.status_code == status.HTTP_200_OK

        a1.refresh_from_db()
        a2.refresh_from_db()
        assert a1.status == LicenseAssignment.Status.REVOKED
        assert a1.revoked_at is not None
        assert a2.status == LicenseAssignment.Status.REVOKED
        assert a2.revoked_at is not None

        lic.refresh_from_db()
        assert lic.is_deleted is True

    def test_delete_license_with_no_assignments_succeeds(
        self, admin_api_client, license_factory,
    ):
        """A license with zero assignments can be deleted cleanly."""
        lic = license_factory(name="EmptyLic", total_seats=10)
        response = admin_api_client.delete(f"{self.base_url}{lic.id}/")
        assert response.status_code == status.HTTP_200_OK

        lic.refresh_from_db()
        assert lic.is_deleted is True

    def test_delete_does_not_touch_already_revoked_assignments(
        self, admin_api_client, license_factory, employee_factory,
    ):
        """Assignments already REVOKED before deletion are left untouched."""
        from apps.licenses.models import LicenseAssignment

        emp = employee_factory(first_name="OldUser")
        lic = license_factory(name="PartialDel", total_seats=5)
        assignment = LicenseService.assign(lic, employee=emp)

        assignment = LicenseService.revoke(assignment)
        revoked_at_before = assignment.revoked_at

        response = admin_api_client.delete(f"{self.base_url}{lic.id}/")
        assert response.status_code == status.HTTP_200_OK

        assignment.refresh_from_db()
        assert assignment.status == LicenseAssignment.Status.REVOKED
        assert assignment.revoked_at == revoked_at_before

    def test_used_seats_is_zero_after_delete(
        self, admin_api_client, license_factory, employee_factory,
    ):
        """After deletion, used_seats on the license drops to 0."""
        emp = employee_factory(first_name="SeatUser")
        lic = license_factory(name="SeatCheck", total_seats=3)
        LicenseService.assign(lic, employee=emp)
        assert lic.used_seats == 1

        admin_api_client.delete(f"{self.base_url}{lic.id}/")

        lic.refresh_from_db()
        assert lic.used_seats == 0
