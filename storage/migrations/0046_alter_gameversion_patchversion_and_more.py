# Generated by Django 4.2.9 on 2024-10-11 03:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0045_alter_member_lastgymcheckindate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gameversion',
            name='patchVersion',
            field=models.CharField(default='', max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name='gameversion',
            name='version',
            field=models.CharField(default='', max_length=64, null=True),
        ),
    ]
