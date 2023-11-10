from django.urls import path
from . import views

app_name = 'FetchVid'

urlpatterns = [
    path('', views.index, name='index'),
    path('info/terms_of_use/', views.terms_of_use, name='terms_of_use'),
    path('info/privacy_policy/', views.privacy_policy, name='privacy_policy'),
    path('info/copyright_information/', views.copyright_information, name='copyright_information'),
    path('video/<str:video_id>/', views.video_detail, name='video_detail'),
    path('video/<str:video_id>/downloading/', views.merge_video_audio, name='merge_video_audio'),
    path('video/<str:video_id>/download/<str:video_quality>/', views.download_video_with_best_audio, name='download_video_with_best_audio'),
]
