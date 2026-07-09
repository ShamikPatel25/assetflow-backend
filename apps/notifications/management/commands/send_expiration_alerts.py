import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import get_tenant_model, tenant_context

from apps.assets.models import Asset
from apps.licenses.models import SoftwareLicense
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService


class Command(BaseCommand):
    help = "Send notifications for expiring/expired warranties and licenses across all tenants."

    # ---------------------------------------------------------------
    # Asset Warranty — 30 days + 7 days ONLY. No expired alert.
    # Reason: hardware still works after warranty expires. Expired
    # alert is noise. Manager only needs advance warning to decide.
    # Deduplication ON for both windows (no repeat same day).
    # ---------------------------------------------------------------
    WARRANTY_ALERT_WINDOWS = [
        ("30_DAYS", 30),
        ("7_DAYS",  7),
    ]

    # ---------------------------------------------------------------
    # Software License — 30 days + 7 days + expired.
    # Reason: license expiry stops software from working daily.
    # 30-day and 7-day windows: deduplication ON (one alert per day).
    # Expired window: deduplication OFF — repeats EVERY DAY until
    # the manager renews the license.
    # ---------------------------------------------------------------
    LICENSE_UPCOMING_WINDOWS = [
        ("30_DAYS", 30),
        ("7_DAYS",  7),
    ]

    def handle(self, *args, **options):
        TenantModel = get_tenant_model()
        today = timezone.now().date()
        tenants = TenantModel.objects.exclude(schema_name="public")

        self.stdout.write(f"Starting expiration checks for {tenants.count()} tenants...")

        for tenant in tenants:
            with tenant_context(tenant):
                self.stdout.write(f"\nProcessing tenant: {tenant.name} ({tenant.schema_name})")

                warranty_count = self._process_warranty_alerts(today)
                license_count  = self._process_license_alerts(today)

                self.stdout.write(
                    f"  -> {warranty_count} warranty alert(s) and "
                    f"{license_count} license alert(s) generated."
                )

        self.stdout.write(self.style.SUCCESS("\nSuccessfully completed expiration checks."))

    # ------------------------------------------------------------------
    # Asset Warranty — 30 days + 7 days, NO expired alert
    # ------------------------------------------------------------------
    def _process_warranty_alerts(self, today):
        """
        Sends warranty alerts only for upcoming expiry (30 days and 7 days).
        - Deduplication ON: skips if already sent today for same asset.
        - No expired alert: hardware still works, expired warning is noise.
        """
        count = 0

        for label, days_ahead in self.WARRANTY_ALERT_WINDOWS:
            target_date = today + datetime.timedelta(days=days_ahead)

            assets = Asset.objects.filter(
                is_active=True,
                is_deleted=False,
                warranty_expiry_date=target_date,
            )

            for asset in assets:
                # Dedup: skip if already notified today for this asset
                if self._already_notified_today(
                    Notification.Type.WARRANTY_EXPIRING, "asset_id", str(asset.id), today
                ):
                    self.stdout.write(
                        f"  [SKIP] {label} warranty alert already sent today "
                        f"for asset: {asset.name}"
                    )
                    continue

                NotificationService.notify_warranty_expiring(asset)
                self.stdout.write(
                    f"  [SENT] {label} warranty expiring alert → asset: {asset.name} "
                    f"(expires {asset.warranty_expiry_date})"
                )
                count += 1

        return count

    # ------------------------------------------------------------------
    # Software License — 30 days + 7 days + expired (daily repeat)
    # ------------------------------------------------------------------
    def _process_license_alerts(self, today):
        """
        Sends license alerts for upcoming expiry (30 days, 7 days) and
        for already-expired licenses.

        Upcoming windows (30d, 7d):
          - Deduplication ON: one notification per day per license.

        Expired window:
          - Deduplication OFF: fires EVERY DAY until license is renewed.
          - Reason: expired license stops software from working — manager
            must be reminded daily until action is taken.
        """
        count = 0

        # --- Upcoming: 30 days and 7 days (dedup ON) ---
        for label, days_ahead in self.LICENSE_UPCOMING_WINDOWS:
            target_date = today + datetime.timedelta(days=days_ahead)

            licenses = SoftwareLicense.objects.filter(
                is_active=True,
                is_deleted=False,
                expiry_date=target_date,
            )

            for license_obj in licenses:
                if self._already_notified_today(
                    Notification.Type.LICENSE_EXPIRING, "license_id", str(license_obj.id), today
                ):
                    self.stdout.write(
                        f"  [SKIP] {label} license alert already sent today "
                        f"for license: {license_obj.name}"
                    )
                    continue

                NotificationService.notify_license_expiring(license_obj)
                self.stdout.write(
                    f"  [SENT] {label} license expiring alert → license: {license_obj.name} "
                    f"(expires {license_obj.expiry_date})"
                )
                count += 1

        # --- Expired: past today (dedup OFF — repeats daily) ---
        expired_licenses = SoftwareLicense.objects.filter(
            is_active=True,
            is_deleted=False,
            expiry_date__isnull=False,
            expiry_date__lt=today,
        )

        for license_obj in expired_licenses:
            # NO deduplication here — intentionally fires every day
            NotificationService.notify_license_expired(license_obj)
            self.stdout.write(
                f"  [SENT] LICENSE EXPIRED alert → license: {license_obj.name} "
                f"(expired {license_obj.expiry_date}) — will repeat daily until renewed"
            )
            count += 1

        return count

    # ------------------------------------------------------------------
    # Deduplication helper (used for upcoming windows only)
    # ------------------------------------------------------------------
    @staticmethod
    def _already_notified_today(notif_type, payload_key, payload_value, today):
        """
        Return True if a notification of the given type for the given
        payload key/value was already created today in the current tenant.
        Prevents duplicate alerts when the command runs multiple times in a day.
        """
        return Notification.objects.filter(
            type=notif_type,
            payload__contains={payload_key: payload_value},
            created_at__date=today,
        ).exists()
