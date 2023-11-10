from django import forms

class VideoForm(forms.Form):
    youtube_link = forms.URLField(max_length=250, label=False)
