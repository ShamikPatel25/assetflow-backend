import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models

from apps.base.models import AbstractBaseModel


class TenantUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class TenantUser(AbstractBaseUser):
    """
    Authentication model for tenant users (ORG_ADMIN, HR_MANAGER, EMPLOYEE).
    Does NOT include Django permissions/staff fields.
    """
    class Role(models.TextChoices):
        ORGANIZATION_ADMIN = "ORGANIZATION_ADMIN", "Organization Admin"
        HR_MANAGER = "HR_MANAGER", "HR Manager"
        EMPLOYEE = "EMPLOYEE", "Employee"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.EMPLOYEE)
    is_active = models.BooleanField(default=False)  # False until invite accepted
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantUserManager()

    USERNAME_FIELD = "email"

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"], name="idx_tenant_user_email"),
            models.Index(fields=["role"], name="idx_tenant_user_role"),
        ]

    def __str__(self):
        return self.email


class Department(AbstractBaseModel):
    """Organization department with optional parent for hierarchy."""

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True, blank=True)
    manager = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_departments",
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["code"], name="idx_department_code"),
            models.Index(fields=["is_active", "is_deleted"], name="idx_dept_active_del"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Employee(AbstractBaseModel):
    """Employee profile linked to a tenant User."""

    user = models.OneToOneField(
        "employees.TenantUser",
        null=False,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=20, null=True, blank=True)
    
    employee_code = models.CharField(max_length=50, unique=True)
    designation = models.CharField(max_length=100, null=True, blank=True)
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employees",
    )
    manager = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="direct_reports",
    )
    joining_date = models.DateField(null=True, blank=True)
    exit_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employee_code"], name="idx_emp_code"),
            models.Index(fields=["department"], name="idx_emp_department"),
            models.Index(fields=["manager"], name="idx_emp_manager"),
            models.Index(fields=["is_active", "is_deleted"], name="idx_emp_active_del"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_code})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
