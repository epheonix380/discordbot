# Generated by Django 4.2.1 on 2023-06-04 05:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0025_guildactivity_image_count_guildactivity_nsfw_count_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='memberguildactivity',
            name='date',
            field=models.DateField(auto_now=True),
        ),
    ]
