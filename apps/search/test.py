"""
Test Suite for Search module.

Covers:
- Search access control
- Search across multiple entity types
- Empty and no-match queries
"""
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestGlobalSearchAPI:
    """Global search endpoint tests."""

    url = "/api/v1/search/"

    def test_unauthenticated_cannot_search(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(f"{self.url}?q=test")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_empty_query_returns_empty(self, hr_api_client):
        """No query → empty results."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_search_returns_typed_results(self, hr_api_client, asset, employee):
        """Search returns results with type field."""
        response = hr_api_client.get(f"{self.url}?q={asset.name}")
        assert response.status_code == status.HTTP_200_OK
        for result in response.data["results"]:
            assert "type" in result
            assert "title" in result
            assert "id" in result

    def _types(self, response):
        return {r["type"] for r in response.data["results"]}

    def test_matches_asset(self, hr_api_client, asset_factory, category):
        asset_factory(name="ZebraSearchAsset", category=category)
        response = hr_api_client.get(f"{self.url}?q=ZebraSearch")
        assert "ASSET" in self._types(response)

    def test_matches_employee(self, hr_api_client, employee_factory):
        employee_factory(first_name="Zephyrine", last_name="Quixote")
        response = hr_api_client.get(f"{self.url}?q=Zephyrine")
        assert "EMPLOYEE" in self._types(response)

    def test_matches_incident(self, hr_api_client, incident_factory):
        incident_factory(title="ZanzibarOutage")
        response = hr_api_client.get(f"{self.url}?q=ZanzibarOutage")
        assert "INCIDENT" in self._types(response)

    def test_matches_request_without_category(
        self, hr_api_client, employee, asset_request_factory
    ):
        """Request with no category falls back to the 'General' label."""
        asset_request_factory(requested_by=employee, category=None,
                              reason="ZorbaProjectorNeeded")
        response = hr_api_client.get(f"{self.url}?q=ZorbaProjector")
        results = response.data["results"]
        assert "REQUEST" in {r["type"] for r in results}
        req_row = next(r for r in results if r["type"] == "REQUEST")
        assert "General" in req_row["title"]

    def test_matches_license(self, hr_api_client, license_factory):
        license_factory(name="ZyngaEnterpriseSuite")
        response = hr_api_client.get(f"{self.url}?q=ZyngaEnterprise")
        assert "LICENSE" in self._types(response)
