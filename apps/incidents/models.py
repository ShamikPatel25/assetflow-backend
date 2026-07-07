from django.db import models

from apps.base.models import AbstractBaseModel


class Incident(AbstractBaseModel):
    """Incident ticket for asset-related issues."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    class Category(models.TextChoices):
        HARDWARE = "HARDWARE", "Hardware"
        SOFTWARE = "SOFTWARE", "Software"
        NETWORK = "NETWORK", "Network"
        PHYSICAL_DAMAGE = "PHYSICAL_DAMAGE", "Physical Damage"
        PERFORMANCE = "PERFORMANCE", "Performance"
        OTHER = "OTHER", "Other"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    incident_number = models.CharField(max_length=50, unique=True)
    asset = models.ForeignKey(
        "assets.Asset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incidents",
    )
    reported_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="reported_incidents",
    )
    assigned_to = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_incidents",
    )
    title = models.CharField(max_length=300)
    description = models.TextField()
    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.OTHER,
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )


    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["incident_number"], name="idx_inc_number"),
            models.Index(fields=["asset"], name="idx_inc_asset"),
            models.Index(fields=["reported_by"], name="idx_inc_reporter"),
            models.Index(fields=["assigned_to"], name="idx_inc_assignee"),
            models.Index(fields=["category"], name="idx_inc_category"),
            models.Index(fields=["priority"], name="idx_inc_priority"),
            models.Index(fields=["status"], name="idx_inc_status"),
            models.Index(fields=["status", "opened_at"], name="idx_inc_status_opened"),
        ]

    def __str__(self):
        return f"{self.incident_number} - {self.title}"


class RepairRecord(AbstractBaseModel):
    """Repair activity linked to an incident."""

    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="repairs",
    )
    asset = models.ForeignKey(
        "assets.Asset",
        on_delete=models.PROTECT,
        related_name="repairs",
    )
    vendor_name = models.CharField(max_length=200, null=True, blank=True)
    repair_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default="INR")
    repair_start_date = models.DateField(null=True, blank=True)
    repair_end_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["incident"], name="idx_repair_incident"),
            models.Index(fields=["asset"], name="idx_repair_asset"),
        ]

    def __str__(self):
        return f"Repair for {self.asset} - {self.incident.incident_number}"
