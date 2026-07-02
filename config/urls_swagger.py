from django.urls import path, include

# This file combines both public and tenant URLs 
# strictly for drf-spectacular schema generation
# so that the Swagger UI on the platform domain shows ALL endpoints.

urlpatterns = [
    # --- Public / Platform Endpoints ---
    path("api/v1/platform/", include("apps.tenants.urls")),
    path("api/v1/platform/auth/", include("apps.accounts.urls_platform")),

    # --- Tenant Endpoints ---
    path("api/v1/auth/", include("apps.employees.urls_auth")),
    path("api/v1/organization/", include("apps.tenants.urls_tenant")),
    path("api/v1/employees/", include("apps.employees.urls")),
    path("api/v1/departments/", include("apps.employees.urls_departments")),
    path("api/v1/assets/", include("apps.assets.urls")),
    path("api/v1/asset-categories/", include("apps.assets.urls_categories")),
    path("api/v1/allocations/", include("apps.allocations.urls")),
    path("api/v1/asset-requests/", include("apps.requests.urls")),
    path("api/v1/incidents/", include("apps.incidents.urls")),
    path("api/v1/licenses/", include("apps.licenses.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/audit-logs/", include("apps.audit.urls")),
    path("api/v1/reports/", include("apps.reports.urls")),
]
