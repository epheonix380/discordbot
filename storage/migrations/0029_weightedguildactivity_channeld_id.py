# Generated by Django 4.2.1 on 2023-06-16 04:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0028_alter_guildactivity_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='weightedguildactivity',
            name='channeld_id',
            field=models.CharField(default=None, max_length=32, null=True),
        ),
    ]
