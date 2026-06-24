from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.assets.views import AssetCategoryViewSet

router = DefaultRouter()
router.register("", AssetCategoryViewSet, basename="asset-categories")

urlpatterns = [path("", include(router.urls))]
