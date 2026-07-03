from django.urls import path
from apps.reports.views import (
    DashboardView,
    AssetReportView,
    AllocationReportView,
    IncidentReportView,
    LicenseReportView,
    EmployeeAssetReportView,
)

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("assets/", AssetReportView.as_view(), name="report-assets"),
    path("allocations/", AllocationReportView.as_view(), name="report-allocations"),
    path("incidents/", IncidentReportView.as_view(), name="report-incidents"),
    path("licenses/", LicenseReportView.as_view(), name="report-licenses"),
    path("employee-assets/", EmployeeAssetReportView.as_view(), name="report-employee-assets"),
]
