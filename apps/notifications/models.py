import uuid

from django.db import models


class Notification(models.Model):
    """In-app notification for tenant users."""

    class Type(models.TextChoices):
        ASSET_ALLOCATED = "ASSET_ALLOCATED", "Asset Allocated"
        ASSET_RETURNED = "ASSET_RETURNED", "Asset Returned"
        REQUEST_SUBMITTED = "REQUEST_SUBMITTED", "Request Submitted"
        REQUEST_APPROVED = "REQUEST_APPROVED", "Request Approved"
        REQUEST_REJECTED = "REQUEST_REJECTED", "Request Rejected"
        INCIDENT_REPORTED = "INCIDENT_REPORTED", "Incident Reported"
        INCIDENT_UPDATED = "INCIDENT_UPDATED", "Incident Updated"
        LICENSE_EXPIRING = "LICENSE_EXPIRING", "License Expiring"
        LICENSE_EXPIRED = "LICENSE_EXPIRED", "License Expired"
        WARRANTY_EXPIRING = "WARRANTY_EXPIRING", "Warranty Expiring"
        WARRANTY_EXPIRED = "WARRANTY_EXPIRED", "Warranty Expired"
        GENERAL = "GENERAL", "General"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        "employees.TenantUser",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=300)
    message = models.TextField()
    type = models.CharField(
        max_length=30,
        choices=Type.choices,
        default=Type.GENERAL,
    )
    payload = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient"], name="idx_notif_recipient"),
            models.Index(fields=["type"], name="idx_notif_type"),
            models.Index(fields=["is_read"], name="idx_notif_is_read"),
            models.Index(fields=["recipient", "is_read"], name="idx_notif_recip_read"),
            models.Index(fields=["recipient", "created_at"], name="idx_notif_recip_date"),
        ]

    def __str__(self):
        return f"{self.title} -> {self.recipient}"
