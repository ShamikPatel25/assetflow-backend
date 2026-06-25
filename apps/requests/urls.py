from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.requests.views import AssetRequestViewSet

router = DefaultRouter()
router.register("", AssetRequestViewSet, basename="asset-requests")

urlpatterns = [path("", include(router.urls))]
