
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('actor_email', models.EmailField(blank=True, max_length=254, null=True)),
                ('action', models.CharField(max_length=100)),
                ('module', models.CharField(max_length=50)),
                ('object_type', models.CharField(max_length=100)),
                ('object_id', models.CharField(blank=True, max_length=100, null=True)),
                ('object_repr', models.CharField(blank=True, max_length=300, null=True)),
                ('old_data', models.JSONField(blank=True, null=True)),
                ('new_data', models.JSONField(blank=True, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True, null=True)),
                ('request_id', models.CharField(blank=True, max_length=100, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['actor_user'], name='idx_audit_actor'), models.Index(fields=['action'], name='idx_audit_action'), models.Index(fields=['module'], name='idx_audit_module'), models.Index(fields=['object_type'], name='idx_audit_obj_type'), models.Index(fields=['object_id'], name='idx_audit_obj_id'), models.Index(fields=['created_at'], name='idx_audit_created'), models.Index(fields=['actor_user', 'created_at'], name='idx_audit_user_time'), models.Index(fields=['module', 'created_at'], name='idx_audit_mod_time')],
            },
        ),
    ]
