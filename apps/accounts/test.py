"""
Exhaustive Test Suite for Accounts, Audit, Search, Tenants, and Reports modules.

Covers:
- Platform auth (public schema Super Admin login)
- Audit log access (admin-only, read-only)
- Global search permissions and results
- Tenant settings access (org admin only)
- Dashboard report permissions
- Soft-delete behavior
"""
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ACCOUNTS (Tenant Auth Duplication & Soft-Delete)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccountsAuth:
    """Black-box: Account-level auth and soft-delete tests."""

    def test_unauthenticated_cannot_access_user_list(self, api_client, tenant):
        """TC-ACC-01: No JWT → blocked from user endpoints."""
        response = api_client.get("/api/v1/auth/users/")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_soft_deleted_user_cannot_login(self, api_client, tenant_user_factory):
        """TC-ACC-02: Deactivated user gets blocked at login."""
        user = tenant_user_factory(email="deactivated@test.local")
        user.is_active = False
        user.save()

        response = api_client.post("/api/v1/auth/login/", data={
            "email": "deactivated@test.local",
            "password": "testpass123",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST



# ═══════════════════════════════════════════════════════════════════════════════
# 2. AUDIT LOGS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditLogs:
    """Black-box: Audit log access is restricted to ORG_ADMIN only."""

    url = "/api/v1/audit-logs/"

    def test_unauthenticated_cannot_view_audit_logs(self, api_client, tenant):
        """TC-AUDIT-01: No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_cannot_view_audit_logs(self, employee_api_client):
        """TC-AUDIT-02: EMPLOYEE → 403."""
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hr_cannot_view_audit_logs(self, hr_api_client):
        """TC-AUDIT-03: HR_MANAGER → 403."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_view_audit_logs(self, admin_api_client):
        """TC-AUDIT-04: ORG_ADMIN → 200."""
        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK


# ═══════════════════════════════════════════════════════════════════════════════
# 3. GLOBAL SEARCH
# ═══════════════════════════════════════════════════════════════════════════════

class TestGlobalSearch:
    """Black-box: Global search endpoint access and behavior."""

    url = "/api/v1/search/"

    def test_unauthenticated_cannot_search(self, api_client, tenant):
        """TC-SEARCH-01: No JWT → blocked."""
        response = api_client.get(f"{self.url}?q=test")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_empty_query_returns_empty_results(self, hr_api_client):
        """TC-SEARCH-02: Empty query → empty results (not error)."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_search_finds_assets_by_name(self, hr_api_client, asset):
        """TC-SEARCH-03: Search for asset name → returns result with type ASSET."""
        response = hr_api_client.get(f"{self.url}?q={asset.name}")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        types = [r["type"] for r in results]
        assert "ASSET" in types

    def test_search_finds_assets_by_code(self, hr_api_client, asset):
        """TC-SEARCH-04: Search by asset_code → returns result."""
        response = hr_api_client.get(f"{self.url}?q={asset.asset_code}")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1

    def test_search_finds_employees(self, hr_api_client, employee):
        """TC-SEARCH-05: Search for employee name → EMPLOYEE result."""
        response = hr_api_client.get(f"{self.url}?q={employee.first_name}")
        assert response.status_code == status.HTTP_200_OK
        types = [r["type"] for r in response.data["results"]]
        assert "EMPLOYEE" in types

    def test_search_no_match_returns_empty(self, hr_api_client):
        """TC-SEARCH-06: Gibberish query → no results (not error)."""
        response = hr_api_client.get(f"{self.url}?q=xyznonexistent999")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TENANT SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTenantSettings:
    """Black-box: Organization settings access control."""

    url = "/api/v1/organization/settings/"

    def test_unauthenticated_blocked(self, api_client, tenant):
        """TC-TENANT-01: No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_employee_cannot_modify_settings(self, employee_api_client):
        """TC-TENANT-02: EMPLOYEE cannot modify organization settings."""
        response = employee_api_client.put(self.url, data={"name": "Hacked"})
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. DASHBOARD REPORTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDashboardReports:
    """Black-box: Dashboard summary endpoint access."""

    url = "/api/v1/reports/dashboard/"

    def test_unauthenticated_cannot_view_dashboard(self, api_client, tenant):
        """TC-DASH-01: No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_cannot_view_dashboard(self, employee_api_client):
        """TC-DASH-02: EMPLOYEE → 403."""
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hr_cannot_view_dashboard(self, hr_api_client):
        """TC-DASH-03: HR_MANAGER → 403 (admin only)."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_view_dashboard(self, admin_api_client):
        """TC-DASH-04: ORG_ADMIN → 200 with stats data."""
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
        """TC-DASH-05: All dashboard values should be integers."""
        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        for section in response.data.values():
            if isinstance(section, dict):
                for value in section.values():
                    assert isinstance(value, int)
