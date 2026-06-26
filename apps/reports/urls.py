from django.urls import path
from apps.reports.views import DashboardView

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]
