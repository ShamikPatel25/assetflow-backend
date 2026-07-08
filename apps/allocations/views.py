from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema_view, extend_schema

from apps.base.permissions import IsOrgAdminOrHROrReadOnly, IsOrgAdminOrHR
from apps.base.views import ReadOnlyViewSet
from apps.allocations.models import AssetAllocation
from apps.allocations.serializers import (
    AssetAllocationSerializer,
    AllocateSerializer,
    ReturnSerializer,
    CancelSerializer,
    TransferSerializer,
)
from apps.allocations.services import AllocationService


@extend_schema_view(
    list=extend_schema(tags=["Allocations"]),
    retrieve=extend_schema(tags=["Allocations"]),
    allocate=extend_schema(
        tags=["Allocations"],
        summary="Allocate Asset to Employee",
        request=AllocateSerializer,
        responses={201: AssetAllocationSerializer},
    ),
    return_asset=extend_schema(
        tags=["Allocations"],
        summary="Return Allocated Asset",
        description=(
            "HR / Org Admin can return any active allocation. "
            "An employee can only return their own allocation."
        ),
        request=ReturnSerializer,
        responses={200: AssetAllocationSerializer},
    ),
    cancel=extend_schema(
        tags=["Allocations"],
        summary="Cancel Allocation",
        description=(
            "Cancels an active allocation without recording a return condition. "
            "Use this for wrong assignments or administrative corrections. "
            "A mandatory reason must be provided for the audit trail."
        ),
        request=CancelSerializer,
        responses={200: AssetAllocationSerializer},
    ),
    transfer=extend_schema(
        tags=["Allocations"],
        summary="Transfer Allocation",
        description=(
            "Transfers an active allocation directly to a new employee. "
            "Closes the current allocation and creates a new one in a single step."
        ),
        request=TransferSerializer,
        responses={200: AssetAllocationSerializer},
    ),
)
class AssetAllocationViewSet(ReadOnlyViewSet):
    """
    Asset allocation management.
    GET    /api/v1/allocations/               -> list
    GET    /api/v1/allocations/{id}/           -> detail
    POST   /api/v1/allocations/allocate/       -> allocate asset to employee
    POST   /api/v1/allocations/{id}/return/    -> return allocated asset
    POST   /api/v1/allocations/{id}/cancel/    -> cancel allocation
    POST   /api/v1/allocations/{id}/transfer/  -> transfer allocation to another employee
    """

    queryset = AssetAllocation.objects.select_related("asset", "employee", "assigned_by")
    serializer_class = AssetAllocationSerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrHROrReadOnly]
    search_fields = ["allocation_number", "asset__asset_code", "employee__first_name"]
    ordering_fields = ["allocated_at", "created_at", "status"]
    filterset_fields = ["status", "asset", "employee"]

    @action(detail=False, methods=["post"], url_path="allocate",
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def allocate(self, request):
        serializer = AllocateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        asset = serializer.validated_data["asset"]
        employee = serializer.validated_data["employee"]

        # Find the assigner (employee profile of the logged-in user)
        assigned_by = getattr(request.user, "employee_profile", None)

        allocation = AllocationService.allocate(
            asset=asset,
            employee=employee,
            assigned_by=assigned_by,
            expected_return_date=serializer.validated_data.get("expected_return_date"),
            remarks=serializer.validated_data.get("remarks"),
        )

        return Response(
            AssetAllocationSerializer(allocation).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="return",
            permission_classes=[IsAuthenticated])
    def return_asset(self, request, pk=None):
        """
        HR / Org Admin can return any active allocation.
        A regular employee can only return an allocation assigned to themselves.
        """
        allocation = self.get_object()
        user = request.user
        role = getattr(user, "role", None)
        is_privileged = role in ("ORGANIZATION_ADMIN", "HR_MANAGER")

        if not is_privileged:
            # Employee must own this allocation
            employee_profile = getattr(user, "employee_profile", None)
            if employee_profile is None or allocation.employee_id != employee_profile.id:
                raise PermissionDenied(
                    "You can only return an allocation that is assigned to you."
                )

        serializer = ReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        allocation = AllocationService.return_asset(
            allocation=allocation,
            return_condition=serializer.validated_data["return_condition"],
            remarks=serializer.validated_data.get("remarks"),
        )

        return Response(AssetAllocationSerializer(allocation).data)

    @action(detail=True, methods=["post"], url_path="cancel",
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def cancel(self, request, pk=None):
        """
        Cancel an active allocation (HR / Org Admin only).
        Use when the allocation was made in error or must be administratively revoked.
        A mandatory reason is required for the audit trail.
        """
        allocation = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        allocation = AllocationService.cancel_allocation(
            allocation=allocation,
            remarks=serializer.validated_data["remarks"],
        )

        return Response(AssetAllocationSerializer(allocation).data)

    @action(detail=True, methods=["post"], url_path="transfer",
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def transfer(self, request, pk=None):
        """
        Transfer an active allocation to another employee directly (HR / Org Admin only).
        """
        allocation = self.get_object()
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assigned_by = getattr(request.user, "employee_profile", None)

        new_allocation = AllocationService.transfer_asset(
            allocation=allocation,
            new_employee=serializer.validated_data["new_employee"],
            assigned_by=assigned_by,
            return_condition=serializer.validated_data.get("return_condition"),
            expected_return_date=serializer.validated_data.get("expected_return_date"),
            remarks=serializer.validated_data.get("remarks"),
        )

        return Response(AssetAllocationSerializer(new_allocation).data)
