# Generated by Django 4.1.10 on 2023-07-19 16:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('FetchVid', '0008_rename_length_video_duration_delete_videoquality'),
    ]

    operations = [
        migrations.AlterField(
            model_name='video',
            name='duration',
            field=models.CharField(max_length=20),
        ),
    ]
