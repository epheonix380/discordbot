# Generated by Django 4.1.7 on 2023-03-20 07:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0012_guild_guess_the_hero_alter_guessthehero_hero_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='guild',
            name='guess_the_hero',
            field=models.CharField(blank=True, default=None, max_length=20, null=True),
        ),
    ]