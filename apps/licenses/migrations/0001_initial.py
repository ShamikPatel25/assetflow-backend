
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('assets', '0001_initial'),
        ('employees', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SoftwareLicense',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('name', models.CharField(max_length=200)),
                ('vendor', models.CharField(blank=True, max_length=200, null=True)),
                ('license_key', models.TextField(blank=True, null=True)),
                ('license_type', models.CharField(choices=[('PERPETUAL', 'Perpetual'), ('SUBSCRIPTION', 'Subscription'), ('OEM', 'OEM'), ('OPEN_SOURCE', 'Open Source')], default='SUBSCRIPTION', max_length=20)),
                ('total_seats', models.PositiveIntegerField(default=1)),
                ('purchase_date', models.DateField(blank=True, null=True)),
                ('expiry_date', models.DateField(blank=True, null=True)),
                ('cost', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('currency', models.CharField(default='INR', max_length=10)),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('EXPIRED', 'Expired'), ('CANCELLED', 'Cancelled')], default='ACTIVE', max_length=20)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LicenseAssignment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('REVOKED', 'Revoked'), ('EXPIRED', 'Expired')], default='ACTIVE', max_length=20)),
                ('asset', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='license_assignments', to='assets.asset')),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_licenses', to='employees.employee')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to=settings.AUTH_USER_MODEL)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='license_assignments', to='employees.employee')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to=settings.AUTH_USER_MODEL)),
                ('license', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assignments', to='licenses.softwarelicense')),
            ],
            options={
                'ordering': ['-assigned_at'],
            },
        ),
        migrations.AddIndex(
            model_name='softwarelicense',
            index=models.Index(fields=['name'], name='idx_license_name'),
        ),
        migrations.AddIndex(
            model_name='softwarelicense',
            index=models.Index(fields=['vendor'], name='idx_license_vendor'),
        ),
        migrations.AddIndex(
            model_name='softwarelicense',
            index=models.Index(fields=['status'], name='idx_license_status'),
        ),
        migrations.AddIndex(
            model_name='softwarelicense',
            index=models.Index(fields=['expiry_date'], name='idx_license_expiry'),
        ),
        migrations.AddIndex(
            model_name='softwarelicense',
            index=models.Index(fields=['status', 'expiry_date'], name='idx_license_status_exp'),
        ),
        migrations.AddIndex(
            model_name='licenseassignment',
            index=models.Index(fields=['license'], name='idx_la_license'),
        ),
        migrations.AddIndex(
            model_name='licenseassignment',
            index=models.Index(fields=['employee'], name='idx_la_employee'),
        ),
        migrations.AddIndex(
            model_name='licenseassignment',
            index=models.Index(fields=['status'], name='idx_la_status'),
        ),
        migrations.AddIndex(
            model_name='licenseassignment',
            index=models.Index(fields=['license', 'status'], name='idx_la_lic_status'),
        ),
        migrations.AddIndex(
            model_name='licenseassignment',
            index=models.Index(fields=['employee', 'status'], name='idx_la_emp_status'),
        ),
        migrations.AddConstraint(
            model_name='licenseassignment',
            constraint=models.UniqueConstraint(condition=models.Q(('is_deleted', False), ('status', 'ACTIVE')), fields=('license', 'employee'), name='uniq_one_active_license_per_employee'),
        ),
    ]
