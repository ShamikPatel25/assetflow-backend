from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.licenses.views import SoftwareLicenseViewSet, LicenseAssignmentViewSet

router = DefaultRouter()
router.register("assignments", LicenseAssignmentViewSet, basename="license-assignments")
router.register("", SoftwareLicenseViewSet, basename="licenses")

urlpatterns = [path("", include(router.urls))]
