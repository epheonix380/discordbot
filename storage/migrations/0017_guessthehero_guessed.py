# Generated by Django 4.1.7 on 2023-03-20 16:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0016_alter_guild_nsfw_channel'),
    ]

    operations = [
        migrations.AddField(
            model_name='guessthehero',
            name='guessed',
            field=models.BooleanField(default=False),
        ),
    ]