from django.db import models

from apps.base.models import AbstractBaseModel


class SoftwareLicense(AbstractBaseModel):
    """Tracks software licenses owned by the organization."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"

    class LicenseType(models.TextChoices):
        PERPETUAL = "PERPETUAL", "Perpetual"
        SUBSCRIPTION = "SUBSCRIPTION", "Subscription"
        OEM = "OEM", "OEM"
        OPEN_SOURCE = "OPEN_SOURCE", "Open Source"

    name = models.CharField(max_length=200)
    vendor = models.CharField(max_length=200, null=True, blank=True)
    license_key = models.TextField(null=True, blank=True)
    license_type = models.CharField(
        max_length=20,
        choices=LicenseType.choices,
        default=LicenseType.SUBSCRIPTION,
    )
    total_seats = models.PositiveIntegerField(default=1)
    purchase_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default="INR")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["name"], name="idx_license_name"),
            models.Index(fields=["vendor"], name="idx_license_vendor"),
            models.Index(fields=["status"], name="idx_license_status"),
            models.Index(fields=["expiry_date"], name="idx_license_expiry"),
            models.Index(fields=["status", "expiry_date"], name="idx_license_status_exp"),
        ]

    def __str__(self):
        return f"{self.name} ({self.vendor})"

    @property
    def used_seats(self):
        """Calculate used seats from active assignments."""
        return self.assignments.filter(
            status=LicenseAssignment.Status.ACTIVE,
            is_deleted=False,
        ).count()

    @property
    def available_seats(self):
        return max(0, self.total_seats - self.used_seats)


class LicenseAssignment(AbstractBaseModel):
    """Assignment of a license seat to an employee."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        REVOKED = "REVOKED", "Revoked"
        EXPIRED = "EXPIRED", "Expired"

    license = models.ForeignKey(
        SoftwareLicense,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="license_assignments",
    )
    assigned_by = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_licenses",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        ordering = ["-assigned_at"]
        indexes = [
            models.Index(fields=["license"], name="idx_la_license"),
            models.Index(fields=["employee"], name="idx_la_employee"),
            models.Index(fields=["status"], name="idx_la_status"),
            models.Index(fields=["license", "status"], name="idx_la_lic_status"),
            models.Index(fields=["employee", "status"], name="idx_la_emp_status"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["license", "employee"],
                condition=models.Q(status="ACTIVE", is_deleted=False),
                name="uniq_one_active_license_per_employee",
            ),
        ]

    def __str__(self):
        return f"{self.license.name} -> {self.employee}"
