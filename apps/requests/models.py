from django.db import models

from apps.base.models import AbstractBaseModel


class AssetRequest(AbstractBaseModel):
    """Employee's request for an asset. Goes through approval workflow."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        ALLOCATED = "ALLOCATED", "Allocated"
        CANCELLED = "CANCELLED", "Cancelled"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    request_number = models.CharField(max_length=50, unique=True)
    requested_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="asset_requests",
    )
    category = models.ForeignKey(
        "assets.AssetCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="asset_requests",
    )
    preferred_asset = models.ForeignKey(
        "assets.Asset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="asset_requests",
    )
    reason = models.TextField()
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    approved_by = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_requests",
    )
    rejected_by = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rejected_requests",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    allocation = models.ForeignKey(
        "allocations.AssetAllocation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="asset_request",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["request_number"], name="idx_req_number"),
            models.Index(fields=["requested_by"], name="idx_req_requester"),
            models.Index(fields=["status"], name="idx_req_status"),
            models.Index(fields=["priority"], name="idx_req_priority"),
            models.Index(fields=["requested_by", "status"], name="idx_req_emp_status"),
            models.Index(fields=["status", "created_at"], name="idx_req_status_date"),
        ]

    def __str__(self):
        return self.request_number
