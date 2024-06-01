# Real Time Audio Streaming in Python

```
ffmpeg -re -i output.mp3 -f wav - | stdbuf -oL websocat -b ws://localhost:5000
```

```
from pytube import YouTube
from pydub import AudioSegment
import os

def download_youtube_audio(url, output_path='output.mp3'):
    # Download the video
    yt = YouTube(url)
    audio_stream = yt.streams.filter(only_audio=True).first()
    download_path = audio_stream.download(filename='temp')

    # Convert the downloaded audio to mp3
    audio = AudioSegment.from_file(download_path)
    audio.export(output_path, format='mp3')

    # Remove the temporary file
    os.remove(download_path)

    print(f"Audio has been successfully downloaded and converted to {output_path}")

# Example usage
download_youtube_audio('https://www.youtube.com/watch?v=MccRk4cYt1U')
```
