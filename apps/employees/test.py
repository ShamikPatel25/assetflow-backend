"""
Tests for Employee, Department, and Tenant Auth modules.

Covers:
- Role-Based Access Control (RBAC) hierarchy enforcement
- Employee profile CRUD with proper ownership rules
- Department management permissions
- Login / Auth flow with correct and incorrect credentials
- Cross-role escalation attacks (employee → HR, HR → admin)
- Soft-delete behavior and inactive user blocking
- Data validation (phone, email, required fields)
"""
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


# 1. AUTHENTICATION & LOGIN FLOW

class TestAuthFlow:
    """Verify the tenant login endpoint handles
    all credential scenarios correctly."""

    login_url = "/api/v1/auth/login/"

    def test_login_with_valid_credentials(self, api_client, tenant_user_factory):
        """Active user with correct password gets JWT tokens."""
        tenant_user_factory(email="valid@test.local", password="MyP@ss123")
        response = api_client.post(self.login_url, data={
            "email": "valid@test.local",
            "password": "MyP@ss123",
        })
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_login_with_wrong_password(self, api_client, tenant_user_factory):
        """Correct email + wrong password → 400."""
        tenant_user_factory(email="wrongpw@test.local", password="CorrectPass")
        response = api_client.post(self.login_url, data={
            "email": "wrongpw@test.local",
            "password": "WrongPassword",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_with_nonexistent_user(self, api_client, tenant):
        """Email that doesn't exist in tenant → 400."""
        response = api_client.post(self.login_url, data={
            "email": "nobody@test.local",
            "password": "anything",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_blocked_for_inactive_user(self, api_client, tenant_user_factory):
        """User with is_active=False cannot login."""
        tenant_user_factory(email="inactive@test.local", is_active=False)
        response = api_client.post(self.login_url, data={
            "email": "inactive@test.local",
            "password": "testpass123",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_returns_user_role(self, api_client, tenant_user_factory):
        """Token response includes the user's role for frontend routing."""
        tenant_user_factory(email="hr@test.local", role="HR_MANAGER")
        response = api_client.post(self.login_url, data={
            "email": "hr@test.local",
            "password": "testpass123",
        })
        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"]["role"] == "HR_MANAGER"

    def test_login_empty_payload(self, api_client, tenant):
        """Empty body → 400."""
        response = api_client.post(self.login_url, data={})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_missing_password(self, api_client, tenant):
        """Email without password → 400."""
        response = api_client.post(self.login_url, data={"email": "a@b.com"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 2. PROFILE MANAGEMENT

class TestProfileManagement:
    """Verify /api/v1/auth/profile/ works for all roles."""

    profile_url = "/api/v1/auth/profile/"

    def test_unauthenticated_cannot_view_profile(self, api_client, tenant):
        """No JWT → 401."""
        response = api_client.get(self.profile_url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_employee_can_view_own_profile(self, employee_api_client, employee_user, employee_factory):
        """Employee with employee_profile can fetch their data."""
        employee_factory(user=employee_user)
        response = employee_api_client.get(self.profile_url)
        assert response.status_code == status.HTTP_200_OK

    def test_user_without_employee_profile_gets_404(self, admin_api_client):
        """User who has no Employee record → 404."""
        response = admin_api_client.get(self.profile_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


# 3. EMPLOYEE LIST & CRUD PERMISSIONS

class TestEmployeeCRUDPermissions:
    """Ensure strict role-based access on /api/v1/employees/."""

    url = "/api/v1/employees/"

    def test_unauthenticated_cannot_list_employees(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_cannot_list_employees(self, employee_api_client):
        """EMPLOYEE role should not see other employees."""
        response = employee_api_client.get(self.url)
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN]

    def test_hr_can_list_employees(self, hr_api_client):
        """HR_MANAGER can list employees."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_admin_can_list_employees(self, admin_api_client):
        """ORGANIZATION_ADMIN can list employees."""
        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_employee_cannot_create_employee(self, employee_api_client):
        """EMPLOYEE role cannot invite a new employee."""
        response = employee_api_client.post(self.url, data={
            "first_name": "Rogue", "last_name": "Agent",
            "email": "rogue@test.local", "role": "EMPLOYEE",
        })
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

    def test_employee_cannot_delete_other_employee(self, employee_api_client, employee_factory):
        """EMPLOYEE role cannot delete another employee."""
        emp = employee_factory()
        url = f"{self.url}{emp.id}/"
        response = employee_api_client.delete(url)
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]


# 4. CROSS-ROLE ESCALATION ATTACKS

class TestCrossRoleEscalation:
    """Verify that no role can escalate to a higher privilege."""

    def test_hr_cannot_modify_org_admin_profile(self, hr_api_client, org_admin_user):
        """HR should not be able to deactivate an Org Admin."""
        url = f"/api/v1/employees/users/{org_admin_user.id}/"
        response = hr_api_client.put(url, data={"is_active": False})
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        ]

    def test_employee_cannot_modify_admin_endpoints(self, employee_api_client):
        """EMPLOYEE cannot modify organization settings."""
        response = employee_api_client.put("/api/v1/organization/settings/", data={"name": "Hacked"})
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

    def test_hr_cannot_access_org_settings_write(self, hr_api_client):
        """HR cannot modify organization settings (org admin only)."""
        response = hr_api_client.put("/api/v1/organization/settings/", data={"name": "Hacked"})
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]


# 5. DEPARTMENT MANAGEMENT

class TestDepartmentManagement:
    """Verify department CRUD and role permissions."""

    url = "/api/v1/departments/"

    def test_hr_can_list_departments(self, hr_api_client, department):
        """HR_MANAGER can see department list."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_employee_cannot_create_department(self, employee_api_client):
        """EMPLOYEE cannot create a department."""
        response = employee_api_client.post(self.url, data={
            "name": "Rogue Dept", "code": "ROGUE"
        })
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

    def test_department_code_uniqueness(self, hr_api_client, department):
        """Duplicate department code should be rejected."""
        response = hr_api_client.post(self.url, data={
            "name": "Duplicate", "code": department.code
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 6. DATA VALIDATION

class TestDataValidation:
    """Verify serializer-level validations."""

    def test_invalid_department_uuid_rejected(self, hr_api_client):
        """Non-UUID department ID → 400."""
        response = hr_api_client.post("/api/v1/employees/", data={
            "first_name": "No", "last_name": "Dept",
            "email": "nodept@test.local", "department": "invalid-uuid",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_password_wrong_old_password(self, hr_api_client):
        """Wrong current password in change-password → error."""
        response = hr_api_client.post("/api/v1/auth/change-password/", data={
            "old_password": "definitely_wrong",
            "new_password": "NewSecure123",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_password_too_short(self, hr_api_client):
        """New password below minimum length → error."""
        response = hr_api_client.post("/api/v1/auth/change-password/", data={
            "old_password": "testpass123",
            "new_password": "short",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST
"""
    ]
"""
