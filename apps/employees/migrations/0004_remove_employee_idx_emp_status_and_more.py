
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0003_remove_department_idx_department_parent_and_more'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='employee',
            name='idx_emp_status',
        ),
        migrations.RemoveIndex(
            model_name='employee',
            name='idx_emp_dept_status',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='status',
        ),
    ]
