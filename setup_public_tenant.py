import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.tenants.models import Organization, Domain
from apps.accounts.models import User

# Create public tenant
public_tenant, created = Organization.objects.get_or_create(
    schema_name="public",
    defaults={
        "name": "AssetFlow Public",
        "is_active": True,
    }
)

if created:
    print("Created public tenant.")

# Create public domain
domain, domain_created = Domain.objects.get_or_create(
    domain="localhost",
    defaults={
        "tenant": public_tenant,
        "is_primary": True,
    }
)

if domain_created:
    print("Created public domain 'localhost'.")

# Create Superuser
if not User.objects.filter(email="admin@assetflow.local").exists():
    User.objects.create_superuser(
        email="admin@assetflow.local",
        first_name="Super",
        last_name="Admin",
        password="admin"
    )
    print("Created superuser: admin@assetflow.local / admin")

print("Setup complete.")
