"""
Test Suite for Tenants module (public schema).

Covers:
- Tenant settings access by different roles
- Platform OrganizationViewSet (super admin org CRUD + activate/deactivate)
- Organization serializers (create / super admin update validation)
"""
import uuid
from unittest.mock import patch

import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestTenantsOrganizationSettings:
    """Organization settings API endpoint."""

    url = "/api/v1/organization/settings/"

    def test_unauthenticated_blocked(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_employee_cannot_modify(self, employee_api_client):
        """EMPLOYEE → blocked from org settings modification."""
        response = employee_api_client.put(self.url, data={"name": "Hacked"})
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

    def test_hr_cannot_write_settings(self, hr_api_client):
        """HR can read but not write org settings."""
        response = hr_api_client.put(self.url, data={"name": "Hacked"})
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

    def test_admin_can_read_settings(self, admin_api_client):
        """ORG_ADMIN reads their own org settings → 200 with derived subdomain."""
        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        # get_object returns request.tenant; to_representation derives subdomain.
        assert "subdomain" in response.data
        assert "name" in response.data

    def test_admin_can_update_contact_fields(self, admin_api_client):
        """ORG_ADMIN updates the editable contact fields → 200 and persists."""
        response = admin_api_client.put(
            self.url,
            data={
                "contact_email": "orgadmin@tenant.local",
                "contact_phone": "1234567890",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["contact_email"] == "orgadmin@tenant.local"
        assert response.data["contact_phone"] == "1234567890"

    def test_admin_update_invalid_phone_rejected(self, admin_api_client):
        """Non-numeric contact_phone → 400 (tenant serializer validation)."""
        response = admin_api_client.put(
            self.url,
            data={"contact_phone": "12ab"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Local fixtures for platform (public schema) tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def super_admin(public_tenant):
    """A platform super admin (accounts.User, is_superuser=True) in public schema."""
    from apps.accounts.models import User
    return User.objects.create_superuser(
        email=f"sa-{uuid.uuid4().hex[:8]}@platform.local",
        password="superpass123",
        first_name="Super",
    )


@pytest.fixture()
def platform_client(super_admin):
    """APIClient authenticated as a super admin on the public (localhost) domain."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient(SERVER_NAME="localhost")
    token = RefreshToken.for_user(super_admin)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


@pytest.fixture()
def public_client(public_tenant):
    """Unauthenticated client on the public (localhost) domain."""
    from rest_framework.test import APIClient
    return APIClient(SERVER_NAME="localhost")


@pytest.fixture()
def secondary_org(public_tenant):
    """A throwaway Organization + primary Domain for update/activate/destroy tests.

    Created WITHOUT going through the create serializer (no schema/user side
    effects). Cleaned up with force_drop to remove any schema at teardown.
    """
    from apps.tenants.models import Organization, Domain
    suffix = uuid.uuid4().hex[:8]
    org = Organization.objects.create(
        name="Secondary Org",
        schema_name=f"tenant_sec{suffix}",
        contact_email="sec@platform.local",
        is_active=True,
    )
    Domain.objects.create(
        domain=f"sec{suffix}.localhost", tenant=org, is_primary=True
    )
    yield org
    try:
        org.delete(force_drop=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# OrganizationViewSet — permissions
# ---------------------------------------------------------------------------

class TestOrganizationViewSetPermissions:
    url = "/api/v1/platform/organizations/"

    def test_unauthenticated_blocked(self, public_client):
        """No JWT → 401."""
        response = public_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_superadmin_forbidden(self, public_tenant, org_admin_user):
        """A tenant user token (non-superuser) hitting platform routes → 401/403.

        The tenant user does not exist in the public schema's accounts.User
        table, so TenantJWTAuthentication rejects it in the public schema.
        """
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        client = APIClient(SERVER_NAME="localhost")
        token = RefreshToken.for_user(org_admin_user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        response = client.get(self.url)
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
        ]

    def test_non_superuser_account_forbidden(self, public_tenant):
        """A public-schema account that is NOT a superuser → 403."""
        from apps.accounts.models import User
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        user = User.objects.create_user(
            email=f"plain-{uuid.uuid4().hex[:6]}@platform.local",
            password="userpass123",
            first_name="Plain",
        )
        client = APIClient(SERVER_NAME="localhost")
        token = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        response = client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# OrganizationViewSet — list / retrieve / update
# ---------------------------------------------------------------------------

class TestOrganizationViewSetReadUpdate:
    url = "/api/v1/platform/organizations/"

    def test_list_organizations(self, platform_client):
        """Super admin can list organizations."""
        response = platform_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data

    def test_retrieve_organization(self, platform_client, secondary_org):
        """Retrieve a single org → includes derived subdomain."""
        response = platform_client.get(f"{self.url}{secondary_org.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Secondary Org"
        # to_representation derives subdomain from the primary domain
        assert response.data["subdomain"].startswith("sec")

    def test_update_name_and_contact(self, platform_client, secondary_org):
        """PUT updates base fields via the super admin update serializer."""
        response = platform_client.put(
            f"{self.url}{secondary_org.id}/",
            data={
                "name": "Renamed Org",
                "contact_email": "new@platform.local",
                "contact_phone": "1234567890",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        secondary_org.refresh_from_db()
        assert secondary_org.name == "Renamed Org"
        assert secondary_org.contact_email == "new@platform.local"

    def test_update_invalid_phone_rejected(self, platform_client, secondary_org):
        """Non-numeric contact_phone → 400."""
        response = platform_client.put(
            f"{self.url}{secondary_org.id}/",
            data={"name": "X", "contact_phone": "12ab"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_invalid_subdomain_rejected(self, platform_client, secondary_org):
        """Subdomain with special characters → 400."""
        response = platform_client.put(
            f"{self.url}{secondary_org.id}/",
            data={"name": "X", "subdomain": "bad_sub!"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_duplicate_subdomain_rejected(self, platform_client, secondary_org):
        """Subdomain already used by the test tenant ('test') → 400."""
        response = platform_client.put(
            f"{self.url}{secondary_org.id}/",
            data={"name": "X", "subdomain": "test"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_patch_not_allowed(self, platform_client, secondary_org):
        """PATCH is excluded from http_method_names → 405."""
        response = platform_client.patch(
            f"{self.url}{secondary_org.id}/", data={"name": "Y"}, format="json"
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ---------------------------------------------------------------------------
# OrganizationViewSet — activate / deactivate
# ---------------------------------------------------------------------------

class TestOrganizationActivateDeactivate:
    url = "/api/v1/platform/organizations/"

    def test_deactivate_active_org(self, platform_client, secondary_org):
        """Deactivating an active org → is_active False."""
        response = platform_client.post(f"{self.url}{secondary_org.id}/deactivate/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_active"] is False
        assert "deactivated successfully" in response.data["message"].lower()
        secondary_org.refresh_from_db()
        assert secondary_org.is_active is False

    def test_deactivate_already_inactive(self, platform_client, secondary_org):
        """Deactivating an already-inactive org → 'already inactive' branch."""
        secondary_org.is_active = False
        secondary_org.save(update_fields=["is_active"])
        response = platform_client.post(f"{self.url}{secondary_org.id}/deactivate/")
        assert response.status_code == status.HTTP_200_OK
        assert "already inactive" in response.data["message"].lower()
        assert response.data["is_active"] is False

    def test_activate_inactive_org(self, platform_client, secondary_org):
        """Activating an inactive org → is_active True."""
        secondary_org.is_active = False
        secondary_org.save(update_fields=["is_active"])
        response = platform_client.post(f"{self.url}{secondary_org.id}/activate/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_active"] is True
        assert "activated successfully" in response.data["message"].lower()
        secondary_org.refresh_from_db()
        assert secondary_org.is_active is True

    def test_activate_already_active(self, platform_client, secondary_org):
        """Activating an already-active org → 'already active' branch."""
        response = platform_client.post(f"{self.url}{secondary_org.id}/activate/")
        assert response.status_code == status.HTTP_200_OK
        assert "already active" in response.data["message"].lower()
        assert response.data["is_active"] is True

    def test_activate_requires_auth(self, public_client, secondary_org):
        """Unauthenticated activate → 401."""
        response = public_client.post(f"{self.url}{secondary_org.id}/activate/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# OrganizationViewSet — destroy
# ---------------------------------------------------------------------------

class TestOrganizationDestroy:
    url = "/api/v1/platform/organizations/"

    def test_destroy_organization(self, platform_client, public_tenant):
        """DELETE removes the org and drops its schema.

        The real force_drop happens against a schema created inside the same
        test transaction, which Postgres refuses (pending trigger events). We
        patch the tenant delete to a plain row-delete so the view's destroy
        flow (get_object → perform_destroy → success Response) is exercised.
        """
        from apps.tenants.models import Organization, Domain
        from django.db.models import Model
        suffix = uuid.uuid4().hex[:8]
        org = Organization.objects.create(
            name="Deletable Org",
            schema_name=f"tenant_del{suffix}",
            is_active=True,
        )
        Domain.objects.create(
            domain=f"del{suffix}.localhost", tenant=org, is_primary=True
        )
        org_id = org.id

        def _plain_delete(self, *args, **kwargs):
            return Model.delete(self)

        with patch.object(Organization, "delete", _plain_delete):
            response = platform_client.delete(f"{self.url}{org_id}/")
        assert response.status_code == status.HTTP_200_OK
        assert "deleted successfully" in response.data["message"].lower()
        assert not Organization.objects.filter(id=org_id).exists()


# ---------------------------------------------------------------------------
# OrganizationViewSet — create (full flow, mocked invitation email)
# ---------------------------------------------------------------------------

class TestOrganizationCreate:
    url = "/api/v1/platform/organizations/"

    def test_create_organization_success(self, platform_client, public_tenant):
        """POST creates org + schema + domain + pending admin (email mocked)."""
        from apps.tenants.models import Organization, Domain
        subdomain = f"neworg{uuid.uuid4().hex[:6]}"
        created_org = None
        try:
            with patch("apps.tenants.serializers.send_invitation_email") as mock_email:
                response = platform_client.post(
                    self.url,
                    data={
                        "name": "Brand New Org",
                        "subdomain": subdomain,
                        "org_admin_email": "founder@example.com",
                    },
                    format="json",
                )
            assert response.status_code == status.HTTP_201_CREATED, response.data
            assert response.data["name"] == "Brand New Org"
            mock_email.assert_called_once()

            created_org = Organization.objects.get(schema_name=f"tenant_{subdomain}")
            assert Domain.objects.filter(
                domain=f"{subdomain}.localhost", tenant=created_org
            ).exists()
        finally:
            if created_org is not None:
                try:
                    created_org.delete(force_drop=True)
                except Exception:
                    pass

    def test_create_duplicate_subdomain_rejected(self, platform_client, public_tenant):
        """Subdomain matching the existing test tenant ('test') → 400."""
        with patch("apps.tenants.serializers.send_invitation_email"):
            response = platform_client.post(
                self.url,
                data={
                    "name": "Dup Org",
                    "subdomain": "test",
                    "org_admin_email": "dup@example.com",
                },
                format="json",
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_invalid_subdomain_rejected(self, platform_client, public_tenant):
        """Subdomain with special chars → 400."""
        with patch("apps.tenants.serializers.send_invitation_email"):
            response = platform_client.post(
                self.url,
                data={
                    "name": "Bad Org",
                    "subdomain": "bad-sub!",
                    "org_admin_email": "bad@example.com",
                },
                format="json",
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_uppercase_email_rejected(self, platform_client, public_tenant):
        """Uppercase admin email → 400 (validate_org_admin_email)."""
        with patch("apps.tenants.serializers.send_invitation_email"):
            response = platform_client.post(
                self.url,
                data={
                    "name": "Case Org",
                    "subdomain": f"caseorg{uuid.uuid4().hex[:6]}",
                    "org_admin_email": "Founder@example.com",
                },
                format="json",
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_missing_required_fields(self, platform_client, public_tenant):
        """Missing subdomain + org_admin_email → 400."""
        with patch("apps.tenants.serializers.send_invitation_email"):
            response = platform_client.post(
                self.url, data={"name": "Incomplete"}, format="json"
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Serializer unit tests
# ---------------------------------------------------------------------------

class TestOrganizationSerializerValidation:
    """Direct unit tests for organization serializer validators."""

    def test_create_subdomain_validation_rejects_specials(self, public_tenant):
        from apps.tenants.serializers import OrganizationCreateSerializer
        from rest_framework import serializers as drf_serializers
        s = OrganizationCreateSerializer()
        with pytest.raises(drf_serializers.ValidationError):
            s.validate_subdomain("Bad Sub!")

    def test_create_subdomain_validation_duplicate(self, public_tenant):
        from apps.tenants.serializers import OrganizationCreateSerializer
        from rest_framework import serializers as drf_serializers
        s = OrganizationCreateSerializer()
        # 'test.localhost' already exists (test tenant)
        with pytest.raises(drf_serializers.ValidationError):
            s.validate_subdomain("test")

    def test_create_email_validation_rejects_spaces(self, public_tenant):
        from apps.tenants.serializers import OrganizationCreateSerializer
        from rest_framework import serializers as drf_serializers
        s = OrganizationCreateSerializer()
        with pytest.raises(drf_serializers.ValidationError):
            s.validate_org_admin_email("a b@example.com")

    def test_create_email_validation_rejects_uppercase(self, public_tenant):
        from apps.tenants.serializers import OrganizationCreateSerializer
        from rest_framework import serializers as drf_serializers
        s = OrganizationCreateSerializer()
        with pytest.raises(drf_serializers.ValidationError):
            s.validate_org_admin_email("Founder@example.com")

    def test_superadmin_phone_validation(self, public_tenant):
        from apps.tenants.serializers import OrganizationSuperAdminUpdateSerializer
        from rest_framework import serializers as drf_serializers
        s = OrganizationSuperAdminUpdateSerializer()
        assert s.validate_contact_phone("") == ""
        assert s.validate_contact_phone("1234567890") == "1234567890"
        with pytest.raises(drf_serializers.ValidationError):
            s.validate_contact_phone("12ab")
        with pytest.raises(drf_serializers.ValidationError):
            s.validate_contact_phone("123")

    def test_superadmin_email_validation(self, public_tenant):
        from apps.tenants.serializers import OrganizationSuperAdminUpdateSerializer
        from rest_framework import serializers as drf_serializers
        s = OrganizationSuperAdminUpdateSerializer()
        assert s.validate_org_admin_email("ok@example.com") == "ok@example.com"
        with pytest.raises(drf_serializers.ValidationError):
            s.validate_org_admin_email("Bad@example.com")
        with pytest.raises(drf_serializers.ValidationError):
            s.validate_org_admin_email("a b@example.com")

    def test_superadmin_update_renames_schema_and_admin_email(self, secondary_org):
        """update() with a new subdomain renames schema + domain and updates admin email."""
        from apps.tenants.serializers import OrganizationSuperAdminUpdateSerializer
        from apps.tenants.models import Domain
        from apps.employees.models import TenantUser
        from django_tenants.utils import tenant_context

        # Seed an org admin in the secondary org's schema.
        with tenant_context(secondary_org):
            TenantUser.objects.create(
                email="old-admin@example.com",
                role=TenantUser.Role.ORGANIZATION_ADMIN,
            )

        new_sub = f"renamed{uuid.uuid4().hex[:6]}"
        serializer = OrganizationSuperAdminUpdateSerializer(
            instance=secondary_org,
            data={
                "name": "Updated Name",
                "subdomain": new_sub,
                "org_admin_email": "new-admin@example.com",
            },
            partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        org = serializer.save()

        assert org.schema_name == f"tenant_{new_sub}"
        assert Domain.objects.filter(
            domain=f"{new_sub}.localhost", tenant=org, is_primary=True
        ).exists()
        with tenant_context(org):
            assert TenantUser.objects.filter(email="new-admin@example.com").exists()

    def test_superadmin_to_representation_subdomain(self, secondary_org):
        """to_representation derives subdomain from the primary domain."""
        from apps.tenants.serializers import OrganizationSuperAdminUpdateSerializer
        data = OrganizationSuperAdminUpdateSerializer(secondary_org).data
        assert data["subdomain"].startswith("sec")

    def test_tenant_update_serializer_phone_and_repr(self, secondary_org):
        """OrganizationTenantUpdateSerializer phone validation + subdomain repr."""
        from apps.tenants.serializers import OrganizationTenantUpdateSerializer
        from rest_framework import serializers as drf_serializers
        s = OrganizationTenantUpdateSerializer()
        assert s.validate_contact_phone("") == ""
        assert s.validate_contact_phone("1234567890") == "1234567890"
        with pytest.raises(drf_serializers.ValidationError):
            s.validate_contact_phone("abc")
        data = OrganizationTenantUpdateSerializer(secondary_org).data
        assert data["subdomain"].startswith("sec")

    def test_domain_serializer_fields(self, secondary_org):
        """DomainSerializer serializes the primary domain."""
        from apps.tenants.serializers import DomainSerializer
        from apps.tenants.models import Domain
        domain = Domain.objects.filter(tenant=secondary_org, is_primary=True).first()
        data = DomainSerializer(domain).data
        assert data["domain"].startswith("sec")
        assert data["is_primary"] is True
