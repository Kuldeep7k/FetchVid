# Generated by Django 4.1.10 on 2023-07-19 19:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('FetchVid', '0009_alter_video_duration'),
    ]

    operations = [
        migrations.AddField(
            model_name='video',
            name='m4a',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='video',
            name='mp4',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='video',
            name='webm',
            field=models.URLField(blank=True),
        ),
    ]
