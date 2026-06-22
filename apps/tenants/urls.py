from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.tenants.views import OrganizationViewSet

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organizations")

urlpatterns = [
    path("", include(router.urls)),
]
