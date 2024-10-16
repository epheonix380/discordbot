# Generated by Django 4.2.9 on 2024-02-07 17:56

import datetime
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0040_memberreminder_origin_channel_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ComplexFrequecy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('years', models.IntegerField(default=0)),
                ('months', models.IntegerField(default=0)),
                ('weeks', models.IntegerField(default=0)),
                ('days', models.IntegerField(default=0)),
                ('hours', models.IntegerField(default=0)),
                ('minutes', models.IntegerField(default=0)),
            ],
        ),
        migrations.AlterField(
            model_name='member',
            name='lastGymCheckinDate',
            field=models.DateField(default=datetime.date(2024, 2, 7)),
        ),
        migrations.AlterField(
            model_name='memberreminder',
            name='member',
            field=models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='storage.member'),
        ),
        migrations.AddField(
            model_name='memberreminder',
            name='complexFrequecy',
            field=models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.CASCADE, to='storage.complexfrequecy'),
        ),
    ]
