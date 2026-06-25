from django.contrib import admin
from apps.incidents.models import Incident, RepairRecord


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ["incident_number", "title", "asset", "reported_by", "status", "priority"]
    list_filter = ["status", "category", "priority"]
    search_fields = ["incident_number", "title"]


@admin.register(RepairRecord)
class RepairRecordAdmin(admin.ModelAdmin):
    list_display = ["incident", "asset", "vendor_name", "repair_cost", "repair_start_date"]
    search_fields = ["vendor_name"]
