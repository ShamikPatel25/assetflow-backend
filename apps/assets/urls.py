from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.assets.views import AssetViewSet

router = DefaultRouter()
router.register("", AssetViewSet, basename="assets")

urlpatterns = [path("", include(router.urls))]
