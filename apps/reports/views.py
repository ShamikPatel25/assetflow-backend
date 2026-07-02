from django.db.models import Count
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, inline_serializer

from apps.assets.models import Asset
from apps.allocations.models import AssetAllocation
from apps.employees.models import Employee
from apps.incidents.models import Incident
from apps.licenses.models import SoftwareLicense
from apps.requests.models import AssetRequest
from apps.base.permissions import IsOrganizationAdmin


# ── Response serializer for Swagger docs ─────────────────────────────────

DashboardResponseSerializer = inline_serializer(
    "DashboardResponse",
    fields={
        "assets": inline_serializer("AssetStats", fields={
            "total": drf_serializers.IntegerField(),
            "available": drf_serializers.IntegerField(),
            "allocated": drf_serializers.IntegerField(),
            "in_maintenance": drf_serializers.IntegerField(),
            "retired": drf_serializers.IntegerField(),
        }),
        "employees": inline_serializer("EmployeeStats", fields={
            "total": drf_serializers.IntegerField(),
            "active": drf_serializers.IntegerField(),
        }),
        "requests": inline_serializer("RequestStats", fields={
            "pending": drf_serializers.IntegerField(),
            "approved": drf_serializers.IntegerField(),
        }),
        "incidents": inline_serializer("IncidentStats", fields={
            "open": drf_serializers.IntegerField(),
            "in_progress": drf_serializers.IntegerField(),
        }),
        "licenses": inline_serializer("LicenseStats", fields={
            "total": drf_serializers.IntegerField(),
            "active": drf_serializers.IntegerField(),
            "expiring_soon": drf_serializers.IntegerField(),
        }),
        "allocations": inline_serializer("AllocationStats", fields={
            "active": drf_serializers.IntegerField(),
        }),
    },
)


@extend_schema(tags=["Dashboard"])
class DashboardView(APIView):
    """Organization dashboard summary statistics."""

    permission_classes = [IsAuthenticated, IsOrganizationAdmin]

    @extend_schema(
        summary="Dashboard Statistics",
        responses={200: DashboardResponseSerializer},
    )
    def get(self, request):
        assets_by_status = dict(
            Asset.objects.filter(is_deleted=False)
            .values_list("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        return Response({
            "assets": {
                "total": sum(assets_by_status.values()),
                "available": assets_by_status.get("AVAILABLE", 0),
                "allocated": assets_by_status.get("ALLOCATED", 0),
                "in_maintenance": assets_by_status.get("IN_MAINTENANCE", 0),
                "retired": assets_by_status.get("RETIRED", 0),
            },
            "employees": {
                "total": Employee.objects.filter(is_deleted=False).count(),
                "active": Employee.objects.filter(is_deleted=False, is_active=True).count(),
            },
            "requests": {
                "pending": AssetRequest.objects.filter(is_deleted=False, status="PENDING").count(),
                "approved": AssetRequest.objects.filter(is_deleted=False, status="APPROVED").count(),
            },
            "incidents": {
                "open": Incident.objects.filter(is_deleted=False, status="OPEN").count(),
                "in_progress": Incident.objects.filter(is_deleted=False, status="IN_PROGRESS").count(),
            },
            "licenses": {
                "total": SoftwareLicense.objects.filter(is_deleted=False).count(),
                "active": SoftwareLicense.objects.filter(is_deleted=False, is_active=True).count(),
                "expiring_soon": SoftwareLicense.objects.filter(
                    is_deleted=False, is_active=True,
                ).count(),
            },
            "allocations": {
                "active": AssetAllocation.objects.filter(is_deleted=False, status="ACTIVE").count(),
            },
        })
