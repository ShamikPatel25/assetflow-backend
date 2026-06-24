
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('allocations', '0001_initial'),
        ('assets', '0001_initial'),
        ('employees', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='assetallocation',
            name='asset',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='allocations', to='assets.asset'),
        ),
        migrations.AddField(
            model_name='assetallocation',
            name='assigned_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_allocations', to='employees.employee'),
        ),
        migrations.AddField(
            model_name='assetallocation',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='assetallocation',
            name='employee',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='allocations', to='employees.employee'),
        ),
        migrations.AddField(
            model_name='assetallocation',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name='assetallocation',
            index=models.Index(fields=['allocation_number'], name='idx_alloc_number'),
        ),
        migrations.AddIndex(
            model_name='assetallocation',
            index=models.Index(fields=['asset'], name='idx_alloc_asset'),
        ),
        migrations.AddIndex(
            model_name='assetallocation',
            index=models.Index(fields=['employee'], name='idx_alloc_employee'),
        ),
        migrations.AddIndex(
            model_name='assetallocation',
            index=models.Index(fields=['status'], name='idx_alloc_status'),
        ),
        migrations.AddIndex(
            model_name='assetallocation',
            index=models.Index(fields=['allocated_at'], name='idx_alloc_date'),
        ),
        migrations.AddIndex(
            model_name='assetallocation',
            index=models.Index(fields=['asset', 'status'], name='idx_alloc_asset_status'),
        ),
        migrations.AddIndex(
            model_name='assetallocation',
            index=models.Index(fields=['employee', 'status'], name='idx_alloc_emp_status'),
        ),
        migrations.AddConstraint(
            model_name='assetallocation',
            constraint=models.UniqueConstraint(condition=models.Q(('is_deleted', False), ('status', 'ACTIVE')), fields=('asset',), name='uniq_one_active_allocation_per_asset'),
        ),
    ]
