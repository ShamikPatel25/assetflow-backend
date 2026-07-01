from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema_view, extend_schema

from apps.assets.models import Asset
from apps.base.permissions import IsOrgAdminOrHROrReadOnly, IsOrgAdminOrHR
from apps.base.views import ReadOnlyViewSet
from apps.employees.models import Employee
from apps.allocations.models import AssetAllocation
from apps.allocations.serializers import (
    AssetAllocationSerializer,
    AllocateSerializer,
    ReturnSerializer,
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
        request=ReturnSerializer,
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

        asset = Asset.objects.get(pk=serializer.validated_data["asset"])
        employee = Employee.objects.get(pk=serializer.validated_data["employee"])

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
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def return_asset(self, request, pk=None):
        allocation = self.get_object()
        serializer = ReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        allocation = AllocationService.return_asset(
            allocation=allocation,
            return_condition=serializer.validated_data.get("return_condition"),
            remarks=serializer.validated_data.get("remarks"),
        )

        return Response(AssetAllocationSerializer(allocation).data)
