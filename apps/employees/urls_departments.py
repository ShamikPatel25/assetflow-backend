from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.employees.views import DepartmentViewSet

router = DefaultRouter()
router.register("", DepartmentViewSet, basename="departments")

urlpatterns = [
    path("", include(router.urls)),
]
