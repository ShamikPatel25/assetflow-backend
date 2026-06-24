from django.contrib import admin
from apps.assets.models import AssetCategory, Asset


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "category_type", "parent", "is_active"]
    list_filter = ["category_type", "is_active"]
    search_fields = ["name", "code"]


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ["asset_code", "name", "category", "status", "condition", "current_owner"]
    list_filter = ["status", "condition", "category"]
    search_fields = ["asset_code", "name", "serial_number"]
