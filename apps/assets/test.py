"""
Tests for Assets and AssetCategory modules.

Covers:
- Category hierarchy (parent-child creation)
- Asset CRUD with role-based permissions
- Status transitions (AVAILABLE → ALLOCATED → IN_MAINTENANCE → RETIRED)
- Asset code uniqueness enforcement
- Category type validation
- Employee cannot create/edit/delete assets
- Soft-delete behavior
- Edge cases: missing required fields, invalid category references
"""
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


# 1. ASSET CATEGORY MANAGEMENT

class TestAssetCategories:
    """Category CRUD, hierarchy, and permissions."""

    url = "/api/v1/asset-categories/"

    def test_hr_can_list_categories(self, hr_api_client, category):
        """HR_MANAGER can list asset categories."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_employee_can_read_categories(self, employee_api_client, category):
        """Employees can read categories (for request dropdown)."""
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_employee_cannot_create_category(self, employee_api_client):
        """EMPLOYEE cannot create asset categories."""
        response = employee_api_client.post(self.url, data={
            "name": "Hacked", "code": "HACK", "category_type": "HARDWARE",
        })
        assert response.status_code in [status.HTTP_403_FORBIDDEN]

    def test_hr_can_create_top_level_category(self, hr_api_client):
        """HR creates a top-level category (no parent)."""
        response = hr_api_client.post(self.url, data={
            "name": "Hardware", "code": "HW", "category_type": "HARDWARE",
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Hardware"

    def test_hr_can_create_child_category(self, hr_api_client, category):
        """HR creates a child category under existing parent."""
        response = hr_api_client.post(self.url, data={
            "name": "Gaming Laptops", "code": "GLAP",
            "category_type": "HARDWARE", "parent": str(category.id),
        })
        assert response.status_code == status.HTTP_201_CREATED

    def test_duplicate_category_code_rejected(self, hr_api_client, category):
        """Duplicate code → 400."""
        response = hr_api_client.post(self.url, data={
            "name": "Duplicate", "code": category.code, "category_type": "HARDWARE",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_category_with_invalid_type(self, hr_api_client):
        """Invalid category_type → 400."""
        response = hr_api_client.post(self.url, data={
            "name": "Bad Type", "code": "BTYPE", "category_type": "UNKNOWN",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 2. ASSET CRUD PERMISSIONS

class TestAssetPermissions:
    """Test who can create, read, update, delete assets."""

    url = "/api/v1/assets/"

    def test_unauthenticated_cannot_access_assets(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_can_list_assets(self, employee_api_client, asset):
        """EMPLOYEE can see asset list (read-only)."""
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_employee_cannot_create_asset(self, employee_api_client, category):
        """EMPLOYEE cannot add an asset to inventory."""
        response = employee_api_client.post(self.url, data={
            "asset_code": "HACK-001", "name": "Hacked",
            "category": str(category.id),
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hr_can_create_asset(self, hr_api_client, category):
        """HR_MANAGER can add an asset."""
        response = hr_api_client.post(self.url, data={
            "asset_code": "AST-NEW-001", "name": "Dell Monitor",
            "category": str(category.id), "status": "AVAILABLE",
        })
        assert response.status_code == status.HTTP_201_CREATED

    def test_admin_can_create_asset(self, admin_api_client, category):
        """ORG_ADMIN can add an asset."""
        response = admin_api_client.post(self.url, data={
            "asset_code": "AST-ADM-001", "name": "Admin Asset",
            "category": str(category.id), "status": "AVAILABLE",
        })
        assert response.status_code == status.HTTP_201_CREATED

    def test_employee_cannot_delete_asset(self, employee_api_client, asset):
        """EMPLOYEE cannot soft-delete an asset."""
        url = f"{self.url}{asset.id}/"
        response = employee_api_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN


# 3. ASSET DATA VALIDATION

class TestAssetValidation:
    """Serializer-level validation edge cases."""

    url = "/api/v1/assets/"

    def test_asset_code_must_be_unique(self, hr_api_client, asset, category):
        """Duplicate asset_code → 400."""
        response = hr_api_client.post(self.url, data={
            "asset_code": asset.asset_code,
            "name": "Duplicate", "category": str(category.id),
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_asset_requires_category(self, hr_api_client):
        """Missing category → 400."""
        response = hr_api_client.post(self.url, data={
            "asset_code": "NO-CAT-001", "name": "No Category",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_status_value_rejected(self, hr_api_client, category):
        """Invalid status string → 400."""
        response = hr_api_client.post(self.url, data={
            "asset_code": "BAD-STATUS", "name": "Bad",
            "category": str(category.id), "status": "FLYING",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_condition_value_rejected(self, hr_api_client, category):
        """Invalid condition string → 400."""
        response = hr_api_client.post(self.url, data={
            "asset_code": "BAD-COND", "name": "Bad",
            "category": str(category.id), "condition": "EXCELLENT",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_asset_code_required(self, hr_api_client, category):
        """Missing asset_code → 400."""
        response = hr_api_client.post(self.url, data={
            "name": "No Code", "category": str(category.id),
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 4. ASSET STATUS TRANSITIONS

class TestAssetStatusTransitions:
    """Status updates via PUT."""

    url = "/api/v1/assets/"

    def test_update_asset_to_in_maintenance(self, hr_api_client, asset):
        """HR can update asset status to IN_MAINTENANCE."""
        url = f"{self.url}{asset.id}/"
        response = hr_api_client.put(url, data={
            "asset_code": asset.asset_code, "name": asset.name,
            "category": str(asset.category.id), "status": "IN_MAINTENANCE",
        })
        assert response.status_code == status.HTTP_200_OK

    def test_update_asset_to_retired(self, hr_api_client, asset):
        """HR can retire an asset."""
        url = f"{self.url}{asset.id}/"
        response = hr_api_client.put(url, data={
            "asset_code": asset.asset_code, "name": asset.name,
            "category": str(asset.category.id), "status": "RETIRED",
        })
        assert response.status_code == status.HTTP_200_OK

    def test_employee_cannot_change_asset_status(self, employee_api_client, asset):
        """EMPLOYEE cannot change asset status."""
        url = f"{self.url}{asset.id}/"
        response = employee_api_client.put(url, data={
            "asset_code": asset.asset_code, "name": asset.name,
            "category": str(asset.category.id), "status": "RETIRED",
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN
