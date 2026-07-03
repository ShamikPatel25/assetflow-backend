"""
Read-only serializers for operational reports.

These are intentionally plain (non-model) serializers so that reporting output
is flat, stable, and decoupled from the write-side CRUD serializers. They never
mutate data — reports are strictly read endpoints.
"""
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes


class AssetReportSerializer(serializers.Serializer):
    """One asset row for the asset inventory report."""

    id = serializers.UUIDField()
    asset_code = serializers.CharField()
    name = serializers.CharField()
    category = serializers.SerializerMethodField()
    status = serializers.CharField()
    condition = serializers.CharField()
    brand = serializers.CharField()
    model = serializers.CharField()
    serial_number = serializers.CharField()
    purchase_date = serializers.DateField()
    warranty_expiry_date = serializers.DateField()
    purchase_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    current_owner = serializers.SerializerMethodField()

    def get_category(self, obj) -> str:
        return obj.category.name if obj.category_id else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_current_owner(self, obj):
        if obj.current_owner_id:
            return {"id": obj.current_owner_id, "name": obj.current_owner.get_full_name()}
        return None


class AllocationReportSerializer(serializers.Serializer):
    """One allocation row for the allocation activity report."""

    id = serializers.UUIDField()
    allocation_number = serializers.CharField()
    asset = serializers.SerializerMethodField()
    employee = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    allocated_at = serializers.DateTimeField()
    expected_return_date = serializers.DateField()
    returned_at = serializers.DateTimeField()
    status = serializers.CharField()
    duration_days = serializers.SerializerMethodField()

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_asset(self, obj):
        if obj.asset_id:
            return {"id": obj.asset_id, "asset_code": obj.asset.asset_code, "name": obj.asset.name}
        return None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_employee(self, obj):
        if obj.employee_id:
            return {"id": obj.employee_id, "name": obj.employee.get_full_name()}
        return None

    def get_department(self, obj) -> str:
        dept = getattr(obj.employee, "department", None) if obj.employee_id else None
        return dept.name if dept else None

    def get_duration_days(self, obj) -> int:
        """Days the asset was (or has been) held."""
        if not obj.allocated_at:
            return None
        end = obj.returned_at or timezone.now()
        return (end.date() - obj.allocated_at.date()).days


class IncidentReportSerializer(serializers.Serializer):
    """One incident row for the incident report."""

    id = serializers.UUIDField()
    incident_number = serializers.CharField()
    title = serializers.CharField()
    asset = serializers.SerializerMethodField()
    category = serializers.CharField()
    priority = serializers.CharField()
    status = serializers.CharField()
    reported_by = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()
    opened_at = serializers.DateTimeField()
    resolved_at = serializers.DateTimeField()
    closed_at = serializers.DateTimeField()
    repair_cost = serializers.SerializerMethodField()

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_asset(self, obj):
        if obj.asset_id:
            return {"id": obj.asset_id, "asset_code": obj.asset.asset_code, "name": obj.asset.name}
        return None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_reported_by(self, obj):
        if obj.reported_by_id:
            return {"id": obj.reported_by_id, "name": obj.reported_by.get_full_name()}
        return None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_assigned_to(self, obj):
        if obj.assigned_to_id:
            return {"id": obj.assigned_to_id, "name": obj.assigned_to.get_full_name()}
        return None

    def get_repair_cost(self, obj) -> float:
        """Total repair cost annotated on the queryset (may be None)."""
        return getattr(obj, "total_repair_cost", None)


class LicenseReportSerializer(serializers.Serializer):
    """One license row for the license utilization report."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    vendor = serializers.CharField()
    license_type = serializers.CharField()
    status = serializers.CharField()
    total_seats = serializers.IntegerField()
    used_seats = serializers.IntegerField()
    available_seats = serializers.IntegerField()
    purchase_date = serializers.DateField()
    expiry_date = serializers.DateField()
    days_to_expiry = serializers.SerializerMethodField()
    cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()

    def get_days_to_expiry(self, obj) -> int:
        if not obj.expiry_date:
            return None
        return (obj.expiry_date - timezone.now().date()).days


class EmployeeAssetReportSerializer(serializers.Serializer):
    """One employee row listing the assets they currently hold."""

    id = serializers.UUIDField()
    name = serializers.SerializerMethodField()
    employee_code = serializers.CharField()
    department = serializers.SerializerMethodField()
    asset_count = serializers.SerializerMethodField()
    assets = serializers.SerializerMethodField()

    def get_name(self, obj) -> str:
        return obj.get_full_name()

    def get_department(self, obj) -> str:
        return obj.department.name if obj.department_id else None

    def _allocations(self, obj):
        # Populated via Prefetch(to_attr="active_allocations") in the view.
        return getattr(obj, "active_allocations", [])

    def get_asset_count(self, obj) -> int:
        return len(self._allocations(obj))

    @extend_schema_field(serializers.ListField)
    def get_assets(self, obj):
        rows = []
        for alloc in self._allocations(obj):
            if alloc.asset_id:
                rows.append({
                    "id": alloc.asset_id,
                    "asset_code": alloc.asset.asset_code,
                    "name": alloc.asset.name,
                    "status": alloc.asset.status,
                    "allocation_number": alloc.allocation_number,
                    "allocated_at": alloc.allocated_at,
                })
        return rows
