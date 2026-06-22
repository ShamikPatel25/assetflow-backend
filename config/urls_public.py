from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(urlconf="config.urls_swagger"), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # Platform endpoints (public schema)
    path("api/v1/platform/", include("apps.tenants.urls")),
    path("api/v1/platform/auth/", include("apps.accounts.urls_platform")),
]
