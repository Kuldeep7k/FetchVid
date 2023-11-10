import os
import re
import shlex
import subprocess
from django.http import HttpResponse, FileResponse
from django import forms
from django.conf import settings
from django.shortcuts import render, redirect
from pytube import YouTube
from .forms import VideoForm
from .models import Video

# Get the base directory of the Django project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Define the path to the FFmpeg executable
FFmpeg_PATH = os.path.join(BASE_DIR, 'ffmpeg', 'bin', 'ffmpeg.exe')

def seconds_to_hhmmss(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def fetch_video_details(video_id):
    try:
        video = Video.objects.get(video_id=video_id)
    except Video.DoesNotExist:
        youtube_link = f'https://www.youtube.com/watch?v={video_id}'
        try:
            yt = YouTube(youtube_link)
            video = Video(
                title=yt.title,
                url=youtube_link,
                video_id=video_id,
                channel_title=yt.author,
                duration=str(seconds_to_hhmmss(yt.length)),
                thumbnail_url=yt.thumbnail_url,
            )
            video.save()

        except Exception as e:
            print(f"Error fetching video details: {e}")
            return None

    return video


def index(request):
    if request.method == 'POST':
        form = VideoForm(request.POST)
        if form.is_valid():
            youtube_link = form.cleaned_data['youtube_link']
            video_id = get_video_id(youtube_link)
            video = fetch_video_details(video_id)

            if video:
                return redirect('FetchVid:video_detail', video_id=video_id)

    else:
        form = VideoForm()

    return render(request, 'index.html', {'form': form})


class VideoDownloadForm(forms.Form):
    video_quality = forms.CharField(widget=forms.HiddenInput)
    audio_quality = forms.CharField(widget=forms.HiddenInput)


def video_detail(request, video_id):
    # Use the fetched YouTube link
    youtube_link = f'https://www.youtube.com/watch?v={video_id}'
    video = fetch_video_details(video_id)

    # Increment views count if the video is found
    if video:
        video.views += 1
        video.save()

    # Get all available video and audio qualities from pytube
    yt = YouTube(youtube_link)

    # Get all video streams and sort them by resolution in descending order
    video_streams = yt.streams.filter(type="video").order_by('resolution')
    video_streams = list(reversed(video_streams))
    video_qualities = [
        {
            'format': stream.resolution,
            'fps': stream.fps,
            'url': stream.url,
            'mime_type': stream.mime_type,
            'codecs': stream.codecs
        }
        for stream in video_streams
        if (
            2160 >= int(stream.resolution[:-1]) >= 144 and
            any("vp9" in codec for codec in stream.codecs)
        ) or (
            stream.resolution == "2160p" or stream.resolution == "1440p"  # Include 1440p and 2160p resolutions
        )
    ]

    # Get all available audio streams and sort them by audio bitrate in descending order
    audio_streams = yt.streams.filter(type="audio")
    audio_qualities = []
    abr_set = set()  # To keep track of unique abr values

    for stream in audio_streams:
        abr = stream.abr
        if abr not in abr_set:
            abr_set.add(abr)
            audio_qualities.append({'abr': abr, 'audio_codec': stream.audio_codec, 'mime_type': stream.mime_type})

    # Sort audio_qualities in descending order based on abr
    audio_qualities = sorted(audio_qualities, key=lambda x: extract_numeric_bitrate(x['abr']), reverse=True)

    # Prepare video_audio_qualities list containing tuples of (video_quality, audio_quality)
    video_audio_qualities = []
    for video_quality, audio_quality in zip(video_qualities, audio_qualities):
        video_audio_qualities.append((video_quality, audio_quality))

    # If the number of video qualities is greater than audio qualities, add the remaining video qualities separately
    if len(video_qualities) > len(audio_qualities):
        remaining_video_qualities = video_qualities[len(audio_qualities):]
        for video_quality in remaining_video_qualities:
            video_audio_qualities.append((video_quality, None))

    # If the number of audio qualities is greater than video qualities, add the remaining audio qualities separately
    elif len(audio_qualities) > len(video_qualities):
        remaining_audio_qualities = audio_qualities[len(video_qualities):]
        for audio_quality in remaining_audio_qualities:
            video_audio_qualities.append((None, audio_quality))

    # Handle video download form submission
    if request.method == 'POST':
        form = VideoDownloadForm(request.POST)
        if form.is_valid():
            video_quality = form.cleaned_data['video_quality']
            audio_quality = form.cleaned_data['audio_quality']

            # Call the download_video_with_best_audio view with the selected qualities
            return download_video_with_best_audio(request, video_id, video_quality, audio_quality)

    else:
        # If it's a GET request, create an empty form
        form = VideoDownloadForm()

    return render(request, 'video_details.html', {'video': video, 'video_audio_qualities': video_audio_qualities})



def get_video_id(youtube_link):
    video_id = None
    video_id_regex = r"(?:youtu\.be/|watch\?v=|embed/|playlist\?list=)([^&?/\s]+)"

    match = re.search(video_id_regex, youtube_link)

    if match:
        video_id = match.group(1)

    return video_id


class CleanupFileResponse(FileResponse):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cleanup_files = []

    def add_cleanup_file(self, file_path):
        self.cleanup_files.append(file_path)

    def close(self):
        super().close()
        for file_path in self.cleanup_files:
            if os.path.exists(file_path):
                os.remove(file_path)


def extract_numeric_bitrate(abr):
    # Extract numeric part of the bitrate (e.g., '48kbps' -> '48')
    match = re.search(r'\d+', abr)
    return int(match.group()) if match else 0



def download_video_with_best_audio(request, video_id, video_quality, audio_quality):
    video = fetch_video_details(video_id)

    if video:
        youtube_link = f'https://www.youtube.com/watch?v={video.video_id}'
        yt = YouTube(youtube_link)

        # Try to get the video stream with the selected quality
        video_stream = yt.streams.filter(type="video", resolution=video_quality).first()

        # Get all available audio streams
        audio_streams = yt.streams.filter(type="audio")

        # Get the audio stream with the highest bitrate
        best_audio_stream = max(audio_streams, key=lambda stream: extract_numeric_bitrate(stream.abr)) if audio_streams else None

        if video_stream and best_audio_stream:
            # Download video and audio in the same directory with the video ID as the filename
            video_format = video_stream.subtype
            audio_format = best_audio_stream.subtype
            download_dir = settings.MEDIA_ROOT
            video_path = os.path.join(download_dir, f"{video.video_id}.{video_format}")
            audio_path = os.path.join(download_dir, f"{video.video_id}_audio.{audio_format}")
            video_stream.download(output_path=download_dir, filename=f"{video.video_id}.{video_format}")
            best_audio_stream.download(output_path=download_dir, filename=f"{video.video_id}_audio.{audio_format}")

            # Check if video and audio files were downloaded successfully
            if not os.path.exists(video_path):
                return HttpResponse("Error downloading video.", status=500)
            if not os.path.exists(audio_path):
                return HttpResponse("Error downloading audio.", status=500)

            # Convert audio to M4A format if it's in MP4 format
            if audio_format == 'mp4':
                m4a_audio_path = os.path.join(download_dir, f"{video.video_id}_audio.m4a")
                cmd = f'"{FFmpeg_PATH}" -i "{audio_path}" -vn -c:a copy "{m4a_audio_path}"'
                print(f"Converting audio: {cmd}")

                process = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = process.communicate()

                # Check if the ffmpeg command executed successfully
                if process.returncode != 0:
                    print(f"FFmpeg error: {stderr.decode('utf-8')}")
                    return HttpResponse("Error converting audio to M4A.", status=500)

                # Replace the audio path with the M4A file
                audio_path = m4a_audio_path

            # Merge video and audio using ffmpeg, output as MP4
            merged_path = os.path.join(download_dir, f"{video.video_id}_merged.mp4")
            cmd = f'"{FFmpeg_PATH}" -i "{video_path}" -i "{audio_path}" -c:v copy -c:a copy "{merged_path}"'
            print(f"Merging video and audio: {cmd}")

            process = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            # Check if the ffmpeg command executed successfully
            if process.returncode != 0:
                print(f"FFmpeg error: {stderr.decode('utf-8')}")
                return HttpResponse("Error merging video and audio.", status=500)

            # Check if the merged file exists
            if not os.path.exists(merged_path):
                return HttpResponse("Error creating merged video.", status=500)

            # Serve the merged MP4 file for download with video resolution in the filename
            response = CleanupFileResponse(open(merged_path, 'rb'), content_type='video/mp4')
            response['Content-Disposition'] = f'attachment; filename="{video.title} ({video_quality})_({audio_quality}).mp4"'

            # Add merged_path to the cleanup_files list in the response
            response.add_cleanup_file(video_path)
            response.add_cleanup_file(audio_path)
            response.add_cleanup_file(merged_path)

            # Remove the original audio .mp4 file
            if audio_format == 'mp4':
                os.remove(audio_path)

            return response

    return redirect('FetchVid:video_detail', video_id=video_id)



def merge_video_audio(request, video_id):
    if request.method == 'POST':
        video_quality = request.POST.get('video_quality')
        audio_quality = request.POST.get('audio_quality')

        video = fetch_video_details(video_id)
        if video and video.video_id:
            youtube_link = f'https://www.youtube.com/watch?v={video.video_id}'
            yt = YouTube(youtube_link)

            # Try to get the video stream with 60fps
            video_stream = yt.streams.filter(type="video", resolution=video_quality, fps=60).first()

            # If 60fps stream is not available, fallback to 30fps stream
            if not video_stream:
                video_stream = yt.streams.filter(type="video", resolution=video_quality, fps=30).first()

            # Get all available audio streams and choose the one with the desired quality
            audio_streams = yt.streams.filter(type="audio")
            audio_stream = None
            for stream in audio_streams:
                if stream.abr == audio_quality:
                    audio_stream = stream
                    break

            if video_stream and audio_stream:
                # Download video and audio in the same directory with the video ID as the filename
                video_format = video_stream.subtype
                audio_format = audio_stream.subtype
                download_dir = settings.MEDIA_ROOT
                video_path = os.path.join(download_dir, f"{video.video_id}.{video_format}")
                audio_path = os.path.join(download_dir, f"{video.video_id}_audio.{audio_format}")  # Add "_audio" suffix to the audio filename
                video_stream.download(output_path=download_dir, filename=f"{video.video_id}.{video_format}")
                audio_stream.download(output_path=download_dir, filename=f"{video.video_id}_audio.{audio_format}")

                # Check if video and audio files were downloaded successfully
                if not os.path.exists(video_path):
                    return HttpResponse("Error downloading video.", status=500)
                if not os.path.exists(audio_path):
                    return HttpResponse("Error downloading audio.", status=500)

                # Convert audio to M4A format if it's in MP4 format
                if audio_format == 'mp4':
                    m4a_audio_path = os.path.join(download_dir, f"{video.video_id}_audio.m4a")
                    cmd = f'"{FFmpeg_PATH}" -i "{audio_path}" -vn -c:a copy "{m4a_audio_path}"'
                    print(f"Converting audio: {cmd}")

                    process = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate()

                    # Check if the ffmpeg command executed successfully
                    if process.returncode != 0:
                        print(f"FFmpeg error: {stderr.decode('utf-8')}")
                        return HttpResponse("Error converting audio to M4A.", status=500)

                    # Replace the audio path with the M4A file
                    audio_path = m4a_audio_path

                # Merge video and audio using ffmpeg, output as MP4
                merged_path = os.path.join(download_dir, f"{video.video_id}_merged.mp4")
                cmd = f'"{FFmpeg_PATH}" -i "{video_path}" -i "{audio_path}" -c:v copy -c:a copy "{merged_path}"'
                print(f"Merging video and audio: {cmd}")

                process = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = process.communicate()

                # Check if the ffmpeg command executed successfully
                if process.returncode != 0:
                    print(f"FFmpeg error: {stderr.decode('utf-8')}")
                    return HttpResponse("Error merging video and audio.", status=500)

                # Check if the merged file exists
                if not os.path.exists(merged_path):
                    return HttpResponse("Error creating merged video.", status=500)

                # Serve the merged MP4 file for download
                response = CleanupFileResponse(open(merged_path, 'rb'), content_type='video/mp4')
                response['Content-Disposition'] = f'attachment; filename="{video.title} ({video_quality})_({audio_quality}).mp4"'

                # Add merged_path to the cleanup_files list in the response
                response.add_cleanup_file(video_path)
                response.add_cleanup_file(audio_path)
                response.add_cleanup_file(merged_path)

                # Remove the original audio .mp4 file
                if audio_format == 'mp4':
                    os.remove(audio_path)

                return response

    return redirect('FetchVid:video_detail', video_id=video_id)


def terms_of_use(request):
    return render(request, './terms-of-use.html')

def privacy_policy(request):
    return render(request, './privacy-policy.html')

def copyright_information(request):
    return render(request, './copyright-information.html')