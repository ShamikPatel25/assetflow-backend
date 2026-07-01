"""
Test Suite for Tenants module (public schema).

Covers:
- Tenant settings access by different roles
"""
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestTenantsOrganizationSettings:
    """Black-box: Organization settings API endpoint."""

    url = "/api/v1/organization/settings/"

    def test_unauthenticated_blocked(self, api_client, tenant):
        """TC-ORG-01: No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_employee_cannot_modify(self, employee_api_client):
        """TC-ORG-02: EMPLOYEE → blocked from org settings modification."""
        response = employee_api_client.put(self.url, data={"name": "Hacked"})
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

    def test_hr_cannot_write_settings(self, hr_api_client):
        """TC-ORG-03: HR can read but not write org settings."""
        response = hr_api_client.put(self.url, data={"name": "Hacked"})
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
