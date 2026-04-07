"""
Day 2 - Project 1: Transcribe an Audio File with Deepgram
===========================================================
Sends an audio file to Deepgram's REST API and prints the transcript.

How to get a test audio file:
  On Mac: Open QuickTime → File → New Audio Recording → Record → Save
  Then run: ffmpeg -i recording.m4a test_audio.wav
  OR just find any MP3/WAV/M4A file on your computer.

How to run:
  python3 project1_transcribe_file.py test_audio.wav
  python3 project1_transcribe_file.py   (will ask for file path)
"""

import os
import sys
import time
import json
import httpx
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


def transcribe_file(audio_path: str):
    path = Path(audio_path)
    if not path.exists():
        print(f"Error: File not found: {audio_path}")
        sys.exit(1)

    # Detect content type from extension
    ext = path.suffix.lower()
    content_types = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }
    content_type = content_types.get(ext, "audio/wav")

    print(f"\nTranscribing: {path.name} ({path.stat().st_size / 1024:.1f} KB)")
    print("Sending to Deepgram...")

    start = time.time()

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    params = {
        "model": "nova-2",
        "language": "en",
        "punctuate": "true",
        "smart_format": "true",
        "utterances": "true",
    }

    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": content_type,
    }

    response = httpx.post(
        DEEPGRAM_URL,
        content=audio_data,
        headers=headers,
        params=params,
        timeout=60.0,
    )

    elapsed = time.time() - start

    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
        sys.exit(1)

    result = response.json()
    transcript = result["results"]["channels"][0]["alternatives"][0]["transcript"]
    confidence = result["results"]["channels"][0]["alternatives"][0]["confidence"]
    words = result["results"]["channels"][0]["alternatives"][0].get("words", [])

    print(f"\n{'='*55}")
    print(f"TRANSCRIPT:")
    print(f"{'='*55}")
    print(transcript if transcript else "(no speech detected)")
    print(f"\nConfidence   : {confidence:.1%}")
    print(f"Processing   : {elapsed:.2f}s")
    print(f"Words found  : {len(words)}")

    if words:
        print(f"\nFirst 5 words with timestamps:")
        for w in words[:5]:
            print(f"  '{w['word']}' at {w['start']:.2f}s — {w['end']:.2f}s")

    # Save transcript to file
    output_path = path.with_suffix(".transcript.txt")
    with open(output_path, "w") as f:
        f.write(transcript)
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    print("=== Deepgram - Project 1: Transcribe Audio File ===\n")

    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
    else:
        audio_file = input("Enter path to audio file (WAV/MP3/M4A): ").strip()

    transcribe_file(audio_file)
