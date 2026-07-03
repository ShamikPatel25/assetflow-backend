"""
FilterSets for report endpoints.

Each report supports the same conventions as the rest of the API (django-filter
backend) plus explicit date-range filters (``<field>_after`` / ``<field>_before``)
so reports can be scoped to a period. They extend BaseFilterSet so the active
view is available if needed.
"""
from django_filters import rest_framework as filters

from apps.base.filters import BaseFilterSet
from apps.assets.models import Asset
from apps.allocations.models import AssetAllocation
from apps.incidents.models import Incident
from apps.licenses.models import SoftwareLicense
from apps.employees.models import Employee


class AssetReportFilter(BaseFilterSet):
    purchase_date = filters.DateFromToRangeFilter()
    warranty_expiry_date = filters.DateFromToRangeFilter()

    class Meta:
        model = Asset
        fields = ["status", "condition", "category", "purchase_date", "warranty_expiry_date"]


class AllocationReportFilter(BaseFilterSet):
    allocated_at = filters.DateFromToRangeFilter()
    department = filters.UUIDFilter(field_name="employee__department")

    class Meta:
        model = AssetAllocation
        fields = ["status", "asset", "employee", "department", "allocated_at"]


class IncidentReportFilter(BaseFilterSet):
    opened_at = filters.DateFromToRangeFilter()

    class Meta:
        model = Incident
        fields = ["status", "category", "priority", "assigned_to", "opened_at"]


class LicenseReportFilter(BaseFilterSet):
    expiry_date = filters.DateFromToRangeFilter()

    class Meta:
        model = SoftwareLicense
        fields = ["status", "license_type", "vendor", "expiry_date"]


class EmployeeAssetReportFilter(BaseFilterSet):
    class Meta:
        model = Employee
        fields = ["department"]
