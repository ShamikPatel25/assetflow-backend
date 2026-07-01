"""
Root conftest.py for AssetFlow backend tests.

Since this project uses django-tenants for multi-tenancy, all tenant-level
tests must run inside a tenant schema. This conftest provides:
  1. A shared 'public' tenant + domain  (session scope)
  2. A test tenant + domain              (session scope)
  3. Helper fixtures for creating users, employees, assets, etc.
"""

import uuid
import pytest
from unittest.mock import MagicMock, patch
from django.db import connection
from django.test.utils import override_settings


# ---------------------------------------------------------------------------
# Tenant fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def setup_tenants(django_db_setup, django_db_blocker):
    """Create public and test tenant schemas once per test session."""
    with django_db_blocker.unblock():
        from apps.tenants.models import Organization, Domain

        # Public tenant (schema_name='public')
        public, _ = Organization.objects.get_or_create(
            schema_name="public",
            defaults={"name": "Public Tenant"},
        )
        Domain.objects.get_or_create(
            domain="localhost",
            tenant=public,
            defaults={"is_primary": True},
        )

        # Test tenant
        test_tenant, created = Organization.objects.get_or_create(
            schema_name="test_org",
            defaults={
                "name": "Test Organization",
                "contact_email": "admin@testorg.local",
                "is_active": True,
            },
        )
        if created:
            test_tenant.create_schema(check_if_exists=True)

        Domain.objects.get_or_create(
            domain="test.localhost",
            tenant=test_tenant,
            defaults={"is_primary": True},
        )

        return public, test_tenant


@pytest.fixture()
def tenant(setup_tenants, db):
    """Activate the test tenant schema for the current test."""
    _, test_tenant = setup_tenants
    connection.set_tenant(test_tenant)
    yield test_tenant
    connection.set_schema_to_public()


@pytest.fixture()
def public_tenant(setup_tenants, db):
    """Activate the public schema for the current test."""
    public, _ = setup_tenants
    connection.set_tenant(public)
    yield public
    connection.set_schema_to_public()


# ---------------------------------------------------------------------------
# User & Employee fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tenant_user_factory(tenant):
    """Factory function to create TenantUser instances."""
    from apps.employees.models import TenantUser

    def _create(email=None, role="EMPLOYEE", is_active=True, password="testpass123"):
        email = email or f"user-{uuid.uuid4().hex[:8]}@test.local"
        user = TenantUser(email=email, role=role, is_active=is_active)
        user.set_password(password)
        user.save()
        return user

    return _create


@pytest.fixture()
def org_admin_user(tenant_user_factory):
    """A TenantUser with ORGANIZATION_ADMIN role."""
    return tenant_user_factory(
        email="orgadmin@test.local", role="ORGANIZATION_ADMIN"
    )


@pytest.fixture()
def hr_user(tenant_user_factory):
    """A TenantUser with HR_MANAGER role."""
    return tenant_user_factory(email="hr@test.local", role="HR_MANAGER")


@pytest.fixture()
def employee_user(tenant_user_factory):
    """A TenantUser with EMPLOYEE role."""
    return tenant_user_factory(email="employee@test.local", role="EMPLOYEE")


@pytest.fixture()
def department_factory(tenant):
    """Factory function to create Department instances."""
    from apps.employees.models import Department

    def _create(name=None, code=None, **kwargs):
        name = name or f"Dept-{uuid.uuid4().hex[:6]}"
        code = code or f"D-{uuid.uuid4().hex[:6].upper()}"
        return Department.objects.create(name=name, code=code, **kwargs)

    return _create


@pytest.fixture()
def department(department_factory):
    """A default department."""
    return department_factory(name="Engineering", code="ENG")


@pytest.fixture()
def employee_factory(tenant):
    """Factory function to create Employee + linked TenantUser."""
    from apps.employees.models import TenantUser, Employee

    def _create(
        email=None,
        first_name="Test",
        last_name="Employee",
        role="EMPLOYEE",
        is_active=True,
        department=None,
        **kwargs,
    ):
        email = email or f"emp-{uuid.uuid4().hex[:8]}@test.local"
        user = kwargs.pop("user", None)
        if not user:
            user = TenantUser(email=email, role=role, is_active=is_active)
            user.set_password("testpass123")
            user.save()
        emp = Employee.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
            department=department,
            **kwargs,
        )
        return emp

    return _create


@pytest.fixture()
def employee(employee_factory, department):
    """A default employee with EMPLOYEE role."""
    return employee_factory(
        first_name="John",
        last_name="Doe",
        department=department,
    )


@pytest.fixture()
def admin_employee(employee_factory, department):
    """An employee with ORGANIZATION_ADMIN role."""
    return employee_factory(
        email="admin-emp@test.local",
        first_name="Admin",
        last_name="User",
        role="ORGANIZATION_ADMIN",
        department=department,
    )


@pytest.fixture()
def hr_employee(employee_factory, department):
    """An employee with HR_MANAGER role."""
    return employee_factory(
        email="hr-emp@test.local",
        first_name="HR",
        last_name="Manager",
        role="HR_MANAGER",
        department=department,
    )


# ---------------------------------------------------------------------------
# Asset fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def category_factory(tenant):
    """Factory function to create AssetCategory instances."""
    from apps.assets.models import AssetCategory

    def _create(name=None, code=None, category_type="HARDWARE", **kwargs):
        name = name or f"Category-{uuid.uuid4().hex[:6]}"
        code = code or f"CAT-{uuid.uuid4().hex[:6].upper()}"
        return AssetCategory.objects.create(
            name=name, code=code, category_type=category_type, **kwargs
        )

    return _create


@pytest.fixture()
def category(category_factory):
    """A default hardware asset category."""
    return category_factory(name="Laptops", code="LAP")


@pytest.fixture()
def asset_factory(tenant):
    """Factory function to create Asset instances."""
    from apps.assets.models import Asset

    def _create(
        name=None,
        category=None,
        status="AVAILABLE",
        condition="NEW",
        **kwargs,
    ):
        from apps.assets.models import AssetCategory

        if category is None:
            category, _ = AssetCategory.objects.get_or_create(
                code="DEFAULT",
                defaults={"name": "Default", "category_type": "HARDWARE"},
            )
        name = name or f"Asset-{uuid.uuid4().hex[:6]}"
        asset_code = kwargs.pop('asset_code', f"AST-{uuid.uuid4().hex[:6].upper()}")
        return Asset.objects.create(asset_code=asset_code, 
                        name=name,
            category=category,
            status=status,
            condition=condition,
            **kwargs,
        )

    return _create


@pytest.fixture()
def asset(asset_factory, category):
    """A default available asset."""
    return asset_factory(name="MacBook Pro", category=category)


# ---------------------------------------------------------------------------
# Allocation fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def allocation_factory(tenant):
    """Factory function to create AssetAllocation instances."""
    from apps.allocations.models import AssetAllocation
    from django.utils import timezone

    def _create(asset=None, employee=None, **kwargs):
        defaults = {
            "allocation_number": f"ALLOC-{uuid.uuid4().hex[:8].upper()}",
            "allocated_at": timezone.now(),
            "status": "ACTIVE",
        }
        defaults.update(kwargs)
        return AssetAllocation.objects.create(
            asset=asset, employee=employee, **defaults
        )

    return _create


# ---------------------------------------------------------------------------
# License fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def license_factory(tenant):
    """Factory function to create SoftwareLicense instances."""
    from apps.licenses.models import SoftwareLicense
    from datetime import date, timedelta

    def _create(name=None, total_seats=10, status="ACTIVE", **kwargs):
        name = name or f"License-{uuid.uuid4().hex[:6]}"
        defaults = {
            "vendor": "TestVendor",
            "license_key": f"KEY-{uuid.uuid4().hex[:12]}",
            "license_type": "SUBSCRIPTION",
            "total_seats": total_seats,
            "purchase_date": date.today(),
            "expiry_date": date.today() + timedelta(days=365),
            "cost": 999.99,
            "status": status,
        }
        defaults.update(kwargs)
        return SoftwareLicense.objects.create(name=name, **defaults)

    return _create


# ---------------------------------------------------------------------------
# Request fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def asset_request_factory(tenant):
    """Factory function to create AssetRequest instances."""
    from apps.requests.models import AssetRequest

    def _create(requested_by=None, category=None, **kwargs):
        defaults = {
            "request_number": f"REQ-{uuid.uuid4().hex[:8].upper()}",
            "reason": "Need for work",
            "priority": "MEDIUM",
            "status": "PENDING",
        }
        defaults.update(kwargs)
        return AssetRequest.objects.create(
            requested_by=requested_by, category=category, **defaults
        )

    return _create


# ---------------------------------------------------------------------------
# Incident fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def incident_factory(tenant):
    """Factory function to create Incident instances."""
    from apps.incidents.models import Incident
    from django.utils import timezone

    def _create(asset=None, reported_by=None, **kwargs):
        if reported_by is None:
            from apps.employees.models import TenantUser
            from apps.employees.models import Employee
            user = TenantUser.objects.create(email=f"reporter-{uuid.uuid4().hex[:8]}@test.local", role="EMPLOYEE")
            reported_by = Employee.objects.create(user=user, first_name="Reporter", employee_code=f"RPT-{uuid.uuid4().hex[:6]}")
            
        defaults = {
            "incident_number": f"INC-{uuid.uuid4().hex[:8].upper()}",
            "title": "Test Incident",
            "description": "Something broke",
            "category": "HARDWARE",
            "priority": "MEDIUM",
            "status": "OPEN",
            "opened_at": timezone.now(),
        }
        defaults.update(kwargs)
        return Incident.objects.create(
            asset=asset, reported_by=reported_by, **defaults
        )

    return _create


# ---------------------------------------------------------------------------
# API client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def api_client():
    """Unauthenticated DRF test client."""
    from rest_framework.test import APIClient
    return APIClient(SERVER_NAME="test.localhost")


@pytest.fixture()
def admin_api_client(org_admin_user):
    """API client authenticated as ORGANIZATION_ADMIN."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient(SERVER_NAME="test.localhost")
    token = RefreshToken.for_user(org_admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


@pytest.fixture()
def hr_api_client(hr_user):
    """API client authenticated as HR_MANAGER."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient(SERVER_NAME="test.localhost")
    token = RefreshToken.for_user(hr_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


@pytest.fixture()
def employee_api_client(employee_user):
    """API client authenticated as EMPLOYEE."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient(SERVER_NAME="test.localhost")
    token = RefreshToken.for_user(employee_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_notification_service():
    """Patch NotificationService to prevent side-effects in unit tests."""
    with patch("apps.notifications.services.NotificationService") as mock:
        yield mock


@pytest.fixture()
def mock_audit_log():
    """Patch log_action to prevent side-effects in unit tests."""
    with patch("apps.audit.services.log_action") as mock:
        yield mock


@pytest.fixture()
def mock_send_invitation_email():
    """Patch send_invitation_email to prevent side-effects in unit tests."""
    with patch("apps.accounts.utils.send_invitation_email") as mock:
        yield mock
