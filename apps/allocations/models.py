from django.db import models

from apps.base.models import AbstractBaseModel


class AssetAllocation(AbstractBaseModel):
    """
    Tracks asset ownership. This is the source of truth for who owns what.
    Asset.current_owner is only a denormalized shortcut.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        RETURNED = "RETURNED", "Returned"
        CANCELLED = "CANCELLED", "Cancelled"

    allocation_number = models.CharField(max_length=50, unique=True)
    asset = models.ForeignKey(
        "assets.Asset",
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    assigned_by = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_allocations",
    )
    allocated_at = models.DateTimeField()
    expected_return_date = models.DateField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    return_condition = models.CharField(max_length=50, null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        ordering = ["-allocated_at"]
        indexes = [
            models.Index(fields=["allocation_number"], name="idx_alloc_number"),
            models.Index(fields=["asset"], name="idx_alloc_asset"),
            models.Index(fields=["employee"], name="idx_alloc_employee"),
            models.Index(fields=["status"], name="idx_alloc_status"),
            models.Index(fields=["allocated_at"], name="idx_alloc_date"),
            models.Index(fields=["asset", "status"], name="idx_alloc_asset_status"),
            models.Index(fields=["employee", "status"], name="idx_alloc_emp_status"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["asset"],
                condition=models.Q(status="ACTIVE", is_deleted=False),
                name="uniq_one_active_allocation_per_asset",
            ),
        ]

    def __str__(self):
        return self.allocation_number
