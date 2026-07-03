import datetime

from django.core.cache import cache
from django.db.models import Count, Sum, Q, Prefetch
from django.utils import timezone
from rest_framework import serializers as drf_serializers, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer

from apps.assets.models import Asset
from apps.allocations.models import AssetAllocation
from apps.employees.models import Employee
from apps.incidents.models import Incident
from apps.licenses.models import SoftwareLicense
from apps.requests.models import AssetRequest
from apps.base.permissions import IsOrganizationAdmin, IsOrgAdminOrHR
from apps.reports.filters import (
    AssetReportFilter,
    AllocationReportFilter,
    IncidentReportFilter,
    LicenseReportFilter,
    EmployeeAssetReportFilter,
)
from apps.reports.serializers import (
    AssetReportSerializer,
    AllocationReportSerializer,
    IncidentReportSerializer,
    LicenseReportSerializer,
    EmployeeAssetReportSerializer,
)


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
        tenant_schema = getattr(request, "tenant", None)
        schema_name = tenant_schema.schema_name if tenant_schema else "public"
        cache_key = f"dashboard_stats_{schema_name}"
        
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        assets_by_status = dict(
            Asset.objects.filter(is_deleted=False)
            .values_list("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        data = {
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
                    is_deleted=False,
                    status=SoftwareLicense.Status.ACTIVE,
                    expiry_date__isnull=False,
                    expiry_date__gte=timezone.now().date(),
                    expiry_date__lte=timezone.now().date() + datetime.timedelta(days=30),
                ).count(),
            },
            "allocations": {
                "active": AssetAllocation.objects.filter(is_deleted=False, status="ACTIVE").count(),
            },
        }
        
        # Cache for 15 minutes (900 seconds)
        cache.set(cache_key, data, timeout=900)
        return Response(data)


# ── Operational reports ──────────────────────────────────────────────────
#
# Each report is a read-only, filterable, searchable, paginated list of records
# plus a `summary` block of aggregates for the *filtered* result set. They reuse
# the project's default filter/search/ordering backends and pagination, so query
# params behave exactly like the rest of the API (e.g. ?page=2&search=..&ordering=..).


class BaseReportView(generics.ListAPIView):
    """
    Base for operational reports.

    Returns the standard paginated payload with an extra top-level `summary`
    key. Reports are management analytics, so access is limited to Org Admin
    and HR Manager. Subclasses set queryset/serializer/filters and override
    `get_summary()`.
    """

    permission_classes = [IsAuthenticated, IsOrgAdminOrHR]

    def get_summary(self, queryset):
        return {}

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        summary = self.get_summary(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data["summary"] = summary
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({"summary": summary, "results": serializer.data})


@extend_schema_view(get=extend_schema(tags=["Reports"], summary="Asset Report"))
class AssetReportView(BaseReportView):
    """Asset inventory report with status/condition/value breakdowns."""

    serializer_class = AssetReportSerializer
    filterset_class = AssetReportFilter
    search_fields = ["asset_code", "name", "serial_number", "brand", "model"]
    ordering_fields = ["asset_code", "name", "purchase_date", "status", "created_at"]
    ordering = ("-created_at",)

    def get_queryset(self):
        return (
            Asset.objects.filter(is_deleted=False)
            .select_related("category", "current_owner")
        )

    def get_summary(self, queryset):
        return {
            "total": queryset.count(),
            "total_value": queryset.aggregate(v=Sum("purchase_cost"))["v"] or 0,
            "by_status": dict(
                queryset.values_list("status").annotate(c=Count("id")).values_list("status", "c")
            ),
            "by_condition": dict(
                queryset.values_list("condition").annotate(c=Count("id")).values_list("condition", "c")
            ),
        }


@extend_schema_view(get=extend_schema(tags=["Reports"], summary="Allocation Report"))
class AllocationReportView(BaseReportView):
    """Allocation activity report across all employees and assets."""

    serializer_class = AllocationReportSerializer
    filterset_class = AllocationReportFilter
    search_fields = [
        "allocation_number", "asset__asset_code",
        "employee__first_name", "employee__last_name",
    ]
    ordering_fields = ["allocated_at", "returned_at", "status", "created_at"]
    ordering = ("-allocated_at",)

    def get_queryset(self):
        return (
            AssetAllocation.objects.filter(is_deleted=False)
            .select_related("asset", "employee", "employee__department")
        )

    def get_summary(self, queryset):
        by_status = dict(
            queryset.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )
        return {
            "total": queryset.count(),
            "active": by_status.get("ACTIVE", 0),
            "returned": by_status.get("RETURNED", 0),
            "cancelled": by_status.get("CANCELLED", 0),
        }


@extend_schema_view(get=extend_schema(tags=["Reports"], summary="Incident Report"))
class IncidentReportView(BaseReportView):
    """Incident report with priority/status breakdowns and repair costs."""

    serializer_class = IncidentReportSerializer
    filterset_class = IncidentReportFilter
    search_fields = ["incident_number", "title", "asset__asset_code"]
    ordering_fields = ["opened_at", "priority", "status", "created_at"]
    ordering = ("-opened_at",)

    def get_queryset(self):
        return (
            Incident.objects.filter(is_deleted=False)
            .select_related("asset", "reported_by", "assigned_to")
            .annotate(
                total_repair_cost=Sum(
                    "repairs__repair_cost",
                    filter=Q(repairs__is_deleted=False),
                )
            )
        )

    def get_summary(self, queryset):
        return {
            "total": queryset.count(),
            "by_status": dict(
                queryset.values_list("status").annotate(c=Count("id")).values_list("status", "c")
            ),
            "by_priority": dict(
                queryset.values_list("priority").annotate(c=Count("id")).values_list("priority", "c")
            ),
            "by_category": dict(
                queryset.values_list("category").annotate(c=Count("id")).values_list("category", "c")
            ),
            "total_repair_cost": Incident.objects.filter(
                id__in=queryset.values("id")
            ).aggregate(
                v=Sum("repairs__repair_cost", filter=Q(repairs__is_deleted=False))
            )["v"] or 0,
        }


@extend_schema_view(get=extend_schema(tags=["Reports"], summary="License Report"))
class LicenseReportView(BaseReportView):
    """Software license utilization and expiry report."""

    serializer_class = LicenseReportSerializer
    filterset_class = LicenseReportFilter
    search_fields = ["name", "vendor"]
    ordering_fields = ["name", "expiry_date", "created_at"]
    ordering = ("-created_at",)

    def get_queryset(self):
        return SoftwareLicense.objects.filter(is_deleted=False)

    def get_summary(self, queryset):
        today = timezone.now().date()
        by_status = dict(
            queryset.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )
        return {
            "total": queryset.count(),
            "active": by_status.get("ACTIVE", 0),
            "expired": by_status.get("EXPIRED", 0),
            "cancelled": by_status.get("CANCELLED", 0),
            "expiring_soon": queryset.filter(
                status=SoftwareLicense.Status.ACTIVE,
                expiry_date__isnull=False,
                expiry_date__gte=today,
                expiry_date__lte=today + datetime.timedelta(days=30),
            ).count(),
            "total_seats": queryset.aggregate(v=Sum("total_seats"))["v"] or 0,
            "total_cost": queryset.aggregate(v=Sum("cost"))["v"] or 0,
        }


@extend_schema_view(get=extend_schema(tags=["Reports"], summary="Employee Asset Report"))
class EmployeeAssetReportView(BaseReportView):
    """Per-employee report of the assets each employee currently holds."""

    serializer_class = EmployeeAssetReportSerializer
    filterset_class = EmployeeAssetReportFilter
    search_fields = ["first_name", "last_name", "employee_code"]
    ordering_fields = ["first_name", "employee_code", "created_at"]
    ordering = ("first_name",)

    def get_queryset(self):
        active_allocations = (
            AssetAllocation.objects.filter(status="ACTIVE", is_deleted=False)
            .select_related("asset")
        )
        return (
            Employee.objects.filter(is_deleted=False)
            .select_related("department")
            .prefetch_related(
                Prefetch("allocations", queryset=active_allocations, to_attr="active_allocations")
            )
        )

    def get_summary(self, queryset):
        active = AssetAllocation.objects.filter(
            status="ACTIVE", is_deleted=False, employee__in=queryset
        )
        return {
            "total_employees": queryset.count(),
            "employees_with_assets": active.values("employee").distinct().count(),
            "total_assets_allocated": active.count(),
        }
