from django.contrib import admin
from apps.employees.models import Department, Employee


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "code"]


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["employee_code", "first_name", "last_name", "department", "created_at"]
    list_filter = ["department", "is_active"]
    search_fields = ["first_name", "last_name", "employee_code", "email"]
