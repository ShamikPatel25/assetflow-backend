"""
Tests for the Asset Allocation module.

The allocation lifecycle is a strict state machine:

    AVAILABLE asset ──allocate()──▶ ALLOCATED asset + ACTIVE allocation
    ACTIVE allocation ──return_asset()──▶ RETURNED allocation + AVAILABLE asset
    ACTIVE allocation ──cancel()──────▶ CANCELLED allocation + AVAILABLE asset
    AVAILABLE asset ──allocate()──▶ (can be re-allocated to anyone)

These tests exercise the full flow end to end:
    allocate  ->  return  ->  re-allocate  ->  return again
    allocate  ->  cancel
and every error branch on the way.

Because this project normalizes ALL API errors into a single
``{"message": <sentence>, "code": <int>}`` body (see apps/base/errors),
the API tests assert on that exact contract instead of Django/DRF's
default shape-shifting payloads (``{"field": [...]}``, ``{"detail": ...}``).
"""
import uuid

import pytest
from django.db import IntegrityError, transaction
from rest_framework import status

from apps.allocations.models import AssetAllocation
from apps.allocations.services import AllocationService
from apps.assets.models import Asset
from apps.base.errors import AFValidationError, error_codes

pytestmark = pytest.mark.django_db


# ===========================================================================
# 1. SERVICE — allocate()
# ===========================================================================

class TestAllocateService:
    """AllocationService.allocate() business rules."""

    def test_allocate_available_asset_succeeds(self, asset, employee,
                                               mock_notification_service):
        """An AVAILABLE asset -> ACTIVE allocation + ALLOCATED asset."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)

        assert allocation.status == AssetAllocation.Status.ACTIVE
        assert allocation.employee == employee
        assert allocation.allocation_number.startswith("ALLOC-")
        assert allocation.allocated_at is not None
        assert allocation.returned_at is None

        asset.refresh_from_db()
        assert asset.status == Asset.Status.ALLOCATED
        assert asset.current_owner == employee
        assert asset.current_allocation == allocation

    def test_allocate_passes_through_optional_fields(self, asset, employee,
                                                     employee_factory,
                                                     mock_notification_service):
        """assigned_by / expected_return_date / remarks are persisted."""
        assigner = employee_factory(first_name="Assigner")
        allocation = AllocationService.allocate(
            asset=asset,
            employee=employee,
            assigned_by=assigner,
            expected_return_date="2030-01-01",
            remarks="For onboarding",
        )
        assert allocation.assigned_by == assigner
        assert str(allocation.expected_return_date) == "2030-01-01"
        assert allocation.remarks == "For onboarding"

    def test_allocate_already_allocated_asset_fails(self, asset, employee,
                                                    employee_factory,
                                                    mock_notification_service):
        """Re-allocating an ALLOCATED asset raises INVALID_STATUS_TRANSITION."""
        AllocationService.allocate(asset=asset, employee=employee)
        other = employee_factory(first_name="Jane")

        with pytest.raises(AFValidationError) as exc:
            AllocationService.allocate(asset=asset, employee=other)
        assert exc.value.app_code == error_codes.INVALID_STATUS_TRANSITION

    def test_allocate_maintenance_asset_fails(self, asset_factory, category, employee,
                                              mock_notification_service):
        """An IN_MAINTENANCE asset cannot be allocated."""
        broken = asset_factory(name="Broken", category=category,
                               status=Asset.Status.IN_MAINTENANCE)
        with pytest.raises(AFValidationError) as exc:
            AllocationService.allocate(asset=broken, employee=employee)
        assert exc.value.app_code == error_codes.INVALID_STATUS_TRANSITION

    def test_allocate_retired_asset_fails(self, asset_factory, category, employee,
                                          mock_notification_service):
        """A RETIRED asset cannot be allocated."""
        retired = asset_factory(name="Old", category=category,
                                status=Asset.Status.RETIRED)
        with pytest.raises(AFValidationError) as exc:
            AllocationService.allocate(asset=retired, employee=employee)
        assert exc.value.app_code == error_codes.INVALID_STATUS_TRANSITION

    def test_allocate_to_inactive_employee_fails(self, asset, employee_factory,
                                                 mock_notification_service):
        """An inactive/exited employee cannot receive an allocation."""
        inactive = employee_factory(first_name="Exited")
        inactive.is_active = False  # Employee.is_active is the flag the service checks
        inactive.save(update_fields=["is_active"])
        with pytest.raises(AFValidationError) as exc:
            AllocationService.allocate(asset=asset, employee=inactive)
        assert exc.value.app_code == error_codes.DATA_VALIDATION_FAILED

    def test_failed_allocation_leaves_asset_untouched(self, asset_factory, category,
                                                      employee,
                                                      mock_notification_service):
        """A rejected allocation must not mutate the asset (no partial writes)."""
        broken = asset_factory(name="Broken", category=category,
                               status=Asset.Status.IN_MAINTENANCE)
        with pytest.raises(AFValidationError):
            AllocationService.allocate(asset=broken, employee=employee)

        broken.refresh_from_db()
        assert broken.status == Asset.Status.IN_MAINTENANCE
        assert broken.current_owner is None
        assert broken.current_allocation is None
        assert not AssetAllocation.objects.filter(asset=broken).exists()


# ===========================================================================
# 2. SERVICE — return_asset()
# ===========================================================================

class TestReturnService:
    """AllocationService.return_asset() business rules."""

    def test_return_active_allocation_succeeds(self, asset, employee,
                                               mock_notification_service):
        """Returning an ACTIVE allocation frees the asset."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        returned = AllocationService.return_asset(allocation, return_condition="GOOD")

        assert returned.status == AssetAllocation.Status.RETURNED
        assert returned.returned_at is not None
        assert returned.return_condition == "GOOD"

        asset.refresh_from_db()
        assert asset.status == Asset.Status.AVAILABLE
        assert asset.current_owner is None
        assert asset.current_allocation is None

    def test_return_without_remarks_keeps_original(self, asset, employee,
                                                   mock_notification_service):
        """Returning with no remarks does not wipe existing remarks."""
        allocation = AllocationService.allocate(
            asset=asset, employee=employee, remarks="original note",
        )
        AllocationService.return_asset(allocation, return_condition="FAIR")
        allocation.refresh_from_db()
        assert allocation.remarks == "original note"

    def test_return_with_remarks_overrides(self, asset, employee,
                                           mock_notification_service):
        """Returning with remarks overwrites the stored remarks."""
        allocation = AllocationService.allocate(
            asset=asset, employee=employee, remarks="original note",
        )
        AllocationService.return_asset(allocation, return_condition="DAMAGED",
                                        remarks="damaged on return")
        allocation.refresh_from_db()
        assert allocation.remarks == "damaged on return"

    def test_return_already_returned_fails(self, asset, employee,
                                           mock_notification_service):
        """Returning a RETURNED allocation raises INVALID_STATUS_TRANSITION."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.return_asset(allocation, return_condition="GOOD")

        with pytest.raises(AFValidationError) as exc:
            AllocationService.return_asset(allocation, return_condition="GOOD")
        assert exc.value.app_code == error_codes.INVALID_STATUS_TRANSITION

    def test_return_cancelled_allocation_fails(self, asset, employee,
                                               allocation_factory,
                                               mock_notification_service):
        """Only ACTIVE allocations are returnable — CANCELLED is rejected."""
        allocation = allocation_factory(
            asset=asset, employee=employee,
            status=AssetAllocation.Status.CANCELLED,
        )
        with pytest.raises(AFValidationError) as exc:
            AllocationService.return_asset(allocation)
        assert exc.value.app_code == error_codes.INVALID_STATUS_TRANSITION


# ===========================================================================
# 3. FULL LIFECYCLE — allocate -> return -> re-allocate
# ===========================================================================

class TestAllocationLifecycle:
    """The complete happy path the user cares about, across owners."""

    def test_allocate_return_reallocate_to_new_owner(self, asset, employee,
                                                     employee_factory,
                                                     mock_notification_service):
        """Same asset flows: emp A -> return -> emp B."""
        alloc1 = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.return_asset(alloc1, return_condition="GOOD")

        new_emp = employee_factory(first_name="Second")
        alloc2 = AllocationService.allocate(asset=asset, employee=new_emp)

        assert alloc2.status == AssetAllocation.Status.ACTIVE
        assert alloc2.employee == new_emp
        assert alloc1.allocation_number != alloc2.allocation_number

        asset.refresh_from_db()
        assert asset.status == Asset.Status.ALLOCATED
        assert asset.current_owner == new_emp
        assert asset.current_allocation == alloc2

    def test_repeated_cycles_keep_one_active_allocation(self, asset, employee,
                                                        mock_notification_service):
        """Allocate/return the same asset+employee twice; history accumulates."""
        for _ in range(2):
            alloc = AllocationService.allocate(asset=asset, employee=employee)
            AllocationService.return_asset(alloc, return_condition="GOOD")

        allocs = AssetAllocation.objects.filter(asset=asset)
        assert allocs.count() == 2
        assert allocs.filter(status=AssetAllocation.Status.ACTIVE).count() == 0
        assert allocs.filter(status=AssetAllocation.Status.RETURNED).count() == 2

        asset.refresh_from_db()
        assert asset.status == Asset.Status.AVAILABLE

    def test_cannot_reallocate_before_return(self, asset, employee,
                                             employee_factory,
                                             mock_notification_service):
        """The asset stays locked to its owner until it is returned."""
        AllocationService.allocate(asset=asset, employee=employee)
        other = employee_factory(first_name="Impatient")

        with pytest.raises(AFValidationError):
            AllocationService.allocate(asset=asset, employee=other)


# ===========================================================================
# 4. MODEL — constraint & representation
# ===========================================================================

class TestAssetAllocationModel:
    def test_str_returns_allocation_number(self, asset, employee,
                                           mock_notification_service):
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        assert str(allocation) == allocation.allocation_number

    def test_unique_active_allocation_per_asset(self, asset, employee,
                                                employee_factory,
                                                allocation_factory):
        """DB guards against two ACTIVE allocations for one asset (defense-in-depth)."""
        allocation_factory(asset=asset, employee=employee,
                           status=AssetAllocation.Status.ACTIVE)
        other = employee_factory(first_name="Dup")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                allocation_factory(asset=asset, employee=other,
                                   status=AssetAllocation.Status.ACTIVE)


# ===========================================================================
# 5. API — access control (auth + role)
# ===========================================================================

class TestAllocationAccessControl:
    base_url = "/api/v1/allocations/"

    def test_unauthenticated_is_rejected(self, api_client, tenant):
        response = api_client.get(self.base_url)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
        )
        assert response.data["code"] == error_codes.PERMISSION_DENIED

    def test_employee_can_read_allocations(self, employee_api_client):
        response = employee_api_client.get(self.base_url)
        assert response.status_code == status.HTTP_200_OK

    def test_employee_cannot_allocate(self, employee_api_client, asset, employee,
                                      mock_notification_service):
        response = employee_api_client.post(f"{self.base_url}allocate/", data={
            "asset": str(asset.id), "employee": str(employee.id),
        }, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["code"] == error_codes.PERMISSION_DENIED

        asset.refresh_from_db()
        assert asset.status == Asset.Status.AVAILABLE

    def test_employee_cannot_return(self, employee_api_client, asset, employee,
                                    mock_notification_service):
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = employee_api_client.post(
            f"{self.base_url}{allocation.id}/return/", data={}, format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["code"] == error_codes.PERMISSION_DENIED


# ===========================================================================
# 6. API — allocate action (success + normalized error contract)
# ===========================================================================

class TestAllocateEndpoint:
    base_url = "/api/v1/allocations/"

    def _allocate(self, client, **data):
        return client.post(f"{self.base_url}allocate/", data=data, format="json")

    def test_hr_allocates_successfully(self, hr_api_client, asset, employee,
                                       mock_notification_service):
        response = self._allocate(hr_api_client, asset=str(asset.id),
                                  employee=str(employee.id), remarks="Project X")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "ACTIVE"
        # to_representation nests related objects
        assert response.data["asset"]["asset_code"] == asset.asset_code
        assert response.data["employee"]["name"] == employee.get_full_name()

        asset.refresh_from_db()
        assert asset.status == Asset.Status.ALLOCATED
        assert asset.current_owner_id == employee.id

    def test_assigned_by_taken_from_caller_profile(self, hr_api_client, hr_user,
                                                   asset, employee, employee_factory,
                                                   mock_notification_service):
        assigner = employee_factory(user=hr_user, first_name="HR", last_name="Boss")
        response = self._allocate(hr_api_client, asset=str(asset.id),
                                  employee=str(employee.id))
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["assigned_by"]["id"] == assigner.id

    def test_allocate_unavailable_asset_returns_custom_error(
        self, hr_api_client, asset_factory, category, employee,
        mock_notification_service,
    ):
        """Business error -> normalized {message, code}, NOT a Django default."""
        broken = asset_factory(name="Broken", category=category,
                               status=Asset.Status.IN_MAINTENANCE)
        response = self._allocate(hr_api_client, asset=str(broken.id),
                                  employee=str(employee.id))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == error_codes.INVALID_STATUS_TRANSITION
        assert response.data["message"] == "Invalid status transition."
        # No leaked DRF/Django keys
        assert set(response.data.keys()) == {"message", "code"}

    def test_allocate_inactive_employee_returns_custom_error(
        self, hr_api_client, asset, employee_factory, mock_notification_service,
    ):
        inactive = employee_factory(first_name="Exited")
        inactive.is_active = False  # Employee.is_active is the flag the service checks
        inactive.save(update_fields=["is_active"])
        response = self._allocate(hr_api_client, asset=str(asset.id),
                                  employee=str(inactive.id))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == error_codes.DATA_VALIDATION_FAILED
        assert response.data["message"] == "Cannot allocate to an inactive or exited employee."

    def test_allocate_missing_asset_is_normalized(self, hr_api_client, employee,
                                                  mock_notification_service):
        """Serializer field errors are flattened, not returned as {field: [...]}."""
        response = self._allocate(hr_api_client, employee=str(employee.id))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == error_codes.DATA_VALIDATION_FAILED
        assert isinstance(response.data["message"], str)
        assert "asset" in response.data["message"].lower()

    def test_allocate_nonexistent_asset_is_normalized(self, hr_api_client, employee,
                                                      mock_notification_service):
        response = self._allocate(hr_api_client, asset=str(uuid.uuid4()),
                                  employee=str(employee.id))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == error_codes.DATA_VALIDATION_FAILED
        assert isinstance(response.data["message"], str)


# ===========================================================================
# 7. API — return action (success + normalized error contract)
# ===========================================================================

class TestReturnEndpoint:
    base_url = "/api/v1/allocations/"

    def test_hr_returns_successfully(self, hr_api_client, asset, employee,
                                     mock_notification_service):
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = hr_api_client.post(
            f"{self.base_url}{allocation.id}/return/",
            data={"return_condition": "GOOD", "remarks": "back in one piece"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "RETURNED"
        assert response.data["return_condition"] == "GOOD"
        asset.refresh_from_db()
        assert asset.status == Asset.Status.AVAILABLE
        assert asset.current_allocation is None

    def test_return_already_returned_returns_custom_error(
        self, hr_api_client, asset, employee, mock_notification_service,
    ):
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.return_asset(allocation)
        response = hr_api_client.post(
            f"{self.base_url}{allocation.id}/return/",
            data={"return_condition": "GOOD"}, format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == error_codes.INVALID_STATUS_TRANSITION
        assert response.data["message"] == "Invalid status transition."

    def test_return_unknown_allocation_is_normalized_404(
        self, hr_api_client, mock_notification_service,
    ):
        """A missing object yields the normalized RECORD_NOT_FOUND body."""
        response = hr_api_client.post(
            f"{self.base_url}{uuid.uuid4()}/return/", data={}, format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["code"] == error_codes.RECORD_NOT_FOUND
        assert set(response.data.keys()) == {"message", "code"}


# ===========================================================================
# 8. API — list / retrieve / filter
# ===========================================================================

class TestAllocationReadEndpoints:
    base_url = "/api/v1/allocations/"

    def test_retrieve_nests_related_objects(self, hr_api_client, asset, employee,
                                            employee_factory,
                                            mock_notification_service):
        assigner = employee_factory(first_name="Assigner", last_name="One")
        allocation = AllocationService.allocate(
            asset=asset, employee=employee, assigned_by=assigner,
        )
        response = hr_api_client.get(f"{self.base_url}{allocation.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["asset"]["id"] == asset.id
        assert response.data["employee"]["id"] == employee.id
        assert response.data["assigned_by"]["name"] == assigner.get_full_name()

    def test_filter_by_status(self, hr_api_client, asset_factory, category, employee,
                              mock_notification_service):
        a1 = asset_factory(name="A1", category=category)
        a2 = asset_factory(name="A2", category=category)
        AllocationService.allocate(asset=a1, employee=employee)          # ACTIVE
        alloc2 = AllocationService.allocate(asset=a2, employee=employee)
        AllocationService.return_asset(alloc2, return_condition="GOOD")  # RETURNED

        response = hr_api_client.get(f"{self.base_url}?status=ACTIVE")
        assert response.status_code == status.HTTP_200_OK
        results = response.data.get("results", response.data)
        statuses = {row["status"] for row in results}
        assert statuses == {"ACTIVE"}


# ===========================================================================
# 9. API — return_condition validation (ChoiceField)
# ===========================================================================

class TestReturnConditionValidation:
    base_url = "/api/v1/allocations/"

    def test_return_with_valid_condition_good(self, hr_api_client, asset, employee,
                                              mock_notification_service):
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = hr_api_client.post(
            f"{self.base_url}{allocation.id}/return/",
            data={"return_condition": "GOOD"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["return_condition"] == "GOOD"

    def test_return_with_valid_condition_damaged(self, hr_api_client, asset, employee,
                                                 mock_notification_service):
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = hr_api_client.post(
            f"{self.base_url}{allocation.id}/return/",
            data={"return_condition": "DAMAGED", "remarks": "screen cracked"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["return_condition"] == "DAMAGED"

    def test_return_missing_condition_is_rejected(self, hr_api_client, asset, employee,
                                                  mock_notification_service):
        """return_condition is now required — omitting it must fail validation."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = hr_api_client.post(
            f"{self.base_url}{allocation.id}/return/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == error_codes.DATA_VALIDATION_FAILED

    def test_return_invalid_condition_is_rejected(self, hr_api_client, asset, employee,
                                                  mock_notification_service):
        """Free-text garbage values like 'meh' must be rejected."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = hr_api_client.post(
            f"{self.base_url}{allocation.id}/return/",
            data={"return_condition": "meh"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == error_codes.DATA_VALIDATION_FAILED

    def test_return_new_condition_is_rejected(self, hr_api_client, asset, employee,
                                              mock_notification_service):
        """'NEW' is not a valid return condition (excluded from choices)."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = hr_api_client.post(
            f"{self.base_url}{allocation.id}/return/",
            data={"return_condition": "NEW"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ===========================================================================
# 10. API — employee self-return
# ===========================================================================

class TestEmployeeSelfReturn:
    """
    An employee may return their OWN allocation.
    They must NOT be able to return another employee's allocation.
    """
    base_url = "/api/v1/allocations/"

    def _make_linked_client(self, employee_factory, department):
        """
        Build an APIClient whose TenantUser has an employee_profile attached.
        This simulates a real logged-in employee who has a profile record.
        """
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        emp = employee_factory(first_name="Self", last_name="Returner", department=department)
        client = APIClient(SERVER_NAME="test.localhost")
        token = RefreshToken.for_user(emp.user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        return emp, client

    def test_employee_can_return_own_allocation(
        self, asset, employee_factory, department, mock_notification_service,
    ):
        """An employee returns their own allocation — should succeed with 200."""
        emp, client = self._make_linked_client(employee_factory, department)
        allocation = AllocationService.allocate(asset=asset, employee=emp)

        response = client.post(
            f"{self.base_url}{allocation.id}/return/",
            data={"return_condition": "GOOD", "remarks": "done with it"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["status"] == "RETURNED"
        assert response.data["return_condition"] == "GOOD"

        asset.refresh_from_db()
        assert asset.status == Asset.Status.AVAILABLE
        assert asset.current_owner is None

    def test_employee_cannot_return_other_employees_allocation(
        self, asset, employee, employee_factory, department, mock_notification_service,
    ):
        """Employee must not be able to return an allocation assigned to someone else."""
        # employee fixture owns the allocation
        allocation = AllocationService.allocate(asset=asset, employee=employee)

        # a different employee tries to return it
        _, other_client = self._make_linked_client(employee_factory, department)
        response = other_client.post(
            f"{self.base_url}{allocation.id}/return/",
            data={"return_condition": "GOOD"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # allocation must remain ACTIVE
        allocation.refresh_from_db()
        assert allocation.status == AssetAllocation.Status.ACTIVE

    def test_employee_without_profile_cannot_return(
        self, asset, employee, employee_api_client, mock_notification_service,
    ):
        """
        employee_api_client uses a TenantUser that has NO employee_profile.
        The view must reject this with 403.
        """
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = employee_api_client.post(
            f"{self.base_url}{allocation.id}/return/",
            data={"return_condition": "GOOD"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ===========================================================================
# 11. SERVICE — cancel_allocation()
# ===========================================================================

class TestCancelService:
    """AllocationService.cancel_allocation() business rules."""

    def test_cancel_active_allocation_succeeds(self, asset, employee,
                                               mock_notification_service):
        """Cancelling an ACTIVE allocation frees the asset and marks CANCELLED."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        cancelled = AllocationService.cancel_allocation(
            allocation, remarks="Wrong employee assigned"
        )

        assert cancelled.status == AssetAllocation.Status.CANCELLED
        assert cancelled.remarks == "Wrong employee assigned"

        asset.refresh_from_db()
        assert asset.status == Asset.Status.AVAILABLE
        assert asset.current_owner is None
        assert asset.current_allocation is None

    def test_cancel_returned_allocation_fails(self, asset, employee,
                                              mock_notification_service):
        """A RETURNED allocation cannot be cancelled."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.return_asset(allocation, return_condition="GOOD")

        with pytest.raises(AFValidationError) as exc:
            AllocationService.cancel_allocation(allocation, remarks="late")
        assert exc.value.app_code == error_codes.INVALID_STATUS_TRANSITION

    def test_cancel_already_cancelled_fails(self, asset, employee,
                                            mock_notification_service):
        """A CANCELLED allocation cannot be cancelled again."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.cancel_allocation(allocation, remarks="first cancel")

        with pytest.raises(AFValidationError) as exc:
            AllocationService.cancel_allocation(allocation, remarks="second cancel")
        assert exc.value.app_code == error_codes.INVALID_STATUS_TRANSITION

    def test_cancel_allows_reallocation(self, asset, employee, employee_factory,
                                        mock_notification_service):
        """After cancellation the asset can be re-allocated immediately."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.cancel_allocation(allocation, remarks="mistake")

        new_emp = employee_factory(first_name="Replacement")
        new_alloc = AllocationService.allocate(asset=asset, employee=new_emp)
        assert new_alloc.status == AssetAllocation.Status.ACTIVE


# ===========================================================================
# 12. API — cancel action
# ===========================================================================

class TestCancelEndpoint:
    base_url = "/api/v1/allocations/"

    def test_hr_can_cancel_allocation(self, hr_api_client, asset, employee,
                                      mock_notification_service):
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = hr_api_client.post(
            f"{self.base_url}{allocation.id}/cancel/",
            data={"remarks": "Created by mistake"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "CANCELLED"

        asset.refresh_from_db()
        assert asset.status == Asset.Status.AVAILABLE

    def test_cancel_missing_remarks_is_rejected(self, hr_api_client, asset, employee,
                                                mock_notification_service):
        """remarks is required for cancel — omitting it must fail."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = hr_api_client.post(
            f"{self.base_url}{allocation.id}/cancel/",
            data={},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == error_codes.DATA_VALIDATION_FAILED

    def test_employee_cannot_cancel(self, employee_api_client, asset, employee,
                                    mock_notification_service):
        """Regular employees must not be able to cancel any allocation."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        response = employee_api_client.post(
            f"{self.base_url}{allocation.id}/cancel/",
            data={"remarks": "I want to cancel this"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        allocation.refresh_from_db()
        assert allocation.status == AssetAllocation.Status.ACTIVE

    def test_cancel_returned_allocation_returns_custom_error(
        self, hr_api_client, asset, employee, mock_notification_service,
    ):
        """Cancelling a non-ACTIVE allocation returns normalized error."""
        allocation = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.return_asset(allocation, return_condition="GOOD")

        response = hr_api_client.post(
            f"{self.base_url}{allocation.id}/cancel/",
            data={"remarks": "too late"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == error_codes.INVALID_STATUS_TRANSITION

    def test_cancel_unknown_allocation_is_normalized_404(
        self, hr_api_client, mock_notification_service,
    ):
        response = hr_api_client.post(
            f"{self.base_url}{uuid.uuid4()}/cancel/",
            data={"remarks": "not found"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["code"] == error_codes.RECORD_NOT_FOUND


# 13. TRANSFER ASSET

class TestTransferService:
    def test_transfer_active_allocation_succeeds(self, asset, employee, employee_factory):
        alloc1 = AllocationService.allocate(asset, employee)
        emp2 = employee_factory(first_name="Emp2")

        alloc2 = AllocationService.transfer_asset(alloc1, emp2, return_condition="GOOD", remarks="Moved")

        # Original alloc is returned
        alloc1.refresh_from_db()
        assert alloc1.status == "RETURNED"
        assert alloc1.return_condition == "GOOD"

        # New alloc is active
        assert alloc2.status == "ACTIVE"
        assert alloc2.employee == emp2

        # Asset belongs to new emp
        asset.refresh_from_db()
        assert asset.status == "ALLOCATED"
        assert asset.current_owner == emp2

    def test_transfer_to_same_employee_fails(self, asset, employee):
        alloc = AllocationService.allocate(asset, employee)
        
        with pytest.raises(AFValidationError) as exc:
            AllocationService.transfer_asset(alloc, employee)
        assert "same employee" in str(exc.value)

    def test_transfer_returned_allocation_fails(self, asset, employee, employee_factory):
        alloc = AllocationService.allocate(asset, employee)
        AllocationService.return_asset(alloc, return_condition="GOOD")
        
        emp2 = employee_factory(first_name="Emp2")
        with pytest.raises(AFValidationError):
            AllocationService.transfer_asset(alloc, emp2)


class TestTransferEndpoint:
    base_url = "/api/v1/allocations/"

    def test_hr_can_transfer_allocation(self, hr_api_client, asset, employee, employee_factory):
        alloc = AllocationService.allocate(asset, employee)
        emp2 = employee_factory(first_name="Emp2")

        response = hr_api_client.post(
            f"{self.base_url}{alloc.id}/transfer/",
            data={
                "new_employee": str(emp2.id),
                "return_condition": "GOOD",
                "remarks": "Transfer demo",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ACTIVE"
        assert response.data["employee"]["id"] == emp2.id

    def test_employee_cannot_transfer(self, employee_api_client, asset, employee, employee_factory):
        alloc = AllocationService.allocate(asset, employee)
        emp2 = employee_factory(first_name="Emp2")

        response = employee_api_client.post(
            f"{self.base_url}{alloc.id}/transfer/",
            data={"new_employee": str(emp2.id)}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
