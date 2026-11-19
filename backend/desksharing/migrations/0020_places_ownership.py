# Departments on rooms and places, campus-wide floors and equipment (schema, additive).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0069_category_constraint_names'),
        ('desksharing', '0019_release_request_wanted'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeskAdminSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('place_name_pattern', models.CharField(choices=[('letter', 'Room + letter'), ('number', 'Room + number')], default='letter', max_length=10)),
            ],
            options={
                'verbose_name': 'desksharing admin setting',
            },
        ),
        migrations.CreateModel(
            name='FeatureImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='desk-features/')),
                ('position', models.PositiveIntegerField(db_index=True, default=0)),
            ],
            options={
                'ordering': ['position', 'id'],
            },
        ),
        migrations.AddField(
            model_name='feature',
            name='description',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='feature',
            name='description_de',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='feature',
            name='description_en',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='place',
            name='pool',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='desk_places', to='catalog.resourcepool'),
        ),
        migrations.AddField(
            model_name='place',
            name='pool_overridden',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='reservation',
            name='pool',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='desk_reservations', to='catalog.resourcepool'),
        ),
        migrations.AddField(
            model_name='room',
            name='pool',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='desk_rooms', to='catalog.resourcepool'),
        ),
        migrations.AddField(
            model_name='featureimage',
            name='feature',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='desksharing.feature'),
        ),
    ]
