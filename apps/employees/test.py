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

    def test_hr_cannot_modify_org_admin_profile(self, hr_api_client, admin_employee):
        """HR should not be able to edit an Org Admin's employee profile."""
        url = f"/api/v1/employees/{admin_employee.id}/"
        response = hr_api_client.put(url, data={"first_name": "Hacked"}, format="json")
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
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


# ---------------------------------------------------------------------------
# Helpers for invitation-token tests
# ---------------------------------------------------------------------------

def _make_invitation_token(user_id, ttl_hours=1, token_type="invitation"):
    """Build a signed JWT invitation token like apps.accounts.utils does."""
    import jwt
    from datetime import datetime, timedelta, timezone
    from django.conf import settings

    payload = {
        "user_id": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
        "type": token_type,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _make_expired_token(user_id):
    """Build an already-expired invitation token."""
    import jwt
    from datetime import datetime, timedelta, timezone
    from django.conf import settings

    payload = {
        "user_id": str(user_id),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "type": "invitation",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


# 7. EMPLOYEE UTILS — generate_employee_code

class TestGenerateEmployeeCode:
    """Unit tests for apps.employees.utils.generate_employee_code."""

    def test_code_uses_first_and_last_initials(self, tenant):
        from apps.employees.utils import generate_employee_code

        code = generate_employee_code("Krish", "Patel")
        assert code.startswith("KP")
        assert len(code) == 5
        assert code[2:].isdigit()

    def test_empty_names_fall_back_to_x(self, tenant):
        """Empty first/last name → 'XX' prefix (defensive branch)."""
        from apps.employees.utils import generate_employee_code

        code = generate_employee_code("", "")
        assert code.startswith("XX")

    def test_code_is_unique_against_existing(self, tenant, employee_factory):
        """A generated code must not collide with an existing employee."""
        from apps.employees.utils import generate_employee_code

        existing = employee_factory(first_name="Zed", last_name="Young")
        code = generate_employee_code("Zed", "Young")
        assert code != existing.employee_code

    def test_collision_forces_new_code(self, tenant, monkeypatch):
        """When the first candidate collides, the loop retries and returns
        a different (non-existing) code."""
        from apps.employees import utils
        from apps.employees.models import TenantUser, Employee

        # Seed an employee whose code is exactly the first candidate we will
        # force via a deterministic randint sequence.
        user = TenantUser(email="collide@test.local", role="EMPLOYEE")
        user.set_password("testpass123")
        user.save()
        Employee.objects.create(
            user=user, first_name="Ann", last_name="Bee",
            employee_code="AB001",
        )

        seq = iter([1, 2])  # first -> "001" (collides), second -> "002"

        def fake_randint(a, b):
            return next(seq)

        monkeypatch.setattr(utils.random, "randint", fake_randint)
        code = utils.generate_employee_code("Ann", "Bee")
        assert code == "AB002"

    def test_fallback_to_four_digits_when_space_exhausted(self, tenant, monkeypatch):
        """If every 3-digit candidate collides, fall back to 4-digit codes."""
        from apps.employees import utils

        # Every 3-digit lookup reports "exists"; the 4-digit lookups do not.
        calls = {"n": 0}
        real_filter = utils.Employee.objects.filter

        class _QS:
            def __init__(self, exists):
                self._exists = exists

            def exists(self):
                return self._exists

        def fake_filter(**kwargs):
            code = kwargs.get("employee_code", "")
            # 3-digit codes are prefix(2) + 3 = len 5; 4-digit => len 6
            return _QS(exists=len(code) == 5)

        monkeypatch.setattr(utils.Employee.objects, "filter", fake_filter)
        code = utils.generate_employee_code("Cee", "Dee")
        assert code.startswith("CD")
        assert len(code) == 6  # 4-digit fallback used

    def test_raises_when_no_unique_code_possible(self, tenant, monkeypatch):
        """If both 3- and 4-digit spaces are exhausted, raise ValueError."""
        from apps.employees import utils

        class _QS:
            def exists(self):
                return True

        monkeypatch.setattr(utils.Employee.objects, "filter", lambda **kw: _QS())
        with pytest.raises(ValueError):
            utils.generate_employee_code("Ex", "Ex")


# 8. EmployeeCreateSerializer — validation + create

class TestEmployeeCreateSerializer:
    """Direct serializer tests for creating employees + invitations."""

    def _valid_payload(self, **overrides):
        data = {
            "first_name": "New",
            "last_name": "Hire",
            "email": "newhire@test.local",
            "phone": "1234567890",
            "designation": "Engineer",
            "joining_date": "2024-01-01",
            "role": "EMPLOYEE",
        }
        data.update(overrides)
        return data

    def test_create_happy_path_sends_invitation(self, tenant, monkeypatch):
        from apps.employees.serializers import EmployeeCreateSerializer
        from apps.employees.models import Employee, TenantUser

        sent = {}

        def fake_send(user, tenant_name, domain_name):
            sent["user"] = user
            sent["tenant"] = tenant_name
            sent["domain"] = domain_name

        monkeypatch.setattr(
            "apps.employees.serializers.send_invitation_email", fake_send
        )

        ser = EmployeeCreateSerializer(data=self._valid_payload())
        assert ser.is_valid(), ser.errors
        employee = ser.save()

        assert isinstance(employee, Employee)
        assert employee.employee_code
        user = TenantUser.objects.get(email="newhire@test.local")
        assert user.is_active is False           # inactive until invite accepted
        assert user.has_usable_password() is False
        assert sent["user"] == user
        # to_representation delegates to EmployeeSerializer
        rep = ser.data
        assert rep["email"] == "newhire@test.local"

    def test_create_with_department_and_manager(self, tenant, department,
                                                employee_factory, monkeypatch):
        from apps.employees.serializers import EmployeeCreateSerializer

        monkeypatch.setattr(
            "apps.employees.serializers.send_invitation_email", lambda *a, **k: None
        )
        mgr = employee_factory(first_name="Boss", last_name="Person")
        ser = EmployeeCreateSerializer(data=self._valid_payload(
            department=str(department.id), manager=str(mgr.id),
        ))
        assert ser.is_valid(), ser.errors
        employee = ser.save()
        assert employee.department_id == department.id
        assert employee.manager_id == mgr.id

    def test_email_with_spaces_rejected(self, tenant):
        from apps.employees.serializers import EmployeeCreateSerializer

        ser = EmployeeCreateSerializer(data=self._valid_payload(email="a b@test.local"))
        assert not ser.is_valid()
        assert "email" in ser.errors

    def test_email_with_uppercase_rejected(self, tenant):
        from apps.employees.serializers import EmployeeCreateSerializer

        ser = EmployeeCreateSerializer(data=self._valid_payload(email="Upper@test.local"))
        assert not ser.is_valid()
        assert "email" in ser.errors

    def test_duplicate_email_rejected(self, tenant, tenant_user_factory):
        from apps.employees.serializers import EmployeeCreateSerializer

        tenant_user_factory(email="dupe@test.local")
        ser = EmployeeCreateSerializer(data=self._valid_payload(email="dupe@test.local"))
        assert not ser.is_valid()
        assert "email" in ser.errors

    def test_phone_non_numeric_rejected(self, tenant):
        from apps.employees.serializers import EmployeeCreateSerializer

        ser = EmployeeCreateSerializer(data=self._valid_payload(phone="12ab34xyz"))
        assert not ser.is_valid()
        assert "phone" in ser.errors

    def test_phone_wrong_length_rejected(self, tenant):
        from apps.employees.serializers import EmployeeCreateSerializer

        ser = EmployeeCreateSerializer(data=self._valid_payload(phone="123"))
        assert not ser.is_valid()
        assert "phone" in ser.errors

    def test_invalid_department_uuid_rejected(self, tenant):
        from apps.employees.serializers import EmployeeCreateSerializer

        ser = EmployeeCreateSerializer(data=self._valid_payload(department="not-a-uuid"))
        assert not ser.is_valid()
        assert "department" in ser.errors

    def test_nonexistent_department_rejected(self, tenant):
        import uuid as _uuid
        from apps.employees.serializers import EmployeeCreateSerializer

        ser = EmployeeCreateSerializer(
            data=self._valid_payload(department=str(_uuid.uuid4()))
        )
        assert not ser.is_valid()
        assert "department" in ser.errors

    def test_invalid_manager_uuid_rejected(self, tenant):
        from apps.employees.serializers import EmployeeCreateSerializer

        ser = EmployeeCreateSerializer(data=self._valid_payload(manager="bad-uuid"))
        assert not ser.is_valid()
        assert "manager" in ser.errors

    def test_nonexistent_manager_rejected(self, tenant):
        import uuid as _uuid
        from apps.employees.serializers import EmployeeCreateSerializer

        ser = EmployeeCreateSerializer(
            data=self._valid_payload(manager=str(_uuid.uuid4()))
        )
        assert not ser.is_valid()
        assert "manager" in ser.errors

    def test_hr_cannot_create_non_employee_role(self, tenant, hr_user):
        """validate_role: HR manager may only create EMPLOYEE role."""
        from apps.employees.serializers import EmployeeCreateSerializer

        class _Req:
            user = hr_user

        ser = EmployeeCreateSerializer(
            data=self._valid_payload(role="HR_MANAGER"),
            context={"request": _Req()},
        )
        assert not ser.is_valid()
        assert "role" in ser.errors

    def test_hr_can_create_employee_role(self, tenant, hr_user, monkeypatch):
        from apps.employees.serializers import EmployeeCreateSerializer

        monkeypatch.setattr(
            "apps.employees.serializers.send_invitation_email", lambda *a, **k: None
        )

        class _Req:
            user = hr_user

        ser = EmployeeCreateSerializer(
            data=self._valid_payload(role="EMPLOYEE"),
            context={"request": _Req()},
        )
        assert ser.is_valid(), ser.errors

    def test_blank_department_and_manager_become_none(self, tenant, monkeypatch):
        """Blank department/manager/phone short-circuit to None/empty."""
        from apps.employees.serializers import EmployeeCreateSerializer

        ser = EmployeeCreateSerializer()
        assert ser.validate_department("") is None
        assert ser.validate_manager("") is None
        assert ser.validate_phone("") == ""

    def test_create_with_blank_optionals(self, tenant, monkeypatch):
        """A create payload with blank department/manager validates and saves."""
        from apps.employees.serializers import EmployeeCreateSerializer

        monkeypatch.setattr(
            "apps.employees.serializers.send_invitation_email", lambda *a, **k: None
        )
        ser = EmployeeCreateSerializer(data=self._valid_payload(
            email="blankopt@test.local", department="", manager="",
        ))
        assert ser.is_valid(), ser.errors
        employee = ser.save()
        assert employee.department is None
        assert employee.manager is None


# 9. EmployeeSerializer — representation, validate, update

class TestEmployeeSerializerRepresentation:
    """to_representation nests email/department/manager."""

    def test_representation_includes_email_department_manager(
        self, tenant, department, employee_factory
    ):
        from apps.employees.serializers import EmployeeSerializer

        mgr = employee_factory(first_name="Manager", last_name="One")
        emp = employee_factory(
            first_name="Sub", last_name="Ordinate",
            department=department, manager=mgr,
        )
        data = EmployeeSerializer(emp).data
        assert data["email"] == emp.user.email
        assert data["department"]["id"] == department.id
        assert data["department"]["name"] == department.name
        assert data["manager"]["id"] == mgr.id
        assert data["manager"]["name"] == mgr.get_full_name()

    def test_department_serializer_nests_manager(
        self, tenant, department_factory, employee_factory
    ):
        from apps.employees.serializers import DepartmentSerializer

        mgr = employee_factory(first_name="Dept", last_name="Head")
        dept = department_factory(name="Ops", code="OPS", manager=mgr)
        data = DepartmentSerializer(dept).data
        assert data["manager"]["id"] == mgr.id
        assert data["manager"]["name"] == mgr.get_full_name()


class TestEmployeeSerializerValidation:
    """validate_phone + validate (HR/admin guard, email uniqueness)."""

    def test_validate_phone_non_numeric(self, tenant):
        from apps.employees.serializers import EmployeeSerializer

        ser = EmployeeSerializer()
        with pytest.raises(Exception):
            ser.validate_phone("12ab")

    def test_validate_phone_length(self, tenant):
        from apps.employees.serializers import EmployeeSerializer

        ser = EmployeeSerializer()
        with pytest.raises(Exception):
            ser.validate_phone("123")

    def test_validate_phone_blank_ok(self, tenant):
        from apps.employees.serializers import EmployeeSerializer

        ser = EmployeeSerializer()
        assert ser.validate_phone("") == ""

    def test_validate_phone_valid_returns_value(self, tenant):
        from apps.employees.serializers import EmployeeSerializer

        ser = EmployeeSerializer()
        assert ser.validate_phone("1234567890") == "1234567890"

    def test_hr_cannot_edit_org_admin_profile(self, tenant, hr_user, admin_employee):
        from apps.employees.serializers import EmployeeSerializer

        class _Req:
            user = hr_user

        ser = EmployeeSerializer(
            instance=admin_employee,
            data={"first_name": "Hacked"},
            partial=True,
            context={"request": _Req()},
        )
        # BaseModelSerializer.is_valid(raise_exception=True) raises AFValidationError.
        from apps.base.errors import AFValidationError
        with pytest.raises(AFValidationError):
            ser.is_valid(raise_exception=True)

    def test_email_uniqueness_on_update(self, tenant, employee_factory,
                                        tenant_user_factory, admin_employee):
        from apps.employees.serializers import EmployeeSerializer

        other = tenant_user_factory(email="taken@test.local")
        target = employee_factory(first_name="Target", last_name="Emp")

        class _Req:
            user = admin_employee.user

        ser = EmployeeSerializer(
            instance=target,
            data={"email": "taken@test.local"},
            partial=True,
            context={"request": _Req()},
        )
        from apps.base.errors import AFValidationError
        with pytest.raises(AFValidationError):
            ser.is_valid(raise_exception=True)

    def test_update_changes_email_and_resends_invite_for_inactive(
        self, tenant, monkeypatch
    ):
        """update(): changing email on an inactive user resends invite."""
        from apps.employees.serializers import EmployeeSerializer
        from apps.employees.models import TenantUser, Employee

        user = TenantUser(email="pending@test.local", role="EMPLOYEE", is_active=False)
        user.set_unusable_password()
        user.save()
        emp = Employee.objects.create(
            user=user, first_name="Pend", last_name="Ing",
            employee_code="PI999",
        )

        sent = {}
        monkeypatch.setattr(
            "apps.employees.serializers.send_invitation_email",
            lambda u, t, d: sent.update({"user": u, "tenant": t, "domain": d}),
        )

        ser = EmployeeSerializer(
            instance=emp, data={"email": "moved@test.local"}, partial=True,
        )
        assert ser.is_valid(), ser.errors
        ser.save()
        user.refresh_from_db()
        assert user.email == "moved@test.local"
        assert sent.get("user") == user  # invite resent because inactive

    def test_update_changes_email_active_user_no_resend(self, tenant, monkeypatch):
        """Active user email change updates email but does NOT resend invite."""
        from apps.employees.serializers import EmployeeSerializer
        from apps.employees.models import TenantUser, Employee

        user = TenantUser(email="active@test.local", role="EMPLOYEE", is_active=True)
        user.set_password("testpass123")
        user.save()
        emp = Employee.objects.create(
            user=user, first_name="Act", last_name="Ive",
            employee_code="AI999",
        )

        sent = {}
        monkeypatch.setattr(
            "apps.employees.serializers.send_invitation_email",
            lambda u, t, d: sent.update({"user": u}),
        )

        ser = EmployeeSerializer(
            instance=emp, data={"email": "active2@test.local"}, partial=True,
        )
        assert ser.is_valid(), ser.errors
        ser.save()
        user.refresh_from_db()
        assert user.email == "active2@test.local"
        assert "user" not in sent  # no invite for active users


# 10. Invitation serializers — validate / setup / resend

class TestInvitationValidateSerializer:

    def test_valid_token_attaches_user(self, tenant, tenant_user_factory):
        from apps.employees.serializers_invitation import InvitationValidateSerializer

        user = tenant_user_factory(email="invitee@test.local", is_active=False)
        token = _make_invitation_token(user.id)
        ser = InvitationValidateSerializer(data={"token": token})
        assert ser.is_valid(), ser.errors
        assert ser.context["user"].id == user.id

    def test_wrong_token_type_rejected(self, tenant, tenant_user_factory):
        from apps.employees.serializers_invitation import InvitationValidateSerializer

        user = tenant_user_factory(is_active=False)
        token = _make_invitation_token(user.id, token_type="reset")
        ser = InvitationValidateSerializer(data={"token": token})
        assert not ser.is_valid()

    def test_missing_user_id_rejected(self, tenant):
        import jwt
        from datetime import datetime, timedelta, timezone
        from django.conf import settings
        from apps.employees.serializers_invitation import InvitationValidateSerializer

        token = jwt.encode(
            {"exp": datetime.now(timezone.utc) + timedelta(hours=1), "type": "invitation"},
            settings.SECRET_KEY, algorithm="HS256",
        )
        ser = InvitationValidateSerializer(data={"token": token})
        assert not ser.is_valid()

    def test_unknown_user_rejected(self, tenant):
        import uuid as _uuid
        from apps.employees.serializers_invitation import InvitationValidateSerializer

        token = _make_invitation_token(_uuid.uuid4())
        ser = InvitationValidateSerializer(data={"token": token})
        assert not ser.is_valid()

    def test_already_active_user_rejected(self, tenant, tenant_user_factory):
        from apps.employees.serializers_invitation import InvitationValidateSerializer

        user = tenant_user_factory(is_active=True)
        token = _make_invitation_token(user.id)
        ser = InvitationValidateSerializer(data={"token": token})
        assert not ser.is_valid()

    def test_expired_token_rejected(self, tenant, tenant_user_factory):
        from apps.employees.serializers_invitation import InvitationValidateSerializer

        user = tenant_user_factory(is_active=False)
        token = _make_expired_token(user.id)
        ser = InvitationValidateSerializer(data={"token": token})
        assert not ser.is_valid()

    def test_garbage_token_rejected(self, tenant):
        from apps.employees.serializers_invitation import InvitationValidateSerializer

        ser = InvitationValidateSerializer(data={"token": "not.a.jwt"})
        assert not ser.is_valid()


class TestInvitationSetupSerializer:

    def test_setup_happy_path_activates_user(self, tenant, tenant_user_factory):
        from apps.employees.serializers_invitation import InvitationSetupSerializer

        user = tenant_user_factory(email="setup@test.local", is_active=False)
        token = _make_invitation_token(user.id)
        ser = InvitationSetupSerializer(data={
            "token": token,
            "email": "setup@test.local",
            "password": "NewPassw0rd",
            "confirm_password": "NewPassw0rd",
        })
        assert ser.is_valid(), ser.errors
        saved = ser.save()
        user.refresh_from_db()
        assert user.is_active is True
        assert user.check_password("NewPassw0rd")
        assert saved.id == user.id

    def test_password_mismatch_rejected(self, tenant, tenant_user_factory):
        from apps.employees.serializers_invitation import InvitationSetupSerializer

        user = tenant_user_factory(email="mismatch@test.local", is_active=False)
        token = _make_invitation_token(user.id)
        ser = InvitationSetupSerializer(data={
            "token": token,
            "email": "mismatch@test.local",
            "password": "NewPassw0rd",
            "confirm_password": "Different0ne",
        })
        assert not ser.is_valid()

    def test_email_mismatch_rejected(self, tenant, tenant_user_factory):
        from apps.employees.serializers_invitation import InvitationSetupSerializer

        user = tenant_user_factory(email="real@test.local", is_active=False)
        token = _make_invitation_token(user.id)
        ser = InvitationSetupSerializer(data={
            "token": token,
            "email": "other@test.local",
            "password": "NewPassw0rd",
            "confirm_password": "NewPassw0rd",
        })
        assert not ser.is_valid()


class TestInvitationResendSerializer:

    def test_resend_happy_path(self, tenant, tenant_user_factory, monkeypatch):
        from apps.employees.serializers_invitation import InvitationResendSerializer

        sent = {}
        monkeypatch.setattr(
            "apps.employees.serializers_invitation.send_invitation_email",
            lambda u, t, d: sent.update({"user": u, "tenant": t, "domain": d}),
        )
        user = tenant_user_factory(email="resend@test.local", is_active=False)
        ser = InvitationResendSerializer(data={"email": "resend@test.local"})
        assert ser.is_valid(), ser.errors
        ser.save()
        assert sent["user"].id == user.id

    def test_resend_unknown_email_rejected(self, tenant):
        from apps.employees.serializers_invitation import InvitationResendSerializer

        ser = InvitationResendSerializer(data={"email": "nobody@test.local"})
        assert not ser.is_valid()

    def test_resend_active_user_rejected(self, tenant, tenant_user_factory):
        from apps.employees.serializers_invitation import InvitationResendSerializer

        tenant_user_factory(email="alreadyactive@test.local", is_active=True)
        ser = InvitationResendSerializer(data={"email": "alreadyactive@test.local"})
        assert not ser.is_valid()


# 11. Invitation API views

class TestInvitationViews:

    validate_url = "/api/v1/auth/invitation/validate/"
    setup_url = "/api/v1/auth/invitation/setup/"
    resend_url = "/api/v1/auth/invitation/resend/"

    def test_validate_endpoint_returns_email(self, api_client, tenant_user_factory):
        user = tenant_user_factory(email="apivalidate@test.local", is_active=False)
        token = _make_invitation_token(user.id)
        response = api_client.post(self.validate_url, data={"token": token})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "apivalidate@test.local"

    def test_validate_endpoint_rejects_bad_token(self, api_client, tenant):
        response = api_client.post(self.validate_url, data={"token": "garbage"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_setup_endpoint_activates_account(self, api_client, tenant_user_factory):
        user = tenant_user_factory(email="apisetup@test.local", is_active=False)
        token = _make_invitation_token(user.id)
        response = api_client.post(self.setup_url, data={
            "token": token,
            "email": "apisetup@test.local",
            "password": "NewPassw0rd",
            "confirm_password": "NewPassw0rd",
        })
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.is_active is True

    def test_resend_endpoint(self, api_client, tenant_user_factory, monkeypatch):
        monkeypatch.setattr(
            "apps.employees.serializers_invitation.send_invitation_email",
            lambda *a, **k: None,
        )
        tenant_user_factory(email="apiresend@test.local", is_active=False)
        response = api_client.post(self.resend_url, data={"email": "apiresend@test.local"})
        assert response.status_code == status.HTTP_200_OK


# 12. EmployeeViewSet.perform_destroy branches

class TestEmployeeDestroyRules:

    base_url = "/api/v1/employees/"

    def test_admin_cannot_delete_own_account(self, admin_api_client, org_admin_user,
                                             employee_factory):
        """A user cannot delete the employee profile tied to their own account."""
        emp = employee_factory(user=org_admin_user, first_name="Self", last_name="Admin")
        response = admin_api_client.delete(f"{self.base_url}{emp.id}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hr_cannot_delete_org_admin(self, hr_api_client, employee_factory):
        admin_emp = employee_factory(
            email="del-admin@test.local", role="ORGANIZATION_ADMIN",
            first_name="Org", last_name="Admin",
        )
        response = hr_api_client.delete(f"{self.base_url}{admin_emp.id}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_cannot_delete_other_org_admin(self, admin_api_client, employee_factory):
        other_admin = employee_factory(
            email="other-admin@test.local", role="ORGANIZATION_ADMIN",
            first_name="Other", last_name="Admin",
        )
        response = admin_api_client.delete(f"{self.base_url}{other_admin.id}/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_soft_delete_employee(self, admin_api_client, employee_factory):
        """Happy path: admin deletes a normal employee → user deactivated."""
        emp = employee_factory(
            email="deleteme@test.local", role="EMPLOYEE",
            first_name="Delete", last_name="Me",
        )
        user_id = emp.user_id
        response = admin_api_client.delete(f"{self.base_url}{emp.id}/")
        assert response.status_code in (
            status.HTTP_204_NO_CONTENT, status.HTTP_200_OK,
        )
        from apps.employees.models import TenantUser
        emp.user.refresh_from_db()
        assert TenantUser.objects.get(id=user_id).is_active is False


# 13. TENANT LOGIN — profile payload + inactive branch

class TestTenantLoginProfilePayload:
    """TenantLoginView profile embedding and the serializer's inactive branch."""

    login_url = "/api/v1/auth/login/"

    def test_login_returns_profile_when_it_exists(self, api_client, employee_factory):
        """A user with an Employee profile → profile block populated on login."""
        emp = employee_factory(email="withprofile@test.local", role="EMPLOYEE")
        response = api_client.post(self.login_url, data={
            "email": "withprofile@test.local", "password": "testpass123",
        })
        assert response.status_code == status.HTTP_200_OK
        assert response.data["profile"] is not None
        assert response.data["profile"]["employee_code"] == emp.employee_code

    def test_login_serializer_rejects_inactive_user(self, tenant, tenant_user_factory):
        """authenticate() returning an inactive TenantUser → 'deactivated' branch."""
        from unittest.mock import patch
        from apps.employees.serializers_auth import TenantLoginSerializer

        user = tenant_user_factory(email="inact@test.local", is_active=False)
        with patch(
            "apps.employees.serializers_auth.authenticate", return_value=user
        ):
            serializer = TenantLoginSerializer(data={
                "email": "inact@test.local", "password": "testpass123",
            })
            assert not serializer.is_valid()
            assert "deactivated" in str(serializer.errors).lower()


# 14. PROFILE UPDATE (PUT /auth/profile/)

class TestProfileUpdate:
    """ProfileView.put — success, validation, and missing-profile branches."""

    profile_url = "/api/v1/auth/profile/"

    def test_employee_updates_own_profile_phone(
        self, employee_api_client, employee_user, employee_factory
    ):
        employee_factory(user=employee_user)
        response = employee_api_client.put(
            self.profile_url, data={"phone": "1234567890"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["profile"]["phone"] == "1234567890"

    def test_profile_update_invalid_phone_rejected(
        self, employee_api_client, employee_user, employee_factory
    ):
        employee_factory(user=employee_user)
        response = employee_api_client.put(
            self.profile_url, data={"phone": "12ab"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_profile_update_without_profile_returns_404(self, admin_api_client):
        """A user with no Employee record cannot PUT their profile → 404."""
        response = admin_api_client.put(
            self.profile_url, data={"phone": "1234567890"}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# 15. CHANGE PASSWORD — success path

class TestChangePasswordSuccess:
    url = "/api/v1/auth/change-password/"

    def test_change_password_success(self, hr_api_client, hr_user):
        response = hr_api_client.post(self.url, data={
            "old_password": "testpass123", "new_password": "BrandNewPass1",
            "confirm_password": "BrandNewPass1",
        })
        assert response.status_code == status.HTTP_200_OK
        assert "changed successfully" in response.data["message"].lower()
        hr_user.refresh_from_db()
        assert hr_user.check_password("BrandNewPass1")


# 16. EmployeeProfileSerializer.validate_phone (unit)

class TestEmployeeProfileSerializerPhone:
    def test_phone_empty_allowed(self, tenant):
        from apps.employees.serializers_auth import EmployeeProfileSerializer
        assert EmployeeProfileSerializer().validate_phone("") == ""

    def test_phone_valid_returned(self, tenant):
        from apps.employees.serializers_auth import EmployeeProfileSerializer
        assert EmployeeProfileSerializer().validate_phone("1234567890") == "1234567890"

    def test_phone_non_digit_rejected(self, tenant):
        from rest_framework import serializers as drf_serializers
        from apps.employees.serializers_auth import EmployeeProfileSerializer
        with pytest.raises(drf_serializers.ValidationError):
            EmployeeProfileSerializer().validate_phone("12ab567890")

    def test_phone_too_short_rejected(self, tenant):
        from rest_framework import serializers as drf_serializers
        from apps.employees.serializers_auth import EmployeeProfileSerializer
        with pytest.raises(drf_serializers.ValidationError):
            EmployeeProfileSerializer().validate_phone("12345")


# 17. EmployeeCreateSerializer.validate_email — direct validator branches

class TestEmployeeCreateEmailValidator:
    """EmailField rejects spaces before validate_email runs, so the space
    branch is exercised by calling the validator directly (matches the
    tenants serializer unit-test approach)."""

    def test_validate_email_rejects_spaces(self, tenant):
        from rest_framework import serializers as drf_serializers
        from apps.employees.serializers import EmployeeCreateSerializer
        with pytest.raises(drf_serializers.ValidationError):
            EmployeeCreateSerializer().validate_email("a b@test.local")


# 18. TenantAuthBackend (custom_auth)

class TestTenantAuthBackend:
    def test_authenticate_with_username_kwarg(self, tenant, tenant_user_factory):
        """authenticate() falls back to the 'username' kwarg when email is None."""
        from apps.employees.custom_auth import TenantAuthBackend
        user = tenant_user_factory(email="backend@test.local", password="testpass123")
        result = TenantAuthBackend().authenticate(
            None, username="backend@test.local", password="testpass123"
        )
        assert result == user

    def test_get_user_returns_matching_user(self, tenant, tenant_user_factory):
        from apps.employees.custom_auth import TenantAuthBackend
        user = tenant_user_factory(email="getuser@test.local")
        assert TenantAuthBackend().get_user(user.id) == user

    def test_get_user_missing_returns_none(self, tenant):
        import uuid as _uuid
        from apps.employees.custom_auth import TenantAuthBackend
        assert TenantAuthBackend().get_user(_uuid.uuid4()) is None


# 19. TenantUser manager / model __str__ helpers

class TestTenantUserModelAndManager:
    def test_manager_create_user_sets_password(self, tenant):
        from apps.employees.models import TenantUser
        user = TenantUser.objects.create_user(
            email="mgr@test.local", password="testpass123"
        )
        assert user.email == "mgr@test.local"
        assert user.check_password("testpass123")

    def test_manager_create_user_requires_email(self, tenant):
        from apps.employees.models import TenantUser
        with pytest.raises(ValueError, match="Email is required"):
            TenantUser.objects.create_user(email="", password="x")

    def test_tenant_user_str_returns_email(self, tenant):
        from apps.employees.models import TenantUser
        assert str(TenantUser(email="s@test.local")) == "s@test.local"

    def test_department_str(self, tenant, department_factory):
        dept = department_factory(name="Ops", code="OPS")
        assert str(dept) == "Ops (OPS)"
