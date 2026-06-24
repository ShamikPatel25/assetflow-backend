from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.allocations.views import AssetAllocationViewSet

router = DefaultRouter()
router.register("", AssetAllocationViewSet, basename="allocations")

urlpatterns = [path("", include(router.urls))]
