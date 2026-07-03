"""
Tests for Asset Allocation module.

Covers the entire asset lifecycle:
- Allocation rules (only AVAILABLE assets, only active employees)
- Return flow (sets asset back to AVAILABLE, clears owner)
- Double-allocation prevention (unique constraint)
- Permission checks (only HR/Admin can allocate)
- Service layer business logic (AllocationService)
- Cross-module impact (allocation changes asset status)
"""
from apps.allocations.services import AllocationService
from apps.base.errors import AFValidationError
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


# 1. ALLOCATION SERVICE LOGIC (unit tests)

class TestAllocationServiceLogic:
    """AllocationService.allocate() and .return_asset() rules."""

    def test_allocate_available_asset_succeeds(self, asset, employee,
                                               mock_notification_service):
        """Allocating an AVAILABLE asset creates an ACTIVE allocation."""

        allocation = AllocationService.allocate(asset=asset, employee=employee)
        assert allocation.status == "ACTIVE"
        assert allocation.employee == employee
        asset.refresh_from_db()
        assert asset.status == "ALLOCATED"
        assert asset.current_owner == employee
        assert asset.current_allocation == allocation

    def test_allocate_already_allocated_asset_fails(self, asset, employee,
                                                    employee_factory,
                                                    mock_notification_service):
        """Cannot allocate an asset that is already ALLOCATED."""

        AllocationService.allocate(asset=asset, employee=employee)
        second_employee = employee_factory(first_name="Jane")
        with pytest.raises(AFValidationError):
            AllocationService.allocate(asset=asset, employee=second_employee)

    def test_allocate_maintenance_asset_fails(self, asset_factory, employee, category,
                                              mock_notification_service):
        """Cannot allocate an asset in IN_MAINTENANCE status."""

        broken_asset = asset_factory(name="Broken", category=category,
                                      status="IN_MAINTENANCE")
        with pytest.raises(AFValidationError):
            AllocationService.allocate(asset=broken_asset, employee=employee)

    def test_allocate_retired_asset_fails(self, asset_factory, employee, category,
                                          mock_notification_service):
        """Cannot allocate a RETIRED asset."""

        retired = asset_factory(name="Old", category=category, status="RETIRED")
        with pytest.raises(AFValidationError):
            AllocationService.allocate(asset=retired, employee=employee)

    def test_allocate_to_inactive_employee_fails(self, asset, employee_factory,
                                                  department, mock_notification_service):
        """Cannot allocate to an employee with is_active=False."""

        inactive_emp = employee_factory(first_name="Exited", is_active=False,
                                        department=department)
        # Force-deactivate the employee model too
        inactive_emp.is_active = False
        inactive_emp.save()

        with pytest.raises(AFValidationError):
            AllocationService.allocate(asset=asset, employee=inactive_emp)


# 2. RETURN FLOW

class TestReturnFlow:
    """Asset return via AllocationService.return_asset()."""

    def test_return_active_allocation_succeeds(self, asset, employee,
                                               mock_notification_service):
        """Returning an ACTIVE allocation sets status correctly."""

        allocation = AllocationService.allocate(asset=asset, employee=employee)
        returned = AllocationService.return_asset(allocation, return_condition="GOOD")

        assert returned.status == "RETURNED"
        assert returned.returned_at is not None
        assert returned.return_condition == "GOOD"

        asset.refresh_from_db()
        assert asset.status == "AVAILABLE"
        assert asset.current_owner is None
        assert asset.current_allocation is None

    def test_return_already_returned_allocation_fails(self, asset, employee,
                                                      mock_notification_service):
        """Cannot return an allocation that is already RETURNED."""

        allocation = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.return_asset(allocation)

        with pytest.raises(AFValidationError):
            AllocationService.return_asset(allocation)

    def test_asset_available_for_reallocation_after_return(self, asset, employee,
                                                           employee_factory,
                                                           mock_notification_service):
        """After return, the same asset can be allocated to someone else."""

        alloc1 = AllocationService.allocate(asset=asset, employee=employee)
        AllocationService.return_asset(alloc1)

        new_emp = employee_factory(first_name="New")
        alloc2 = AllocationService.allocate(asset=asset, employee=new_emp)
        assert alloc2.status == "ACTIVE"
        assert alloc2.employee == new_emp


# 3. API PERMISSIONS

class TestAllocationAPIPermissions:
    """Verify allocation API endpoint access by role."""

    url = "/api/v1/allocations/"

    def test_unauthenticated_cannot_list_allocations(self, api_client, tenant):
        """No JWT → blocked."""
        response = api_client.get(self.url)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    def test_employee_can_see_allocations(self, employee_api_client):
        """EMPLOYEE can read allocations."""
        response = employee_api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

    def test_employee_cannot_create_allocation(self, employee_api_client, asset, employee):
        """EMPLOYEE cannot directly allocate assets."""
        response = employee_api_client.post(self.url, data={
            "asset": str(asset.id), "employee": str(employee.id),
        })
        assert response.status_code in [status.HTTP_403_FORBIDDEN]
