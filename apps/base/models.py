import uuid

from django.db import models


class SoftDeleteQuerySet(models.QuerySet):
    """Default queryset that filters out soft-deleted records."""

    def active(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)


class AbstractBaseModel(models.Model):
    """
    Base model for all tenant-level business models.

    Provides UUID primary key, audit tracking (created/updated by),
    soft delete, and is_active toggle out of the box.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "employees.TenantUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created_set",
    )
    updated_by = models.ForeignKey(
        "employees.TenantUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_updated_set",
    )
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    objects = SoftDeleteQuerySet.as_manager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]
