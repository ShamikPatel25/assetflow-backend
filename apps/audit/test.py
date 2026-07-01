"""
Test Suite for Audit Log module.

Covers:
- Audit log access (admin-only)
- Audit logs are read-only (no create/update/delete)
- Role-based access denial for HR and Employee
"""
from apps.audit.models import AuditLog
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestAuditLogAccess:
    """Black-box: Audit log endpoint is read-only and admin-restricted."""

    url = "/api/v1/audit-logs/"

    def test_unauthenticated_blocked(self, api_client, tenant):
        """TC-AUD-01: No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_blocked(self, employee_api_client):
        """TC-AUD-02: EMPLOYEE cannot view audit logs."""
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_hr_blocked(self, hr_api_client):
        """TC-AUD-03: HR_MANAGER cannot view audit logs."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_view(self, admin_api_client):
        """TC-AUD-04: ORG_ADMIN → 200."""
        response = admin_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_admin_cannot_create_audit_log(self, admin_api_client):
        """TC-AUD-05: Audit logs are append-only — no manual creation via API."""
        response = admin_api_client.post(self.url, data={
            "action": "TEST", "module": "TEST",
            "object_type": "Test",
        })
        assert response.status_code in [
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_admin_cannot_delete_audit_log(self, admin_api_client, tenant):
        """TC-AUD-06: Audit logs cannot be deleted via API."""

        log = AuditLog.objects.create(
            action="TEST", module="test",
            object_type="TestModel",
        )
        response = admin_api_client.delete(f"{self.url}{log.id}/")
        assert response.status_code in [
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_403_FORBIDDEN,
        ]
