# Generated by Django 4.1.7 on 2023-03-20 08:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0015_alter_guild_guess_the_hero'),
    ]

    operations = [
        migrations.AlterField(
            model_name='guild',
            name='nsfw_channel',
            field=models.CharField(blank=True, default=None, max_length=24, null=True),
        ),
    ]
