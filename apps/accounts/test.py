"""
Tests for Accounts, Audit, Search, Tenants, and Reports modules.

Covers:
- Platform auth (public schema Super Admin login)
- Audit log access (admin-only, read-only)
- Global search permissions and results
- Tenant settings access (org admin only)
- Dashboard report permissions
- Soft-delete behavior
"""
import pytest
from unittest.mock import patch
from rest_framework import status

pytestmark = pytest.mark.django_db


# 1. ACCOUNTS (Tenant Auth Duplication & Soft-Delete)

class TestAccountsAuth:
    """Account-level auth and soft-delete tests."""

    def test_soft_deleted_user_cannot_login(self, api_client, tenant_user_factory):
        """Deactivated user gets blocked at login."""
        user = tenant_user_factory(email="deactivated@test.local")
        user.is_active = False
        user.save()

        response = api_client.post("/api/v1/auth/login/", data={
            "email": "deactivated@test.local",
            "password": "testpass123",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 2. AUDIT LOGS

class TestAuditLogs:
    """Audit log access is restricted to ORG_ADMIN only."""

    url = "/api/v1/audit-logs/"

    def test_unauthenticated_cannot_view_audit_logs(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_cannot_view_audit_logs(self, employee_api_client):
        """EMPLOYEE → 403."""
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hr_cannot_view_audit_logs(self, hr_api_client):
        """HR_MANAGER → 403."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_view_audit_logs(self, admin_api_client):
        """ORG_ADMIN → 200."""
        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK


# 3. GLOBAL SEARCH

class TestGlobalSearch:
    """Global search endpoint access and behavior."""

    url = "/api/v1/search/"

    def test_unauthenticated_cannot_search(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(f"{self.url}?q=test")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_empty_query_returns_empty_results(self, hr_api_client):
        """Empty query → empty results (not error)."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_search_finds_assets_by_name(self, hr_api_client, asset):
        """Search for asset name → returns result with type ASSET."""
        response = hr_api_client.get(f"{self.url}?q={asset.name}")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        types = [r["type"] for r in results]
        assert "ASSET" in types

    def test_search_finds_assets_by_code(self, hr_api_client, asset):
        """Search by asset_code → returns result."""
        response = hr_api_client.get(f"{self.url}?q={asset.asset_code}")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1

    def test_search_finds_employees(self, hr_api_client, employee):
        """Search for employee name → EMPLOYEE result."""
        response = hr_api_client.get(f"{self.url}?q={employee.first_name}")
        assert response.status_code == status.HTTP_200_OK
        types = [r["type"] for r in response.data["results"]]
        assert "EMPLOYEE" in types

    def test_search_no_match_returns_empty(self, hr_api_client):
        """Gibberish query → no results (not error)."""
        response = hr_api_client.get(f"{self.url}?q=xyznonexistent999")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []


# 4. TENANT SETTINGS

class TestTenantSettings:
    """Organization settings access control."""

    url = "/api/v1/organization/settings/"

    def test_unauthenticated_blocked(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_employee_cannot_modify_settings(self, employee_api_client):
        """EMPLOYEE cannot modify organization settings."""
        response = employee_api_client.put(self.url, data={"name": "Hacked"})
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]


# 5. DASHBOARD REPORTS

class TestDashboardReports:
    """Dashboard summary endpoint access."""

    url = "/api/v1/reports/dashboard/"

    def test_unauthenticated_cannot_view_dashboard(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_cannot_view_dashboard(self, employee_api_client):
        """EMPLOYEE → 403."""
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hr_cannot_view_dashboard(self, hr_api_client):
        """HR_MANAGER → 403 (admin only)."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_view_dashboard(self, admin_api_client):
        """ORG_ADMIN → 200 with stats data."""
        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert "assets" in data
        assert "employees" in data
        assert "requests" in data
        assert "incidents" in data
        assert "licenses" in data
        assert "allocations" in data

    def test_dashboard_counts_are_integers(self, admin_api_client):
        """All dashboard values should be integers."""
        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        for section in response.data.values():
            if isinstance(section, dict):
                for value in section.values():
                    assert isinstance(value, int)


# ---------------------------------------------------------------------------
# Local fixtures for platform (public schema) auth tests
# ---------------------------------------------------------------------------

import uuid


@pytest.fixture()
def super_admin_factory(public_tenant):
    """Factory for creating platform super admins in the public schema."""
    from apps.accounts.models import User

    def _create(email=None, password="superpass123", is_active=True, **kwargs):
        email = email or f"sa-{uuid.uuid4().hex[:8]}@platform.local"
        user = User.objects.create_superuser(
            email=email, password=password, first_name="Super", **kwargs
        )
        if not is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
        return user

    return _create


@pytest.fixture()
def platform_user_factory(public_tenant):
    """Factory for a NON-superuser account in the public schema."""
    from apps.accounts.models import User

    def _create(email=None, password="userpass123", **kwargs):
        email = email or f"pu-{uuid.uuid4().hex[:8]}@platform.local"
        return User.objects.create_user(
            email=email, password=password, first_name="Plain", **kwargs
        )

    return _create


# 6. PLATFORM LOGIN (Super Admin, public schema)

class TestPlatformLoginView:
    """PlatformLoginView — /api/v1/platform/auth/login/ on the public domain."""

    url = "/api/v1/platform/auth/login/"

    def _client(self):
        from rest_framework.test import APIClient
        return APIClient(SERVER_NAME="localhost")

    def test_super_admin_login_success(self, super_admin_factory):
        """Valid super admin credentials → 200 with tokens + user payload."""
        super_admin_factory(email="admin@platform.local", password="superpass123")
        response = self._client().post(self.url, data={
            "email": "admin@platform.local",
            "password": "superpass123",
        })
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["user"]["email"] == "admin@platform.local"
        assert response.data["user"]["role"] == "SUPER_ADMIN"

    def test_login_normalizes_email_case(self, super_admin_factory):
        """Email is lowercased/stripped before authenticating."""
        super_admin_factory(email="mixed@platform.local", password="superpass123")
        response = self._client().post(self.url, data={
            "email": "  MIXED@platform.local  ",
            "password": "superpass123",
        })
        assert response.status_code == status.HTTP_200_OK

    def test_non_superuser_login_forbidden(self, platform_user_factory):
        """A valid but non-superuser account → 403."""
        platform_user_factory(email="plain@platform.local", password="userpass123")
        response = self._client().post(self.url, data={
            "email": "plain@platform.local",
            "password": "userpass123",
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "super admins only" in response.data["message"].lower()

    def test_invalid_password_rejected(self, super_admin_factory):
        """Wrong password → 400 validation error."""
        super_admin_factory(email="admin2@platform.local", password="superpass123")
        # In the public schema the fallback TenantAuthBackend has no
        # employees_tenantuser table, so isolate authentication to the
        # ModelBackend to exercise the serializer's invalid-credentials branch.
        with patch(
            "apps.employees.custom_auth.TenantAuthBackend.authenticate",
            return_value=None,
        ):
            response = self._client().post(self.url, data={
                "email": "admin2@platform.local",
                "password": "wrongpass",
            })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unknown_email_rejected(self, public_tenant):
        """Non-existent user → 400 validation error."""
        with patch(
            "apps.employees.custom_auth.TenantAuthBackend.authenticate",
            return_value=None,
        ):
            response = self._client().post(self.url, data={
                "email": "nobody@platform.local",
                "password": "whatever123",
            })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_inactive_super_admin_rejected(self, super_admin_factory):
        """Deactivated account → 400 (LoginSerializer active check)."""
        super_admin_factory(
            email="inactive@platform.local", password="superpass123", is_active=False
        )
        with patch(
            "apps.employees.custom_auth.TenantAuthBackend.authenticate",
            return_value=None,
        ):
            response = self._client().post(self.url, data={
                "email": "inactive@platform.local",
                "password": "superpass123",
            })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_fields_rejected(self, public_tenant):
        """Missing email/password → 400."""
        response = self._client().post(self.url, data={"email": "x@platform.local"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 7. TOKEN REFRESH (public schema)

class TestTokenRefreshView:
    """TokenRefreshView — /api/v1/platform/auth/token/refresh/."""

    url = "/api/v1/platform/auth/token/refresh/"

    def _client(self):
        from rest_framework.test import APIClient
        return APIClient(SERVER_NAME="localhost")

    def test_refresh_success(self, super_admin_factory):
        """Valid refresh token → 200 with fresh access/refresh."""
        from rest_framework_simplejwt.tokens import RefreshToken
        user = super_admin_factory()
        refresh = RefreshToken.for_user(user)
        response = self._client().post(self.url, data={"refresh": str(refresh)})
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_missing_refresh_token(self, public_tenant):
        """No refresh token in body → 400."""
        response = self._client().post(self.url, data={})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "required" in response.data["message"].lower()

    def test_invalid_refresh_token(self, public_tenant):
        """Garbage refresh token → 401."""
        response = self._client().post(self.url, data={"refresh": "not-a-real-token"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "invalid" in response.data["message"].lower()


# 8. LOGIN SERIALIZER (unit)

class TestLoginSerializer:
    """LoginSerializer.validate branches."""

    def test_valid_credentials_attach_user(self, super_admin_factory):
        from apps.accounts.serializers import LoginSerializer
        user = super_admin_factory(email="ls@platform.local", password="superpass123")
        serializer = LoginSerializer(data={
            "email": "ls@platform.local", "password": "superpass123",
        })
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["user"] == user

    def test_invalid_credentials_error(self, super_admin_factory):
        from apps.accounts.serializers import LoginSerializer
        super_admin_factory(email="ls2@platform.local", password="superpass123")
        with patch(
            "apps.employees.custom_auth.TenantAuthBackend.authenticate",
            return_value=None,
        ):
            serializer = LoginSerializer(data={
                "email": "ls2@platform.local", "password": "nope",
            })
            assert not serializer.is_valid()

    def test_inactive_user_error(self, super_admin_factory):
        from apps.accounts.serializers import LoginSerializer
        super_admin_factory(
            email="ls3@platform.local", password="superpass123", is_active=False
        )
        with patch(
            "apps.employees.custom_auth.TenantAuthBackend.authenticate",
            return_value=None,
        ):
            serializer = LoginSerializer(data={
                "email": "ls3@platform.local", "password": "superpass123",
            })
            assert not serializer.is_valid()
            assert "invalid email or password" in str(serializer.errors).lower()


# 9. USER SERIALIZER (unit)

class TestUserSerializer:
    """UserSerializer field validation."""

    def test_serialize_user_fields(self, super_admin_factory):
        from apps.accounts.serializers import UserSerializer
        user = super_admin_factory(email="us@platform.local")
        data = UserSerializer(user).data
        assert data["email"] == "us@platform.local"
        assert data["role"] == "SUPER_ADMIN"
        assert set(["id", "email", "role", "is_active"]).issubset(data.keys())

    def test_validate_phone_accepts_valid(self, public_tenant):
        from apps.accounts.serializers import UserSerializer
        serializer = UserSerializer()
        assert serializer.validate_phone("1234567890") == "1234567890"

    def test_validate_phone_empty_allowed(self, public_tenant):
        from apps.accounts.serializers import UserSerializer
        serializer = UserSerializer()
        assert serializer.validate_phone("") == ""

    def test_validate_phone_rejects_non_digits(self, public_tenant):
        from rest_framework import serializers as drf_serializers
        from apps.accounts.serializers import UserSerializer
        serializer = UserSerializer()
        with pytest.raises(drf_serializers.ValidationError):
            serializer.validate_phone("12ab567890")

    def test_validate_phone_rejects_too_short(self, public_tenant):
        from rest_framework import serializers as drf_serializers
        from apps.accounts.serializers import UserSerializer
        serializer = UserSerializer()
        with pytest.raises(drf_serializers.ValidationError):
            serializer.validate_phone("12345")


# 10. INVITATION EMAIL (accounts.utils.send_invitation_email)

class TestSendInvitationEmail:
    """send_invitation_email builds a 1-hour JWT setup link and dispatches mail."""

    def _fake_user(self, first_name="Alice"):
        """Lightweight stand-in — the util only reads .id, .email, .first_name."""
        from types import SimpleNamespace
        return SimpleNamespace(
            id=uuid.uuid4(), email="invitee@example.com", first_name=first_name
        )

    def test_sends_email_with_named_greeting(self):
        """A user with a first_name → personalised greeting + one send_mail call."""
        from apps.accounts import utils
        user = self._fake_user(first_name="Alice")
        with patch("apps.accounts.utils.send_mail") as mock_send:
            utils.send_invitation_email(user, "Acme Corp", "acme.localhost")

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        assert kwargs["recipient_list"] == ["invitee@example.com"]
        assert "Acme Corp" in kwargs["subject"]
        assert "Hello Alice," in kwargs["message"]
        assert "Acme Corp Team <" in kwargs["from_email"]
        assert kwargs["fail_silently"] is False

    def test_sends_email_with_generic_greeting_when_no_name(self):
        """Empty first_name → falls back to the 'Sir/Ma'am' greeting branch."""
        from apps.accounts import utils
        user = self._fake_user(first_name="")
        with patch("apps.accounts.utils.send_mail") as mock_send:
            utils.send_invitation_email(user, "Acme Corp", "acme.localhost")

        kwargs = mock_send.call_args.kwargs
        assert "Sir/Ma'am" in kwargs["message"]

    def test_setup_link_embeds_valid_invitation_token(self):
        """The setup URL carries a decodable JWT with the user id + invitation type."""
        import jwt
        from django.conf import settings
        from apps.accounts import utils

        user = self._fake_user()
        with patch("apps.accounts.utils.send_mail") as mock_send:
            utils.send_invitation_email(user, "Acme Corp", "acme.localhost")

        html = mock_send.call_args.kwargs["html_message"]
        # Extract the token from the setup URL embedded in the HTML body.
        token = html.split("setup-account?token=")[1].split('"')[0]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["user_id"] == str(user.id)
        assert payload["type"] == "invitation"


# 11. LOGIN SERIALIZER — inactive account branch

class TestLoginSerializerInactiveBranch:
    """The dedicated 'deactivated' branch fires when authenticate() yields an
    inactive user (distinct from the invalid-credentials path)."""

    def test_inactive_user_rejected_with_deactivated_message(self, public_tenant):
        from types import SimpleNamespace
        from apps.accounts.serializers import LoginSerializer

        inactive_user = SimpleNamespace(is_active=False)
        with patch(
            "apps.accounts.serializers.authenticate", return_value=inactive_user
        ):
            serializer = LoginSerializer(data={
                "email": "ghost@platform.local", "password": "whatever123",
            })
            assert not serializer.is_valid()
            assert "deactivated" in str(serializer.errors).lower()


# 12. USER MODEL / MANAGER (unit)

class TestUserModelAndManager:
    """UserManager guards and User display helpers."""

    def test_create_user_without_email_raises(self, public_tenant):
        from apps.accounts.models import User
        with pytest.raises(ValueError, match="Email is required"):
            User.objects.create_user(email="", password="x")

    def test_str_returns_email(self, public_tenant):
        from apps.accounts.models import User
        user = User(email="who@platform.local", first_name="Who")
        assert str(user) == "who@platform.local"

    def test_get_full_name_combines_names(self, public_tenant):
        from apps.accounts.models import User
        user = User(email="fn@platform.local", first_name="Jane", last_name="Doe")
        assert user.get_full_name() == "Jane Doe"

    def test_get_full_name_falls_back_to_email(self, public_tenant):
        from apps.accounts.models import User
        user = User(email="fallback@platform.local", first_name="", last_name="")
        assert user.get_full_name() == "fallback@platform.local"
