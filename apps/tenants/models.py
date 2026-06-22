import uuid

from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Organization(TenantMixin):
    """
    Each row here creates a separate PostgreSQL schema.
    Lives in the public schema only.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    contact_email = models.EmailField(null=True, blank=True)
    contact_phone = models.CharField(max_length=20, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # django-tenants auto-creates schema using schema_name
    auto_create_schema = True

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active"], name="idx_org_is_active"),
        ]

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    """
    Maps domains/subdomains to an Organization.
    e.g. acme.assetflow.com -> tenant_acme schema
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["domain"], name="idx_domain_domain"),
            models.Index(fields=["tenant", "is_primary"], name="idx_domain_tenant_primary"),
        ]

    def __str__(self):
        return self.domain