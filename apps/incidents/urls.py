from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.incidents.views import IncidentViewSet, RepairRecordViewSet

router = DefaultRouter()
router.register("repairs", RepairRecordViewSet, basename="repairs")
router.register("", IncidentViewSet, basename="incidents")

urlpatterns = [path("", include(router.urls))]
