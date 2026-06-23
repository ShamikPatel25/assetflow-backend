
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0002_alter_department_created_by_and_more'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='department',
            name='idx_department_parent',
        ),
        migrations.RemoveField(
            model_name='department',
            name='parent',
        ),
    ]
