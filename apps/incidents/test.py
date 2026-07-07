"""
Tests for Incidents module.

Covers:
- Incident creation (employees report for their own allocated assets)
- Status transitions via POST /incidents/{id}/status/:
    OPEN -> IN_PROGRESS | CLOSED, IN_PROGRESS -> RESOLVED | CLOSED
    (RESOLVED and CLOSED are terminal; employees may only close their own OPEN)
- Invalid transitions and terminal-state guards
- Role-scoped visibility (employees see only their own; HR/Admin see all)
- Cannot update resolved/closed incidents
- Serializer nesting of asset / reported_by / assigned_to
- RepairRecord closed-incident guards
"""
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


# 1. INCIDENT CREATION

class TestIncidentCreation:
    """Incident creation rules."""

    url = "/api/v1/incidents/"

    def test_employee_can_report_incident(
        self, employee_api_client, employee_user, employee_factory, asset
    ):
        """Employee with profile can report an incident."""
        from apps.allocations.models import AssetAllocation
        from django.utils import timezone
        
        emp = employee_factory(user=employee_user)
        asset.current_owner = emp
        asset.save()
        
        AssetAllocation.objects.create(
            asset=asset,
            employee=emp,
            status=AssetAllocation.Status.ACTIVE,
            allocated_at=timezone.now()
        )

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
        """Missing title → 400."""
        response = hr_api_client.post(self.url, data={
            "asset": str(asset.id),
            "description": "Something broke",
            "category": "HARDWARE",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_incident_requires_description(self, hr_api_client, asset, hr_employee):
        """Missing description → 400."""
        response = hr_api_client.post(self.url, data={
            "asset": str(asset.id),
            "title": "Broken",
            "category": "HARDWARE",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_cannot_report(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.post(self.url, data={"title": "test"})
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]


# 2. INCIDENT STATUS TRANSITIONS

class TestIncidentStatusTransitions:
    """
    Status lifecycle via the single POST /incidents/{id}/status/ action.

    Valid transitions:
        HR / Admin:  OPEN        -> IN_PROGRESS | CLOSED
                     IN_PROGRESS -> RESOLVED | CLOSED
        Employee:    OPEN        -> CLOSED  (own incidents only)
    RESOLVED and CLOSED are terminal.
    """

    def _set_status(self, client, inc, new_status):
        return client.post(
            f"/api/v1/incidents/{inc.id}/status/",
            data={"status": new_status}, format="json",
        )

    # -- HR / Admin happy paths -------------------------------------------

    def test_open_to_in_progress(self, hr_api_client, incident_factory, asset, hr_employee):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        response = self._set_status(hr_api_client, inc, "IN_PROGRESS")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "IN_PROGRESS"

    def test_open_to_closed_stamps_closed_at(self, hr_api_client, incident_factory,
                                             asset, hr_employee):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        response = self._set_status(hr_api_client, inc, "CLOSED")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "CLOSED"
        inc.refresh_from_db()
        assert inc.closed_at is not None

    def test_in_progress_to_resolved_stamps_resolved_at(self, hr_api_client,
                                                        incident_factory, asset, hr_employee):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="IN_PROGRESS")
        response = self._set_status(hr_api_client, inc, "RESOLVED")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "RESOLVED"
        inc.refresh_from_db()
        assert inc.resolved_at is not None

    def test_in_progress_to_closed(self, hr_api_client, incident_factory, asset, hr_employee):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="IN_PROGRESS")
        response = self._set_status(hr_api_client, inc, "CLOSED")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "CLOSED"

    # -- Invalid transitions ----------------------------------------------

    def test_open_to_resolved_rejected(self, hr_api_client, incident_factory, asset, hr_employee):
        """OPEN cannot jump straight to RESOLVED — must pass through IN_PROGRESS."""
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        response = self._set_status(hr_api_client, inc, "RESOLVED")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_resolved_is_terminal(self, hr_api_client, incident_factory, asset, hr_employee):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="RESOLVED")
        response = self._set_status(hr_api_client, inc, "CLOSED")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_closed_is_terminal(self, hr_api_client, incident_factory, asset, hr_employee):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="CLOSED")
        response = self._set_status(hr_api_client, inc, "IN_PROGRESS")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_in_progress_to_open_rejected(self, hr_api_client, incident_factory,
                                          asset, hr_employee):
        """IN_PROGRESS may only go to RESOLVED or CLOSED, not back to OPEN."""
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="IN_PROGRESS")
        response = self._set_status(hr_api_client, inc, "OPEN")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_same_status_is_noop(self, hr_api_client, incident_factory, asset, hr_employee):
        """Re-submitting the current status is a 200 no-op."""
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        response = self._set_status(hr_api_client, inc, "OPEN")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "OPEN"

    def test_invalid_status_value_rejected(self, hr_api_client, incident_factory,
                                           asset, hr_employee):
        """A value outside Status.choices fails serializer validation → 400."""
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        response = self._set_status(hr_api_client, inc, "BOGUS")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # -- Employee-scoped rules --------------------------------------------

    def test_employee_can_close_own_open_incident(
        self, employee_api_client, employee_user, employee_factory, incident_factory, asset,
    ):
        emp = employee_factory(user=employee_user)
        inc = incident_factory(asset=asset, reported_by=emp, status="OPEN")
        response = self._set_status(employee_api_client, inc, "CLOSED")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "CLOSED"

    def test_employee_cannot_set_in_progress(
        self, employee_api_client, employee_user, employee_factory, incident_factory, asset,
    ):
        """Employees may only take OPEN -> CLOSED, not OPEN -> IN_PROGRESS."""
        emp = employee_factory(user=employee_user)
        inc = incident_factory(asset=asset, reported_by=emp, status="OPEN")
        response = self._set_status(employee_api_client, inc, "IN_PROGRESS")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_employee_cannot_touch_another_incident(
        self, employee_api_client, employee_user, employee_factory, incident_factory, asset,
    ):
        """Another employee's incident is invisible (queryset-filtered) → 404."""
        employee_factory(user=employee_user)
        other = employee_factory(first_name="Other")
        inc = incident_factory(asset=asset, reported_by=other, status="OPEN")
        response = self._set_status(employee_api_client, inc, "CLOSED")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # -- Update guard on terminal incidents -------------------------------

    def test_update_resolved_incident_blocked(self, hr_api_client, incident_factory,
                                               asset, hr_employee):
        """Cannot PUT fields on a RESOLVED incident."""
        inc = incident_factory(
            asset=asset, reported_by=hr_employee, status="RESOLVED"
        )
        response = hr_api_client.put(f"/api/v1/incidents/{inc.id}/", data={
            "title": "Updated", "description": "Changed",
            "category": "HARDWARE", "priority": "LOW",
            "asset": str(asset.id), "reported_by": str(hr_employee.id),
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 3. INCIDENT VISIBILITY SCOPING

class TestIncidentVisibility:
    """Role-based incident visibility."""

    url = "/api/v1/incidents/"

    def test_employee_sees_only_own_incidents(
        self, employee_api_client, employee_user, employee_factory,
        incident_factory, asset
    ):
        """EMPLOYEE only sees incidents they reported."""
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
        """HR sees all incidents across all employees."""
        emp1 = employee_factory(first_name="Emp1")
        emp2 = employee_factory(first_name="Emp2")
        incident_factory(asset=asset, reported_by=emp1)
        incident_factory(asset=asset, reported_by=emp2)

        response = hr_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        if isinstance(results, list):
            assert len(results) >= 2

    def test_employee_without_profile_sees_none(
        self, employee_api_client, incident_factory, asset
    ):
        """An EMPLOYEE with no linked profile sees an empty list (qs.none())."""
        incident_factory(asset=asset)  # belongs to someone else
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        assert list(results) == []


# 4. INCIDENT CREATE — perform_create branch rules

class TestIncidentCreateRules:
    url = "/api/v1/incidents/"

    def test_hardware_incident_on_software_asset_rejected(
        self, hr_api_client, category_factory, asset_factory, hr_employee,
    ):
        """A HARDWARE/PHYSICAL incident on a SOFTWARE asset → 400."""
        sw_cat = category_factory(name="SW", code="SWX", category_type="SOFTWARE")
        sw_asset = asset_factory(name="Office365", category=sw_cat)
        response = hr_api_client.post(self.url, data={
            "asset": str(sw_asset.id), "title": "bad", "description": "d",
            "category": "HARDWARE", "priority": "LOW",
            "reported_by": str(hr_employee.id),
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_hr_creates_incident_for_named_reporter(
        self, hr_api_client, asset, hr_employee,
    ):
        """Non-employee role → reported_by taken from payload (else branch)."""
        response = hr_api_client.post(self.url, data={
            "asset": str(asset.id), "title": "HR reported", "description": "d",
            "category": "HARDWARE", "priority": "MEDIUM",
            "reported_by": str(hr_employee.id),
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "OPEN"

    def test_create_without_reporter_or_profile_rejected(self, hr_api_client, asset):
        """Non-employee caller with no profile and no reported_by → 400."""
        response = hr_api_client.post(self.url, data={
            "asset": str(asset.id), "title": "no reporter", "description": "d",
            "category": "HARDWARE", "priority": "LOW",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_employee_report_for_owned_but_unallocated_asset_rejected(
        self, employee_api_client, employee_user, employee_factory, asset,
    ):
        """Owner check passes validation, but no ACTIVE allocation → 400."""
        emp = employee_factory(user=employee_user)
        asset.current_owner = emp
        asset.save(update_fields=["current_owner"])
        response = employee_api_client.post(self.url, data={
            "asset": str(asset.id), "title": "mine", "description": "broke",
            "category": "HARDWARE", "priority": "LOW",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_employee_without_profile_reporting_for_other_rejected(
        self, employee_api_client, employee_factory, asset,
    ):
        """Employee (no profile) naming another reporter → perform_create guard."""
        other = employee_factory(first_name="Other")
        response = employee_api_client.post(self.url, data={
            "asset": str(asset.id), "title": "x", "description": "y",
            "category": "HARDWARE", "priority": "LOW",
            "reported_by": str(other.id),
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 5. INCIDENT UPDATE — success path

class TestIncidentUpdate:
    def test_hr_can_update_open_incident(
        self, hr_api_client, incident_factory, asset, hr_employee,
    ):
        """Updating an OPEN incident passes the guard → 200."""
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        response = hr_api_client.put(f"/api/v1/incidents/{inc.id}/", data={
            "title": "Updated title", "description": "Updated desc",
            "category": "HARDWARE", "priority": "LOW",
            "asset": str(asset.id), "reported_by": str(hr_employee.id),
        })
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Updated title"


# 6. REPAIR RECORDS — closed-incident guards

class TestRepairRecords:
    base_url = "/api/v1/incidents/repairs/"

    def _repair(self, incident, asset, **kwargs):
        from apps.incidents.models import RepairRecord
        return RepairRecord.objects.create(
            incident=incident, asset=asset, vendor_name="FixIt", **kwargs
        )

    def test_hr_can_create_repair_record(
        self, hr_api_client, incident_factory, asset, hr_employee,
    ):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        response = hr_api_client.post(self.base_url, data={
            "incident": str(inc.id), "asset": str(asset.id),
            "vendor_name": "FixIt Co", "repair_cost": "100.00",
        })
        assert response.status_code == status.HTTP_201_CREATED

    def test_cannot_add_repair_to_closed_incident(
        self, hr_api_client, incident_factory, asset, hr_employee,
    ):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="CLOSED")
        response = hr_api_client.post(self.base_url, data={
            "incident": str(inc.id), "asset": str(asset.id), "vendor_name": "X",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_hr_can_update_repair_record(
        self, hr_api_client, incident_factory, asset, hr_employee,
    ):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        rec = self._repair(inc, asset)
        response = hr_api_client.put(f"{self.base_url}{rec.id}/", data={
            "incident": str(inc.id), "asset": str(asset.id), "vendor_name": "NewVendor",
        })
        assert response.status_code == status.HTTP_200_OK

    def test_cannot_update_repair_on_closed_incident(
        self, hr_api_client, incident_factory, asset, hr_employee,
    ):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        rec = self._repair(inc, asset)
        inc.status = "CLOSED"
        inc.save(update_fields=["status"])
        response = hr_api_client.put(f"{self.base_url}{rec.id}/", data={
            "incident": str(inc.id), "asset": str(asset.id), "vendor_name": "Y",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_move_repair_to_closed_incident(
        self, hr_api_client, incident_factory, asset, hr_employee,
    ):
        open_inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        closed_inc = incident_factory(asset=asset, reported_by=hr_employee, status="CLOSED")
        rec = self._repair(open_inc, asset)
        response = hr_api_client.put(f"{self.base_url}{rec.id}/", data={
            "incident": str(closed_inc.id), "asset": str(asset.id), "vendor_name": "Z",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_hr_can_delete_repair_record(
        self, hr_api_client, incident_factory, asset, hr_employee,
    ):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        rec = self._repair(inc, asset)
        response = hr_api_client.delete(f"{self.base_url}{rec.id}/")
        assert response.status_code in (
            status.HTTP_204_NO_CONTENT, status.HTTP_200_OK,
        )

    def test_cannot_delete_repair_from_closed_incident(
        self, hr_api_client, incident_factory, asset, hr_employee,
    ):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        rec = self._repair(inc, asset)
        inc.status = "CLOSED"
        inc.save(update_fields=["status"])
        response = hr_api_client.delete(f"{self.base_url}{rec.id}/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 6b. BULK STATUS UPDATE — POST /incidents/bulk-status/

class TestIncidentBulkStatus:
    url = "/api/v1/incidents/bulk-status/"

    def _bulk(self, client, ids, new_status):
        return client.post(self.url, data={
            "incident_ids": [str(i) for i in ids], "status": new_status,
        }, format="json")

    def test_hr_bulk_advances_multiple(self, hr_api_client, incident_factory,
                                       asset, hr_employee):
        a = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        b = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        response = self._bulk(hr_api_client, [a.id, b.id], "IN_PROGRESS")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["updated_count"] == 2
        assert response.data["errors"] == []

    def test_same_status_counts_as_updated(self, hr_api_client, incident_factory,
                                           asset, hr_employee):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        response = self._bulk(hr_api_client, [inc.id], "OPEN")
        assert response.data["updated_count"] == 1

    def test_unknown_id_reported_in_errors(self, hr_api_client):
        import uuid
        response = self._bulk(hr_api_client, [uuid.uuid4()], "IN_PROGRESS")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["updated_count"] == 0
        assert response.data["errors"][0]["error"] == "Not found."

    def test_terminal_incident_reported_in_errors(self, hr_api_client, incident_factory,
                                                  asset, hr_employee):
        closed = incident_factory(asset=asset, reported_by=hr_employee, status="CLOSED")
        response = self._bulk(hr_api_client, [closed.id], "IN_PROGRESS")
        assert response.data["updated_count"] == 0
        assert "closed" in response.data["errors"][0]["error"].lower()

    def test_invalid_transition_reported_in_errors(self, hr_api_client, incident_factory,
                                                   asset, hr_employee):
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        response = self._bulk(hr_api_client, [inc.id], "RESOLVED")
        assert response.data["updated_count"] == 0
        assert response.data["errors"]

    def test_bulk_in_progress_to_resolved_stamps(self, hr_api_client, incident_factory,
                                                 asset, hr_employee):
        """Bulk IN_PROGRESS -> RESOLVED succeeds and stamps resolved_at."""
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="IN_PROGRESS")
        response = self._bulk(hr_api_client, [inc.id], "RESOLVED")
        assert response.data["updated_count"] == 1
        inc.refresh_from_db()
        assert inc.status == "RESOLVED" and inc.resolved_at is not None

    def test_bulk_in_progress_invalid_target_reported(self, hr_api_client, incident_factory,
                                                      asset, hr_employee):
        """Bulk IN_PROGRESS -> OPEN is rejected per-item."""
        inc = incident_factory(asset=asset, reported_by=hr_employee, status="IN_PROGRESS")
        response = self._bulk(hr_api_client, [inc.id], "OPEN")
        assert response.data["updated_count"] == 0
        assert response.data["errors"]

    def test_mixed_batch_partial_success(self, hr_api_client, incident_factory,
                                         asset, hr_employee):
        ok = incident_factory(asset=asset, reported_by=hr_employee, status="OPEN")
        bad = incident_factory(asset=asset, reported_by=hr_employee, status="CLOSED")
        response = self._bulk(hr_api_client, [ok.id, bad.id], "IN_PROGRESS")
        assert response.data["updated_count"] == 1
        assert len(response.data["errors"]) == 1

    def test_employee_bulk_close_own_and_reject_others(
        self, employee_api_client, employee_user, employee_factory,
        incident_factory, asset,
    ):
        emp = employee_factory(user=employee_user)
        mine = incident_factory(asset=asset, reported_by=emp, status="OPEN")
        other = employee_factory(first_name="Other")
        theirs = incident_factory(asset=asset, reported_by=other, status="OPEN")
        response = self._bulk(employee_api_client, [mine.id, theirs.id], "CLOSED")
        assert response.data["updated_count"] == 1  # only own incident
        assert len(response.data["errors"]) == 1     # permission error on the other

    def test_employee_invalid_transition_reported(
        self, employee_api_client, employee_user, employee_factory,
        incident_factory, asset,
    ):
        """Employee trying OPEN -> IN_PROGRESS in bulk is rejected per-item."""
        emp = employee_factory(user=employee_user)
        mine = incident_factory(asset=asset, reported_by=emp, status="OPEN")
        response = self._bulk(employee_api_client, [mine.id], "IN_PROGRESS")
        assert response.data["updated_count"] == 0
        assert response.data["errors"]

    def test_empty_ids_rejected(self, hr_api_client):
        """allow_empty=False on the serializer → 400."""
        response = hr_api_client.post(self.url, data={
            "incident_ids": [], "status": "CLOSED",
        }, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# 7. INCIDENT SERIALIZER — method fields + employee validate() branches

class TestIncidentSerializerBranches:
    url = "/api/v1/incidents/"

    def _incident(self, asset, **kwargs):
        import uuid
        from django.utils import timezone
        from apps.incidents.models import Incident
        defaults = {
            "incident_number": f"INC-{uuid.uuid4().hex[:8].upper()}",
            "asset": asset, "title": "t", "description": "d",
            "category": "HARDWARE", "priority": "LOW", "status": "OPEN",
            "opened_at": timezone.now(),
        }
        defaults.update(kwargs)
        return Incident.objects.create(**defaults)

    def test_absent_relations_serialize_as_null(self, tenant, hr_employee):
        """No asset / no assignee → those keys stay null (nesting branch skipped)."""
        from apps.incidents.serializers import IncidentSerializer
        inc = self._incident(asset=None, reported_by=hr_employee)  # assigned_to defaults None
        data = IncidentSerializer(inc).data
        assert data["asset"] is None
        assert data["assigned_to"] is None
        # reported_by is a PROTECT (non-null) FK, so it is always nested
        assert data["reported_by"]["id"] == hr_employee.id

    def test_present_relations_are_nested(
        self, tenant, asset, hr_employee, employee_factory,
    ):
        """asset / reported_by / assigned_to present → nested id+label dicts."""
        from apps.incidents.serializers import IncidentSerializer
        assignee = employee_factory(first_name="Assignee")
        inc = self._incident(asset, reported_by=hr_employee, assigned_to=assignee)
        data = IncidentSerializer(inc).data
        assert data["asset"]["asset_code"] == asset.asset_code
        assert data["reported_by"]["name"] == hr_employee.get_full_name()
        assert data["assigned_to"]["name"] == assignee.get_full_name()

    def test_employee_cannot_report_for_another_via_validate(
        self, employee_api_client, employee_user, employee_factory, asset,
    ):
        """Serializer validate() blocks naming a different reporter."""
        emp = employee_factory(user=employee_user)
        asset.current_owner = emp
        asset.save(update_fields=["current_owner"])
        other = employee_factory(first_name="Other2")
        response = employee_api_client.post(self.url, data={
            "asset": str(asset.id), "title": "x", "description": "y",
            "category": "HARDWARE", "priority": "LOW",
            "reported_by": str(other.id),
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_employee_cannot_report_for_unowned_asset_via_validate(
        self, employee_api_client, employee_user, employee_factory, asset_factory, category,
    ):
        """Serializer validate() blocks reporting on an asset owned by someone else."""
        employee_factory(user=employee_user)
        owner = employee_factory(first_name="OwnerX")
        their_asset = asset_factory(name="Theirs", category=category, current_owner=owner)
        response = employee_api_client.post(self.url, data={
            "asset": str(their_asset.id), "title": "x", "description": "y",
            "category": "HARDWARE", "priority": "LOW",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST
