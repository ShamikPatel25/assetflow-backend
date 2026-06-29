import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import get_tenant_model, tenant_context

from apps.assets.models import Asset
from apps.licenses.models import License
from apps.notifications.services import NotificationService

class Command(BaseCommand):
    help = "Send notifications for expiring warranties and licenses across all tenants."

    def handle(self, *args, **options):
        TenantModel = get_tenant_model()
        today = timezone.now().date()
        thirty_days_from_now = today + datetime.timedelta(days=30)
        
        # We only want to process actual tenants, not the public schema
        tenants = TenantModel.objects.exclude(schema_name="public")
        
        self.stdout.write(f"Starting expiration checks for {tenants.count()} tenants...")

        for tenant in tenants:
            with tenant_context(tenant):
                self.stdout.write(f"Processing tenant: {tenant.name} ({tenant.schema_name})")
                
                # Check for expiring warranties
                expiring_assets = Asset.objects.filter(
                    is_active=True,
                    is_deleted=False,
                    warranty_expiry_date__isnull=False,
                    warranty_expiry_date__lte=thirty_days_from_now,
                    warranty_expiry_date__gte=today
                )
                
                asset_count = 0
                for asset in expiring_assets:
                    NotificationService.notify_warranty_expiring(asset)
                    asset_count += 1
                
                # Check for expiring licenses
                expiring_licenses = License.objects.filter(
                    is_active=True,
                    is_deleted=False,
                    expiry_date__isnull=False,
                    expiry_date__lte=thirty_days_from_now,
                    expiry_date__gte=today
                )
                
                license_count = 0
                for license_obj in expiring_licenses:
                    NotificationService.notify_license_expiring(license_obj)
                    license_count += 1
                    
                self.stdout.write(f"  -> Generated {asset_count} warranty alerts and {license_count} license alerts.")

        self.stdout.write(self.style.SUCCESS("Successfully completed expiration checks."))
