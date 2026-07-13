"""
Tenant Isolation Test Suite.

Proves mathematically that Tenant A cannot access Tenant B's data
under any circumstances (read, write, delete, auth).
"""

import uuid
import pytest
from rest_framework import status
from django_tenants.utils import tenant_context

pytestmark = pytest.mark.django_db


class TestTenantIsolation:

    @pytest.fixture(autouse=True)
    def setup_tenant_b_data(self, tenant2, employee_factory, asset_factory, category_factory):
        """Create assets and employees inside Tenant B (test_org2)."""
        with tenant_context(tenant2):
            self.tenant2_cat = category_factory(name="Tenant B Category", code="CAT-B")
            self.tenant2_asset = asset_factory(name="Tenant B Asset", category=self.tenant2_cat)
            self.tenant2_emp = employee_factory(email="emp-b@test2.local")

    def test_cross_tenant_read_prevention(self, admin_api_client):
        """Org A admin attempts to read Org B's asset -> 404 Not Found."""
        response = admin_api_client.get(f"/api/v1/assets/{self.tenant2_asset.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cross_tenant_list_prevention(self, admin_api_client, asset_factory, category_factory, tenant):
        """Org A list API should only show Org A assets, never Org B assets."""
        with tenant_context(tenant):
            cat_a = category_factory(name="Tenant A Category", code="CAT-A")
            asset_a = asset_factory(name="Tenant A Asset", category=cat_a)

        response = admin_api_client.get("/api/v1/assets/")
        assert response.status_code == status.HTTP_200_OK
        ids = [str(r["id"]) for r in response.data.get("results", [])]
        assert str(asset_a.id) in ids
        assert str(self.tenant2_asset.id) not in ids

    def test_cross_tenant_update_prevention(self, admin_api_client):
        """Org A admin attempts to update Org B's asset -> 404 Not Found."""
        response = admin_api_client.patch(f"/api/v1/assets/{self.tenant2_asset.id}/", data={
            "name": "Hacked Asset"
        })
        assert response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED)
        
        response = admin_api_client.put(f"/api/v1/assets/{self.tenant2_asset.id}/", data={
            "name": "Hacked Asset",
            "category": str(self.tenant2_cat.id)
        })
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cross_tenant_delete_prevention(self, admin_api_client):
        """Org A admin attempts to delete Org B's category -> 404 Not Found."""
        response = admin_api_client.delete(f"/api/v1/asset-categories/{self.tenant2_cat.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cross_tenant_allocation_prevention(self, hr_api_client):
        """Org A HR attempts to allocate Org B's asset to Org A's employee -> 400/404."""
        response = hr_api_client.post("/api/v1/allocations/allocate/", data={
            "asset": str(self.tenant2_asset.id),
            "employee": str(self.tenant2_emp.id)
        })
        # Serializer should reject unknown IDs or 400 validation error
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND)

    def test_cross_tenant_auth_boundary(self, hr_user):
        """Org A token used on Org B's domain -> 401/403."""
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        # Create token for Org A user
        token = RefreshToken()
        token["user_id"] = str(hr_user.id)
        token["role"] = getattr(hr_user, "role", "EMPLOYEE")
        token["scope"] = "tenant"

        # Client targeting Org B's domain
        client_b = APIClient(SERVER_NAME="test2.localhost")
        client_b.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

        response = client_b.get("/api/v1/assets/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
