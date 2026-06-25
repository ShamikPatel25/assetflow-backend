from django.contrib import admin
from apps.requests.models import AssetRequest


@admin.register(AssetRequest)
class AssetRequestAdmin(admin.ModelAdmin):
    list_display = ["request_number", "requested_by", "category", "priority", "status", "created_at"]
    list_filter = ["status", "priority"]
    search_fields = ["request_number"]
