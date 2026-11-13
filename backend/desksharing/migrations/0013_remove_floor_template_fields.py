from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('desksharing', '0012_copy_floor_templates'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='floor',
            name='template_content_type',
        ),
        migrations.RemoveField(
            model_name='floor',
            name='template_data',
        ),
    ]
