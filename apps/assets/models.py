from django.db import models

from django.conf import settings
from apps.base.models import AbstractBaseModel


class AssetCategory(AbstractBaseModel):
    """Categorization for assets (e.g. Laptop, Monitor, Software)."""

    class CategoryType(models.TextChoices):
        HARDWARE = "HARDWARE", "Hardware"
        SOFTWARE = "SOFTWARE", "Software"
        LICENSE = "LICENSE", "License"
        ACCESSORY = "ACCESSORY", "Accessory"
        OTHER = "OTHER", "Other"

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True, blank=True)
    category_type = models.CharField(
        max_length=20,
        choices=CategoryType.choices,
        default=CategoryType.OTHER,
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Asset categories"
        indexes = [
            models.Index(fields=["code"], name="idx_asset_cat_code"),
            models.Index(fields=["category_type"], name="idx_asset_cat_type"),
            models.Index(fields=["parent"], name="idx_asset_cat_parent"),
            models.Index(fields=["is_active", "is_deleted"], name="idx_asset_cat_active"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Asset(AbstractBaseModel):
    """Individual asset registered in the organization."""

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        ALLOCATED = "ALLOCATED", "Allocated"
        IN_MAINTENANCE = "IN_MAINTENANCE", "In Maintenance"
        RETIRED = "RETIRED", "Retired"
        LOST = "LOST", "Lost"
        DAMAGED = "DAMAGED", "Damaged"

    class Condition(models.TextChoices):
        NEW = "NEW", "New"
        GOOD = "GOOD", "Good"
        FAIR = "FAIR", "Fair"
        POOR = "POOR", "Poor"
        DAMAGED = "DAMAGED", "Damaged"

    asset_code = models.CharField(max_length=50, unique=True)
    category = models.ForeignKey(
        AssetCategory,
        on_delete=models.PROTECT,
        related_name="assets",
    )
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, null=True, blank=True)
    model = models.CharField(max_length=100, null=True, blank=True)
    serial_number = models.CharField(max_length=100, null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default=settings.DEFAULT_CURRENCY)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    condition = models.CharField(
        max_length=20,
        choices=Condition.choices,
        default=Condition.NEW,
    )
    current_owner = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_assets",
    )
    current_allocation = models.ForeignKey(
        "allocations.AssetAllocation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["asset_code"], name="idx_asset_code"),
            models.Index(fields=["serial_number"], name="idx_asset_serial"),
            models.Index(fields=["category"], name="idx_asset_category"),
            models.Index(fields=["status"], name="idx_asset_status"),
            models.Index(fields=["current_owner"], name="idx_asset_owner"),
            models.Index(fields=["purchase_date"], name="idx_asset_purchase"),
            models.Index(fields=["warranty_expiry_date"], name="idx_asset_warranty"),
            models.Index(fields=["is_active", "is_deleted"], name="idx_asset_active_del"),
            models.Index(fields=["category", "status"], name="idx_asset_cat_status"),
        ]

    def __str__(self):
        return f"{self.name} ({self.asset_code})"
