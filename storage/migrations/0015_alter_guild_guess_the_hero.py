# Generated by Django 4.1.7 on 2023-03-20 07:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0014_alter_guild_guess_the_hero'),
    ]

    operations = [
        migrations.AlterField(
            model_name='guild',
            name='guess_the_hero',
            field=models.CharField(blank=True, default=None, max_length=24, null=True),
        ),
    ]