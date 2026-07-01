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
    """Black-box: Dashboard endpoint access and response."""

    url = "/api/v1/reports/dashboard/"

    def test_unauthenticated_blocked(self, api_client, tenant):
        """TC-RPT-01: No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_blocked(self, employee_api_client):
        """TC-RPT-02: EMPLOYEE cannot view dashboard."""
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_gets_valid_dashboard(self, admin_api_client):
        """TC-RPT-03: ORG_ADMIN gets a full dashboard response."""
        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert "assets" in response.data
        assert "total" in response.data["assets"]
