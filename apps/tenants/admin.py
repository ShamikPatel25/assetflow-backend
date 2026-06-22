from django.contrib import admin
from apps.tenants.models import Organization, Domain


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "schema_name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    readonly_fields = ["schema_name", "created_at", "updated_at"]


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ["domain", "tenant", "is_primary", "created_at"]
    list_filter = ["is_primary"]
    search_fields = ["domain"]
