
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AssetAllocation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('allocation_number', models.CharField(max_length=50, unique=True)),
                ('allocated_at', models.DateTimeField()),
                ('expected_return_date', models.DateField(blank=True, null=True)),
                ('returned_at', models.DateTimeField(blank=True, null=True)),
                ('return_condition', models.CharField(blank=True, max_length=50, null=True)),
                ('remarks', models.TextField(blank=True, null=True)),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('RETURNED', 'Returned'), ('CANCELLED', 'Cancelled')], default='ACTIVE', max_length=20)),
            ],
            options={
                'ordering': ['-allocated_at'],
            },
        ),
    ]
