from django.contrib import admin
from apps.allocations.models import AssetAllocation


@admin.register(AssetAllocation)
class AssetAllocationAdmin(admin.ModelAdmin):
    list_display = ["allocation_number", "asset", "employee", "status", "allocated_at"]
    list_filter = ["status"]
    search_fields = ["allocation_number", "asset__asset_code"]
