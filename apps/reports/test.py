"""
Test Suite for Dashboard Reports module.

Covers:
- Dashboard access by role
- Response structure validation
"""
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestDashboardAPI:
    """Dashboard endpoint access and response."""

    url = "/api/v1/reports/dashboard/"

    def test_unauthenticated_blocked(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_blocked(self, employee_api_client):
        """EMPLOYEE cannot view dashboard."""
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_gets_valid_dashboard(self, admin_api_client):
        """ORG_ADMIN gets a full dashboard response."""
        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert "assets" in response.data
        assert "total" in response.data["assets"]


class TestReportAccessControl:
    """All report endpoints are restricted to Org Admin and HR Manager."""

    urls = [
        "/api/v1/reports/assets/",
        "/api/v1/reports/allocations/",
        "/api/v1/reports/incidents/",
        "/api/v1/reports/licenses/",
        "/api/v1/reports/employee-assets/",
    ]

    @pytest.mark.parametrize("url", urls)
    def test_unauthenticated_blocked(self, api_client, tenant, url):
        """No JWT → blocked."""
        response = api_client.get(url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.parametrize("url", urls)
    def test_employee_blocked(self, employee_api_client, url):
        """EMPLOYEE cannot view reports."""
        response = employee_api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize("url", urls)
    def test_admin_allowed(self, admin_api_client, url):
        """ORG_ADMIN can view every report with summary + results."""
        response = admin_api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "summary" in response.data
        assert "results" in response.data

    @pytest.mark.parametrize("url", urls)
    def test_hr_allowed(self, hr_api_client, url):
        """HR_MANAGER can view every report."""
        response = hr_api_client.get(url)
        assert response.status_code == status.HTTP_200_OK


class TestAssetReport:
    url = "/api/v1/reports/assets/"

    def test_lists_assets_with_summary(self, admin_api_client, asset_factory, category):
        asset_factory(name="A1", category=category, status="AVAILABLE", purchase_cost=1000)
        asset_factory(name="A2", category=category, status="ALLOCATED", purchase_cost=500)

        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["summary"]["total"] == 2
        assert response.data["summary"]["total_value"] == 1500
        assert response.data["summary"]["by_status"]["AVAILABLE"] == 1

    def test_filter_by_status(self, admin_api_client, asset_factory, category):
        asset_factory(name="A1", category=category, status="AVAILABLE")
        asset_factory(name="A2", category=category, status="RETIRED")

        response = admin_api_client.get(self.url, {"status": "RETIRED"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["summary"]["total"] == 1
        assert response.data["results"][0]["status"] == "RETIRED"

    def test_search_by_code(self, admin_api_client, asset_factory, category):
        asset_factory(name="Findme", category=category, asset_code="UNIQUE-XYZ")
        asset_factory(name="Other", category=category)

        response = admin_api_client.get(self.url, {"search": "UNIQUE-XYZ"})
        assert response.data["summary"]["total"] == 1

    def test_soft_deleted_excluded(self, admin_api_client, asset_factory, category):
        a = asset_factory(name="Gone", category=category)
        a.is_deleted = True
        a.save(update_fields=["is_deleted"])

        response = admin_api_client.get(self.url)
        assert response.data["summary"]["total"] == 0


class TestEmployeeAssetReport:
    url = "/api/v1/reports/employee-assets/"

    def test_lists_employee_with_held_assets(
        self, admin_api_client, employee, asset, allocation_factory
    ):
        allocation_factory(asset=asset, employee=employee, status="ACTIVE")

        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["summary"]["total_assets_allocated"] == 1

        row = next(r for r in response.data["results"] if r["id"] == str(employee.id))
        assert row["asset_count"] == 1
        assert row["assets"][0]["asset_code"] == asset.asset_code


class TestLicenseReport:
    url = "/api/v1/reports/licenses/"

    def test_expiring_soon_counts_only_near_expiry(self, admin_api_client, license_factory):
        from datetime import date, timedelta

        license_factory(name="Soon", status="ACTIVE", expiry_date=date.today() + timedelta(days=10))
        license_factory(name="Later", status="ACTIVE", expiry_date=date.today() + timedelta(days=200))

        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["summary"]["expiring_soon"] == 1
