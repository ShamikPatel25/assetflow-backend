
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0002_alter_department_created_by_and_more'),
        ('incidents', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='incident',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to='employees.tenantuser'),
        ),
        migrations.AlterField(
            model_name='incident',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to='employees.tenantuser'),
        ),
        migrations.AlterField(
            model_name='repairrecord',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created_set', to='employees.tenantuser'),
        ),
        migrations.AlterField(
            model_name='repairrecord',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated_set', to='employees.tenantuser'),
        ),
    ]
