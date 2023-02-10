# Generated by Django 4.1.6 on 2023-02-10 09:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0002_guildmembermap'),
    ]

    operations = [
        migrations.AlterField(
            model_name='member',
            name='time_zone',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='storage.timezone'),
        ),
    ]
