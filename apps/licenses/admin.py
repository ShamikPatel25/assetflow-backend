from django.contrib import admin
from apps.licenses.models import SoftwareLicense, LicenseAssignment


@admin.register(SoftwareLicense)
class SoftwareLicenseAdmin(admin.ModelAdmin):
    list_display = ["name", "vendor", "license_type", "total_seats", "status", "expiry_date"]
    list_filter = ["status", "license_type"]
    search_fields = ["name", "vendor"]


@admin.register(LicenseAssignment)
class LicenseAssignmentAdmin(admin.ModelAdmin):
    list_display = ["license", "employee", "status", "assigned_at"]
    list_filter = ["status"]
