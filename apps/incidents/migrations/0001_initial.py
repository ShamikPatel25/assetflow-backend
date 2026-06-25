
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
            name='Incident',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('incident_number', models.CharField(max_length=50, unique=True)),
                ('title', models.CharField(max_length=300)),
                ('description', models.TextField()),
                ('category', models.CharField(choices=[('HARDWARE', 'Hardware'), ('SOFTWARE', 'Software'), ('NETWORK', 'Network'), ('PHYSICAL_DAMAGE', 'Physical Damage'), ('PERFORMANCE', 'Performance'), ('OTHER', 'Other')], default='OTHER', max_length=30)),
                ('priority', models.CharField(choices=[('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High'), ('URGENT', 'Urgent')], default='MEDIUM', max_length=10)),
                ('status', models.CharField(choices=[('OPEN', 'Open'), ('IN_PROGRESS', 'In Progress'), ('RESOLVED', 'Resolved'), ('CLOSED', 'Closed')], default='OPEN', max_length=20)),
                ('ai_category', models.CharField(blank=True, max_length=50, null=True)),
                ('ai_summary', models.TextField(blank=True, null=True)),
                ('ai_confidence', models.FloatField(blank=True, null=True)),
                ('ai_model_version', models.CharField(blank=True, max_length=50, null=True)),
                ('opened_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('asset', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='incidents', to='assets.asset')),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_incidents', to='employees.employee')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to=settings.AUTH_USER_MODEL)),
                ('reported_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reported_incidents', to='employees.employee')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='RepairRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('vendor_name', models.CharField(blank=True, max_length=200, null=True)),
                ('repair_cost', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('currency', models.CharField(default='INR', max_length=10)),
                ('repair_start_date', models.DateField(blank=True, null=True)),
                ('repair_end_date', models.DateField(blank=True, null=True)),
                ('remarks', models.TextField(blank=True, null=True)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='repairs', to='assets.asset')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to=settings.AUTH_USER_MODEL)),
                ('incident', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='repairs', to='incidents.incident')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='incident',
            index=models.Index(fields=['incident_number'], name='idx_inc_number'),
        ),
        migrations.AddIndex(
            model_name='incident',
            index=models.Index(fields=['asset'], name='idx_inc_asset'),
        ),
        migrations.AddIndex(
            model_name='incident',
            index=models.Index(fields=['reported_by'], name='idx_inc_reporter'),
        ),
        migrations.AddIndex(
            model_name='incident',
            index=models.Index(fields=['assigned_to'], name='idx_inc_assignee'),
        ),
        migrations.AddIndex(
            model_name='incident',
            index=models.Index(fields=['category'], name='idx_inc_category'),
        ),
        migrations.AddIndex(
            model_name='incident',
            index=models.Index(fields=['priority'], name='idx_inc_priority'),
        ),
        migrations.AddIndex(
            model_name='incident',
            index=models.Index(fields=['status'], name='idx_inc_status'),
        ),
        migrations.AddIndex(
            model_name='incident',
            index=models.Index(fields=['status', 'opened_at'], name='idx_inc_status_opened'),
        ),
        migrations.AddIndex(
            model_name='repairrecord',
            index=models.Index(fields=['incident'], name='idx_repair_incident'),
        ),
        migrations.AddIndex(
            model_name='repairrecord',
            index=models.Index(fields=['asset'], name='idx_repair_asset'),
        ),
    ]
