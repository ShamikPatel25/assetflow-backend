from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema_view, extend_schema

from apps.base.permissions import IsOrgAdminOrHR
from apps.base.views import CRUDViewSet
from apps.employees.models import Department, Employee
from apps.employees.serializers import DepartmentSerializer, EmployeeSerializer


@extend_schema_view(
    list=extend_schema(tags=["Departments"]),
    create=extend_schema(tags=["Departments"]),
    retrieve=extend_schema(tags=["Departments"]),
    update=extend_schema(tags=["Departments"]),
    partial_update=extend_schema(tags=["Departments"]),
    destroy=extend_schema(tags=["Departments"]),
)
class DepartmentViewSet(CRUDViewSet):
    """CRUD for departments. Accessible by Org Admin and HR Manager."""

    queryset = Department.objects.select_related("manager")
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrHR]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "code", "created_at"]
    filterset_fields = []


@extend_schema_view(
    list=extend_schema(tags=["Employees"]),
    create=extend_schema(tags=["Employees"]),
    retrieve=extend_schema(tags=["Employees"]),
    update=extend_schema(tags=["Employees"]),
    partial_update=extend_schema(tags=["Employees"]),
    destroy=extend_schema(tags=["Employees"])
)
class EmployeeViewSet(CRUDViewSet):
    """CRUD for employees. Accessible by Org Admin and HR Manager."""

    queryset = Employee.objects.select_related("department", "manager", "user")
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrHR]
    search_fields = ["first_name", "last_name", "employee_code", "email"]
    ordering_fields = ["first_name", "employee_code", "created_at", "joining_date"]
    filterset_fields = ["department"]

    def get_serializer_class(self):
        if self.action == "create":
            from apps.employees.serializers import EmployeeCreateSerializer
            return EmployeeCreateSerializer
        return super().get_serializer_class()

    def perform_destroy(self, instance):
        # Soft delete the employee profile
        super().perform_destroy(instance)
        # Deactivate the associated user account to block login
        instance.user.is_active = False
        instance.user.save()
