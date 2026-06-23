
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
            name='Department',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('name', models.CharField(max_length=150)),
                ('code', models.CharField(max_length=50, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to=settings.AUTH_USER_MODEL)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='employees.department')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('first_name', models.CharField(max_length=100)),
                ('last_name', models.CharField(blank=True, default='', max_length=100)),
                ('phone', models.CharField(blank=True, max_length=20, null=True)),
                ('employee_code', models.CharField(max_length=50, unique=True)),
                ('designation', models.CharField(blank=True, max_length=100, null=True)),
                ('joining_date', models.DateField(blank=True, null=True)),
                ('exit_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('INACTIVE', 'Inactive'), ('EXITED', 'Exited')], default='ACTIVE', max_length=20)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to=settings.AUTH_USER_MODEL)),
                ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='employees.department')),
                ('manager', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='direct_reports', to='employees.employee')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='department',
            name='manager',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='managed_departments', to='employees.employee'),
        ),
        migrations.CreateModel(
            name='TenantUser',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('role', models.CharField(choices=[('ORGANIZATION_ADMIN', 'Organization Admin'), ('HR_MANAGER', 'HR Manager'), ('EMPLOYEE', 'Employee')], default='EMPLOYEE', max_length=30)),
                ('is_active', models.BooleanField(default=False)),
                ('last_login', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['email'], name='idx_tenant_user_email'), models.Index(fields=['role'], name='idx_tenant_user_role')],
            },
        ),
        migrations.AddField(
            model_name='employee',
            name='user',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='employee_profile', to='employees.tenantuser'),
        ),
        migrations.AddIndex(
            model_name='department',
            index=models.Index(fields=['code'], name='idx_department_code'),
        ),
        migrations.AddIndex(
            model_name='department',
            index=models.Index(fields=['parent'], name='idx_department_parent'),
        ),
        migrations.AddIndex(
            model_name='department',
            index=models.Index(fields=['is_active', 'is_deleted'], name='idx_dept_active_del'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['employee_code'], name='idx_emp_code'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['department'], name='idx_emp_department'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['manager'], name='idx_emp_manager'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['status'], name='idx_emp_status'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['is_active', 'is_deleted'], name='idx_emp_active_del'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['department', 'status'], name='idx_emp_dept_status'),
        ),
    ]
