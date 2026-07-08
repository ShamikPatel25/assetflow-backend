"""
Test Suite for Dashboard Reports module.

Covers:
- Dashboard access by role
- Response structure validation
- Report serializer method-field branches (present vs. missing relations)
- BaseReportView paginated / non-paginated / summary paths
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from rest_framework import status

pytestmark = pytest.mark.django_db


def _owner(name="Jane Roe"):
    return SimpleNamespace(get_full_name=lambda: name)


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


# ===========================================================================
# Report serializer method-field branches (unit — no DB needed)
#
# Each SerializerMethodField has a "relation present" and a "relation absent"
# branch. Some absent branches are unreachable through the API (non-null FKs),
# so they are exercised directly here with lightweight fake objects.
# ===========================================================================

class TestAssetReportSerializerBranches:
    from apps.reports.serializers import AssetReportSerializer as _S

    def test_category_present_and_absent(self):
        s = self._S()
        assert s.get_category(SimpleNamespace(category_id=1,
                                              category=SimpleNamespace(name="Laptops"))) == "Laptops"
        assert s.get_category(SimpleNamespace(category_id=None, category=None)) is None

    def test_current_owner_present_and_absent(self):
        s = self._S()
        got = s.get_current_owner(SimpleNamespace(current_owner_id="u1",
                                                  current_owner=_owner("Jane Roe")))
        assert got == {"id": "u1", "name": "Jane Roe"}
        assert s.get_current_owner(SimpleNamespace(current_owner_id=None,
                                                   current_owner=None)) is None


class TestAllocationReportSerializerBranches:
    from apps.reports.serializers import AllocationReportSerializer as _S

    def test_asset_present_and_absent(self):
        s = self._S()
        got = s.get_asset(SimpleNamespace(asset_id="a1",
                                          asset=SimpleNamespace(asset_code="AST-1", name="Mac")))
        assert got == {"id": "a1", "asset_code": "AST-1", "name": "Mac"}
        assert s.get_asset(SimpleNamespace(asset_id=None, asset=None)) is None

    def test_employee_present_and_absent(self):
        s = self._S()
        got = s.get_employee(SimpleNamespace(employee_id="e1", employee=_owner("John Doe")))
        assert got == {"id": "e1", "name": "John Doe"}
        assert s.get_employee(SimpleNamespace(employee_id=None, employee=None)) is None

    def test_department_present_and_absent(self):
        s = self._S()
        emp = SimpleNamespace(department=SimpleNamespace(name="Engineering"))
        assert s.get_department(SimpleNamespace(employee_id="e1", employee=emp)) == "Engineering"
        no_dept = SimpleNamespace(department=None)
        assert s.get_department(SimpleNamespace(employee_id="e1", employee=no_dept)) is None
        assert s.get_department(SimpleNamespace(employee_id=None, employee=None)) is None

    def test_duration_days_present_and_absent(self):
        s = self._S()
        start = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        end = start + timedelta(days=5)
        assert s.get_duration_days(SimpleNamespace(allocated_at=start, returned_at=end)) == 5
        # Not returned yet -> measured against now (>= 0)
        assert s.get_duration_days(SimpleNamespace(allocated_at=start, returned_at=None)) >= 0
        # No allocated_at -> None
        assert s.get_duration_days(SimpleNamespace(allocated_at=None, returned_at=None)) is None


class TestIncidentReportSerializerBranches:
    from apps.reports.serializers import IncidentReportSerializer as _S

    def test_asset_present_and_absent(self):
        s = self._S()
        got = s.get_asset(SimpleNamespace(asset_id="a1",
                                          asset=SimpleNamespace(asset_code="AST-1", name="Mac")))
        assert got == {"id": "a1", "asset_code": "AST-1", "name": "Mac"}
        assert s.get_asset(SimpleNamespace(asset_id=None, asset=None)) is None

    def test_reported_by_present_and_absent(self):
        s = self._S()
        got = s.get_reported_by(SimpleNamespace(reported_by_id="e1", reported_by=_owner("R P")))
        assert got == {"id": "e1", "name": "R P"}
        assert s.get_reported_by(SimpleNamespace(reported_by_id=None, reported_by=None)) is None

    def test_assigned_to_present_and_absent(self):
        s = self._S()
        got = s.get_assigned_to(SimpleNamespace(assigned_to_id="e2", assigned_to=_owner("A T")))
        assert got == {"id": "e2", "name": "A T"}
        assert s.get_assigned_to(SimpleNamespace(assigned_to_id=None, assigned_to=None)) is None

    def test_repair_cost_annotation(self):
        s = self._S()
        assert s.get_repair_cost(SimpleNamespace(total_repair_cost=42)) == 42
        assert s.get_repair_cost(SimpleNamespace()) is None


class TestLicenseReportSerializerBranches:
    from apps.reports.serializers import LicenseReportSerializer as _S

    def test_days_to_expiry_present_and_absent(self):
        from datetime import date
        s = self._S()
        future = date.today() + timedelta(days=10)
        assert s.get_days_to_expiry(SimpleNamespace(expiry_date=future)) == 10
        assert s.get_days_to_expiry(SimpleNamespace(expiry_date=None)) is None


class TestEmployeeAssetReportSerializerBranches:
    from apps.reports.serializers import EmployeeAssetReportSerializer as _S

    def test_department_and_counts(self):
        s = self._S()
        emp = SimpleNamespace(department_id=1, department=SimpleNamespace(name="Eng"))
        assert s.get_department(emp) == "Eng"
        assert s.get_department(SimpleNamespace(department_id=None, department=None)) is None

    def test_assets_present_and_skips_missing_asset(self):
        s = self._S()
        good = SimpleNamespace(
            asset_id="a1", allocation_number="ALLOC-1",
            allocated_at="2026-01-01T00:00:00Z",
            asset=SimpleNamespace(asset_code="AST-1", name="Mac", status="ALLOCATED"),
        )
        missing = SimpleNamespace(asset_id=None)
        emp = SimpleNamespace(active_allocations=[good, missing])
        assert s.get_asset_count(emp) == 2
        rows = s.get_assets(emp)
        assert len(rows) == 1  # the asset-less allocation is skipped
        assert rows[0]["asset_code"] == "AST-1"

    def test_assets_defaults_to_empty_without_prefetch(self):
        s = self._S()
        emp = SimpleNamespace()  # no active_allocations attr
        assert s.get_asset_count(emp) == 0
        assert s.get_assets(emp) == []


# ===========================================================================
# BaseReportView / DashboardView branches
# ===========================================================================

class TestReportViewBranches:
    def test_base_get_summary_defaults_to_empty(self):
        from apps.reports.views import BaseReportView
        assert BaseReportView().get_summary(queryset=None) == {}

    def test_dashboard_serves_cached_payload_on_second_call(self, admin_api_client, tenant):
        """Second dashboard hit within TTL returns the cached body (cache-hit branch)."""
        cache.clear()
        first = admin_api_client.get("/api/v1/reports/dashboard/")
        second = admin_api_client.get("/api/v1/reports/dashboard/")
        assert first.status_code == second.status_code == status.HTTP_200_OK
        assert first.data == second.data

    def test_report_pagination_disabled_returns_flat_body(
        self, admin_api_client, asset_factory, category
    ):
        """?pagination=0 -> non-paginated branch: {summary, results}, no page keys."""
        asset_factory(name="A1", category=category)
        response = admin_api_client.get("/api/v1/reports/assets/", {"pagination": "0"})
        assert response.status_code == status.HTTP_200_OK
        assert set(response.data.keys()) == {"summary", "results"}
        assert "count" not in response.data  # not the paginated shape
