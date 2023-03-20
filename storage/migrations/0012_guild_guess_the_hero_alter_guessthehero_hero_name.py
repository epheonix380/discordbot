# Generated by Django 4.1.7 on 2023-03-20 07:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0011_remove_guessthehero_channel_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='guild',
            name='guess_the_hero',
            field=models.CharField(blank=True, default=None, max_length=18, null=True),
        ),
        migrations.AlterField(
            model_name='guessthehero',
            name='hero_name',
            field=models.CharField(default='', max_length=64),
        ),
    ]