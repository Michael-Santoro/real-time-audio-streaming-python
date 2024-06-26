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
```
import asyncio
import queue
import re
import sys
import time
import websockets

from google.cloud import speech

# Audio recording parameters
STREAMING_LIMIT = 240000  # 4 minutes
SAMPLE_RATE = 16000
CHUNK_SIZE = int(SAMPLE_RATE / 10)  # 100ms

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"

def get_current_time() -> int:
    """Return Current Time in MS.

    Returns:
        int: Current Time in MS.
    """
    return int(round(time.time() * 1000))

class ResumableWebSocketStream:
    """Opens a WebSocket stream as a generator yielding the audio chunks."""

    def __init__(self, rate: int, chunk_size: int, uri: str) -> None:
        """Creates a resumable WebSocket stream.

        Args:
        rate: The audio file's sampling rate.
        chunk_size: The audio file's chunk size.
        uri: The WebSocket URI to connect to.
        """
        self._rate = rate
        self.chunk_size = chunk_size
        self._num_channels = 1
        self._buff = queue.Queue()
        self.closed = True
        self.start_time = get_current_time()
        self.restart_counter = 0
        self.audio_input = []
        self.last_audio_input = []
        self.result_end_time = 0
        self.is_final_end_time = 0
        self.final_request_end_time = 0
        self.bridging_offset = 0
        self.last_transcript_was_final = False
        self.new_stream = True
        self._uri = uri

    async def _connect(self):
        async with websockets.connect(self._uri) as websocket:
            self.websocket = websocket
            self.closed = False
            await self._receive_audio()

    async def _receive_audio(self):
        try:
            async for message in self.websocket:
                if isinstance(message, bytes):
                    self._buff.put(message)
                else:
                    print("Received non-binary message")
        except websockets.ConnectionClosed:
            print("Connection closed")

    def __enter__(self) -> "ResumableWebSocketStream":
        """Opens the stream."""
        self.closed = False
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self._connect())
        return self

    def __exit__(self, type, value, traceback) -> None:
        """Closes the stream and releases resources."""
        self.closed = True
        self._buff.put(None)
        self.loop.run_until_complete(self.websocket.close())

    def generator(self):
        """Stream Audio from WebSocket to API and to local buffer"""
        while not self.closed:
            data = []

            if self.new_stream and self.last_audio_input:
                chunk_time = STREAMING_LIMIT / len(self.last_audio_input)

                if chunk_time != 0:
                    if self.bridging_offset < 0:
                        self.bridging_offset = 0

                    if self.bridging_offset > self.final_request_end_time:
                        self.bridging_offset = self.final_request_end_time

                    chunks_from_ms = round(
                        (self.final_request_end_time - self.bridging_offset)
                        / chunk_time
                    )

                    self.bridging_offset = round(
                        (len(self.last_audio_input) - chunks_from_ms) * chunk_time
                    )

                    for i in range(chunks_from_ms, len(self.last_audio_input)):
                        data.append(self.last_audio_input[i])

                self.new_stream = False

            chunk = self._buff.get()
            self.audio_input.append(chunk)

            if chunk is None:
                return
            data.append(chunk)

            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                    self.audio_input.append(chunk)
                except queue.Empty:
                    break

            yield b"".join(data)

def listen_print_loop(responses, stream) -> None:
    """Iterates through server responses and prints them."""
    for response in responses:
        if get_current_time() - stream.start_time > STREAMING_LIMIT:
            stream.start_time = get_current_time()
            break

        if not response.results:
            continue

        result = response.results[0]

        if not result.alternatives:
            continue

        transcript = result.alternatives[0].transcript

        result_seconds = 0
        result_micros = 0

        if result.result_end_time.seconds:
            result_seconds = result.result_end_time.seconds

        if result.result_end_time.microseconds:
            result_micros = result.result_end_time.microseconds

        stream.result_end_time = int((result_seconds * 1000) + (result_micros / 1000))

        corrected_time = (
            stream.result_end_time
            - stream.bridging_offset
            + (STREAMING_LIMIT * stream.restart_counter)
        )
        
        if result.is_final:
            sys.stdout.write(GREEN)
            sys.stdout.write("\033[K")
            sys.stdout.write(str(corrected_time) + ": " + transcript + "\n")

            stream.is_final_end_time = stream.result_end_time
            stream.last_transcript_was_final = True

            if re.search(r"\b(exit|quit)\b", transcript, re.I):
                sys.stdout.write(YELLOW)
                sys.stdout.write("Exiting...\n")
                stream.closed = True
                break
        else:
            sys.stdout.write(RED)
            sys.stdout.write("\033[K")
            sys.stdout.write(str(corrected_time) + ": " + transcript + "\r")

            stream.last_transcript_was_final = False

def main() -> None:
    """start bidirectional streaming from WebSocket to speech API"""
    client = speech.SpeechClient()
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SAMPLE_RATE,
        language_code="en-US",
        max_alternatives=1,
    )

    streaming_config = speech.StreamingRecognitionConfig(
        config=config, interim_results=True
    )

    uri = "ws://localhost:5000"
    mic_manager = ResumableWebSocketStream(SAMPLE_RATE, CHUNK_SIZE, uri)
    print(mic_manager.chunk_size)
    sys.stdout.write(YELLOW)
    sys.stdout.write('\nListening, say "Quit" or "Exit" to stop.\n\n')
    sys.stdout.write("End (ms)       Transcript Results/Status\n")
    sys.stdout.write("=====================================================\n")

    with mic_manager as stream:
        while not stream.closed:
            sys.stdout.write(YELLOW)
            sys.stdout.write(
                "\n" + str(STREAMING_LIMIT * stream.restart_counter) + ": NEW REQUEST\n"
            )

            stream.audio_input = []
            audio_generator = stream.generator()

            requests = (
                speech.StreamingRecognizeRequest(audio_content=content)
                for content in audio_generator
            )

            responses = client.streaming_recognize(streaming_config, requests)

            listen_print_loop(responses, stream)

            if stream.result_end_time > 0:
                stream.final_request_end_time = stream.is_final_end_time
            stream.result_end_time = 0
            stream.last_audio_input = []
            stream.last_audio_input = stream.audio_input
            stream.audio_input = []
            stream.restart_counter = stream.restart_counter + 1

            if not stream.last_transcript_was_final:
                sys.stdout.write("\n")
            stream.new_stream = True

if __name__ == "__main__":
    main()

```
