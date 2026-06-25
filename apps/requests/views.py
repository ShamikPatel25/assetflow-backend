from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema_view, extend_schema

from apps.assets.models import AssetCategory, Asset
from apps.base.permissions import IsOrganizationAdmin, IsOrgAdminOrHR
from apps.base.views import CRUDViewSet
from apps.employees.models import Employee
from apps.requests.models import AssetRequest
from apps.requests.serializers import (
    AssetRequestSerializer,
    AssetRequestCreateSerializer,
    RejectSerializer,
)
from apps.requests.services import AssetRequestService


@extend_schema_view(
    list=extend_schema(tags=["Asset Requests"]),
    create=extend_schema(
        tags=["Asset Requests"],
        summary="Create Asset Request",
        request=AssetRequestCreateSerializer,
        responses={201: AssetRequestSerializer},
    ),
    retrieve=extend_schema(tags=["Asset Requests"]),
    update=extend_schema(tags=["Asset Requests"]),
    partial_update=extend_schema(tags=["Asset Requests"]),
    destroy=extend_schema(tags=["Asset Requests"]),
    approve=extend_schema(
        tags=["Asset Requests"],
        summary="Approve Asset Request",
        request=None,
        responses={200: AssetRequestSerializer},
    ),
    reject=extend_schema(
        tags=["Asset Requests"],
        summary="Reject Asset Request",
        request=RejectSerializer,
        responses={200: AssetRequestSerializer},
    ),
    cancel=extend_schema(
        tags=["Asset Requests"],
        summary="Cancel Asset Request",
        request=None,
        responses={200: AssetRequestSerializer},
    ),
)
class AssetRequestViewSet(CRUDViewSet):
    """
    Asset request workflow.
    GET    /api/v1/asset-requests/                -> list requests
    POST   /api/v1/asset-requests/                -> create request
    GET    /api/v1/asset-requests/{id}/            -> detail
    POST   /api/v1/asset-requests/{id}/approve/    -> approve
    POST   /api/v1/asset-requests/{id}/reject/     -> reject
    POST   /api/v1/asset-requests/{id}/cancel/     -> cancel
    """

    queryset = AssetRequest.objects.select_related(
        "requested_by", "category", "preferred_asset",
        "approved_by", "rejected_by",
    )
    serializer_class = AssetRequestSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["request_number", "requested_by__first_name", "reason"]
    ordering_fields = ["created_at", "priority", "status"]
    filterset_fields = ["status", "priority", "category"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Employees see only their own requests
        if getattr(user, "role", None) == "EMPLOYEE":
            employee = getattr(user, "employee_profile", None)
            if employee:
                return qs.filter(requested_by=employee)
            return qs.none()
        return qs

    def create(self, request, *args, **kwargs):
        serializer = AssetRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee = getattr(request.user, "employee_profile", None)
        if not employee:
            return Response(
                {"message": "No employee profile linked to this user."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        category = None
        preferred_asset = None
        if serializer.validated_data.get("category"):
            category = AssetCategory.objects.get(pk=serializer.validated_data["category"])
        if serializer.validated_data.get("preferred_asset"):
            preferred_asset = Asset.objects.get(pk=serializer.validated_data["preferred_asset"])

        request_obj = AssetRequestService.create_request(
            employee=employee,
            category=category,
            preferred_asset=preferred_asset,
            reason=serializer.validated_data["reason"],
            priority=serializer.validated_data.get("priority", "MEDIUM"),
        )

        return Response(
            AssetRequestSerializer(request_obj).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="approve",
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def approve(self, request, pk=None):
        request_obj = self.get_object()
        approver = getattr(request.user, "employee_profile", None)
        request_obj = AssetRequestService.approve(request_obj, approved_by=approver)
        return Response(AssetRequestSerializer(request_obj).data)

    @action(detail=True, methods=["post"], url_path="reject",
            permission_classes=[IsAuthenticated, IsOrgAdminOrHR])
    def reject(self, request, pk=None):
        request_obj = self.get_object()
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rejector = getattr(request.user, "employee_profile", None)
        request_obj = AssetRequestService.reject(
            request_obj,
            rejected_by=rejector,
            rejection_reason=serializer.validated_data.get("rejection_reason", ""),
        )
        return Response(AssetRequestSerializer(request_obj).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        request_obj = self.get_object()
        request_obj = AssetRequestService.cancel(request_obj)
        return Response(AssetRequestSerializer(request_obj).data)
