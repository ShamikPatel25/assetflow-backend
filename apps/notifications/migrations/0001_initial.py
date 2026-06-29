
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('employees', '0004_remove_employee_idx_emp_status_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=300)),
                ('message', models.TextField()),
                ('type', models.CharField(choices=[('ASSET_ALLOCATED', 'Asset Allocated'), ('ASSET_RETURNED', 'Asset Returned'), ('REQUEST_SUBMITTED', 'Request Submitted'), ('REQUEST_APPROVED', 'Request Approved'), ('REQUEST_REJECTED', 'Request Rejected'), ('INCIDENT_REPORTED', 'Incident Reported'), ('INCIDENT_UPDATED', 'Incident Updated'), ('LICENSE_EXPIRING', 'License Expiring'), ('WARRANTY_EXPIRING', 'Warranty Expiring'), ('GENERAL', 'General')], default='GENERAL', max_length=30)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('is_read', models.BooleanField(default=False)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='employees.tenantuser')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['recipient'], name='idx_notif_recipient'), models.Index(fields=['type'], name='idx_notif_type'), models.Index(fields=['is_read'], name='idx_notif_is_read'), models.Index(fields=['recipient', 'is_read'], name='idx_notif_recip_read'), models.Index(fields=['recipient', 'created_at'], name='idx_notif_recip_date')],
            },
        ),
    ]
