# Generated by Django 4.1.7 on 2023-02-17 08:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('storage', '0007_alter_botignorechannels_channel_id_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ListOfChoices',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_used', models.DateTimeField(auto_now=True)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='storage.member')),
            ],
        ),
        migrations.CreateModel(
            name='Item',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('list', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='storage.listofchoices')),
            ],
        ),
    ]
