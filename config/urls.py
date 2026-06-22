from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(urlconf="config.urls"), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # Tenant endpoints
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
