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
    """Black-box: Global search endpoint tests."""

    url = "/api/v1/search/"

    def test_unauthenticated_cannot_search(self, api_client, tenant):
        """TC-SRCH-01: No JWT → blocked."""
        response = api_client.get(f"{self.url}?q=test")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_empty_query_returns_empty(self, hr_api_client):
        """TC-SRCH-02: No query → empty results."""
        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_search_returns_typed_results(self, hr_api_client, asset, employee):
        """TC-SRCH-03: Search returns results with type field."""
        response = hr_api_client.get(f"{self.url}?q={asset.name}")
        assert response.status_code == status.HTTP_200_OK
        for result in response.data["results"]:
            assert "type" in result
            assert "title" in result
            assert "id" in result
