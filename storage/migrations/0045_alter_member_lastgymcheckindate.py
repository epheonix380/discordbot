# Generated by Django 4.2.9 on 2024-10-11 03:55

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0044_gameversion_patchversion_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='member',
            name='lastGymCheckinDate',
            field=models.DateField(default=datetime.date(2024, 10, 10)),
        ),
    ]
