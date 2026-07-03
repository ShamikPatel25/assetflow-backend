"""
Test Suite for AI Risk Assessment module.

Covers:
- AI endpoint access control (only HR/Admin)
- Validation of action + required IDs
- Mock response fallback when no API key
"""
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestAIEndpointAccess:
    """AI risk assessment endpoint access."""

    url = "/api/v1/ai/risk-assessment/"

    def test_unauthenticated_cannot_access_ai(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.post(self.url, data={
            "action": "APPROVE_REQUEST",
        })
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_cannot_access_ai(self, employee_api_client):
        """EMPLOYEE → 403."""
        response = employee_api_client.post(self.url, data={
            "action": "APPROVE_REQUEST",
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_action_rejected(self, hr_api_client):
        """Invalid action type → 400."""
        response = hr_api_client.post(self.url, data={
            "action": "HACK_SYSTEM",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_approve_request_requires_request_id(self, hr_api_client):
        """APPROVE_REQUEST without request_id → 400."""
        response = hr_api_client.post(self.url, data={
            "action": "APPROVE_REQUEST",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_allocate_asset_requires_both_ids(self, hr_api_client):
        """ALLOCATE_ASSET without employee_id/asset_id → 400."""
        response = hr_api_client.post(self.url, data={
            "action": "ALLOCATE_ASSET",
            "employee_id": "",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST
