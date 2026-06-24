
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('allocations', '0001_initial'),
        ('employees', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AssetCategory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('name', models.CharField(max_length=150)),
                ('code', models.CharField(max_length=50, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('category_type', models.CharField(choices=[('HARDWARE', 'Hardware'), ('SOFTWARE', 'Software'), ('LICENSE', 'License'), ('ACCESSORY', 'Accessory'), ('OTHER', 'Other')], default='OTHER', max_length=20)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to=settings.AUTH_USER_MODEL)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='assets.assetcategory')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Asset categories',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Asset',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('asset_code', models.CharField(max_length=50, unique=True)),
                ('name', models.CharField(max_length=200)),
                ('brand', models.CharField(blank=True, max_length=100, null=True)),
                ('model', models.CharField(blank=True, max_length=100, null=True)),
                ('serial_number', models.CharField(blank=True, max_length=100, null=True)),
                ('purchase_date', models.DateField(blank=True, null=True)),
                ('warranty_expiry_date', models.DateField(blank=True, null=True)),
                ('purchase_cost', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('currency', models.CharField(default='INR', max_length=10)),
                ('status', models.CharField(choices=[('AVAILABLE', 'Available'), ('ALLOCATED', 'Allocated'), ('IN_MAINTENANCE', 'In Maintenance'), ('RETIRED', 'Retired'), ('LOST', 'Lost'), ('DAMAGED', 'Damaged')], default='AVAILABLE', max_length=20)),
                ('condition', models.CharField(choices=[('NEW', 'New'), ('GOOD', 'Good'), ('FAIR', 'Fair'), ('POOR', 'Poor'), ('DAMAGED', 'Damaged')], default='NEW', max_length=20)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to=settings.AUTH_USER_MODEL)),
                ('current_allocation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='allocations.assetallocation')),
                ('current_owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owned_assets', to='employees.employee')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to=settings.AUTH_USER_MODEL)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assets', to='assets.assetcategory')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='assetcategory',
            index=models.Index(fields=['code'], name='idx_asset_cat_code'),
        ),
        migrations.AddIndex(
            model_name='assetcategory',
            index=models.Index(fields=['category_type'], name='idx_asset_cat_type'),
        ),
        migrations.AddIndex(
            model_name='assetcategory',
            index=models.Index(fields=['parent'], name='idx_asset_cat_parent'),
        ),
        migrations.AddIndex(
            model_name='assetcategory',
            index=models.Index(fields=['is_active', 'is_deleted'], name='idx_asset_cat_active'),
        ),
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(fields=['asset_code'], name='idx_asset_code'),
        ),
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(fields=['serial_number'], name='idx_asset_serial'),
        ),
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(fields=['category'], name='idx_asset_category'),
        ),
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(fields=['status'], name='idx_asset_status'),
        ),
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(fields=['current_owner'], name='idx_asset_owner'),
        ),
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(fields=['purchase_date'], name='idx_asset_purchase'),
        ),
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(fields=['warranty_expiry_date'], name='idx_asset_warranty'),
        ),
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(fields=['is_active', 'is_deleted'], name='idx_asset_active_del'),
        ),
        migrations.AddIndex(
            model_name='asset',
            index=models.Index(fields=['category', 'status'], name='idx_asset_cat_status'),
        ),
    ]
