from django.urls import path
from apps.tenants.views_tenant import TenantOrganizationSettingsView

urlpatterns = [
    path("settings/", TenantOrganizationSettingsView.as_view(), name="tenant-organization-settings"),
]
