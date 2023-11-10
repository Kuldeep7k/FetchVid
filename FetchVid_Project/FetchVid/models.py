from django.db import models

class Video(models.Model):
    title = models.CharField(max_length=200)
    url = models.URLField()
    video_id = models.CharField(max_length=100, unique=True)
    channel_title = models.CharField(max_length=100)
    duration = models.CharField(max_length=20)
    thumbnail_url = models.URLField()
    views = models.PositiveIntegerField(default=0)
    download_count = models.IntegerField(default=0)  
