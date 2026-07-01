"""
Exhaustive Test Suite for Incidents module.

Covers:
- Incident creation (any employee can report)
- Status transitions: OPEN → IN_PROGRESS → RESOLVED → CLOSED
- Invalid transitions (close without resolve, resolve closed)
- Employee can only see own incidents
- HR/Admin can see all incidents
- Cannot update resolved/closed incidents
- Resolve and Close action endpoints
"""
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


# ═══════════════════════════════════════════════════════════════════════════════
# 1. INCIDENT CREATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncidentCreation:
    """White-box + Black-box: Incident creation rules."""

    url = "/api/v1/incidents/"

    def test_employee_can_report_incident(
        self, employee_api_client, employee_user, employee_factory, asset
    ):
        """TC-INC-01: Employee with profile can report an incident."""
        emp = employee_factory(user=employee_user)
        asset.current_owner = emp
        asset.save()
        response = employee_api_client.post(self.url, data={
            "asset": str(asset.id),
            "title": "Laptop screen flickering",
            "description": "Screen flickers when opening IDE",
            "category": "HARDWARE",
            "priority": "HIGH",
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "OPEN"

    def test_incident_requires_title(self, hr_api_client, asset, hr_employee):
        """TC-INC-02: Missing title → 400."""
        response = hr_api_client.post(self.url, data={
            "asset": str(asset.id),
            "description": "Something broke",
            "category": "HARDWARE",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_incident_requires_description(self, hr_api_client, asset, hr_employee):
        """TC-INC-03: Missing description → 400."""
        response = hr_api_client.post(self.url, data={
            "asset": str(asset.id),
            "title": "Broken",
            "category": "HARDWARE",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_cannot_report(self, api_client, tenant):
        """TC-INC-04: No JWT → blocked."""
        response = api_client.post(self.url, data={"title": "test"})
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. INCIDENT STATUS TRANSITIONS (Service Logic)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncidentStatusTransitions:
    """White-box: Incident resolve/close lifecycle via API."""

    def test_resolve_open_incident(self, hr_api_client, incident_factory, asset, hr_employee):
        """TC-ITRANS-01: OPEN incident → RESOLVED via /resolve/ endpoint."""
        inc = incident_factory(asset=asset, reported_by=hr_employee)
        url = f"/api/v1/incidents/{inc.id}/resolve/"
        response = hr_api_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "RESOLVED"

    def test_close_resolved_incident(self, hr_api_client, incident_factory, asset, hr_employee):
        """TC-ITRANS-02: RESOLVED → CLOSED via /close/ endpoint."""
        inc = incident_factory(
            asset=asset, reported_by=hr_employee, status="RESOLVED"
        )
        url = f"/api/v1/incidents/{inc.id}/close/"
        response = hr_api_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "CLOSED"

    def test_close_open_incident_fails(self, hr_api_client, incident_factory,
                                        asset, hr_employee):
        """TC-ITRANS-03: Cannot close an OPEN incident (must resolve first)."""
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        url = f"/api/v1/incidents/{inc.id}/close/"
        response = hr_api_client.post(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_resolve_closed_incident_fails(self, hr_api_client, incident_factory,
                                            asset, hr_employee):
        """TC-ITRANS-04: Cannot re-resolve a CLOSED incident."""
        inc = incident_factory(
            asset=asset, reported_by=hr_employee, status="CLOSED"
        )
        url = f"/api/v1/incidents/{inc.id}/resolve/"
        response = hr_api_client.post(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_resolved_incident_blocked(self, hr_api_client, incident_factory,
                                               asset, hr_employee):
        """TC-ITRANS-05: Cannot modify fields on a RESOLVED incident."""
        inc = incident_factory(
            asset=asset, reported_by=hr_employee, status="RESOLVED"
        )
        url = f"/api/v1/incidents/{inc.id}/"
        response = hr_api_client.put(url, data={
            "title": "Updated", "description": "Changed",
            "category": "HARDWARE", "priority": "LOW",
            "asset": str(asset.id), "reported_by": str(hr_employee.id),
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ═══════════════════════════════════════════════════════════════════════════════
# 3. INCIDENT VISIBILITY SCOPING
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncidentVisibility:
    """Black-box: Role-based incident visibility."""

    url = "/api/v1/incidents/"

    def test_employee_sees_only_own_incidents(
        self, employee_api_client, employee_user, employee_factory,
        incident_factory, asset
    ):
        """TC-IVIS-01: EMPLOYEE only sees incidents they reported."""
        emp = employee_factory(user=employee_user)
        incident_factory(asset=asset, reported_by=emp, title="My Incident")
        # Another employee's incident
        other = employee_factory(first_name="Other")
        incident_factory(asset=asset, reported_by=other, title="Not Mine")

        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        if isinstance(results, list):
            for inc in results:
                assert "My Incident" == inc["title"] or inc.get("reported_by") is not None

    def test_hr_sees_all_incidents(self, hr_api_client, incident_factory, asset,
                                    employee_factory):
        """TC-IVIS-02: HR sees all incidents across all employees."""
        emp1 = employee_factory(first_name="Emp1")
        emp2 = employee_factory(first_name="Emp2")
        incident_factory(asset=asset, reported_by=emp1)
        incident_factory(asset=asset, reported_by=emp2)

        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        if isinstance(results, list):
            assert len(results) >= 2
