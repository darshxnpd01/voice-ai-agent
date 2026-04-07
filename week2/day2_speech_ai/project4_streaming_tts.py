"""
Day 2 - Project 4: Streaming TTS with ElevenLabs
==================================================
How to run:
  python3 project4_streaming_tts.py
  python3 project4_streaming_tts.py --compare
"""

import os
import sys
import time
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from elevenlabs import ElevenLabs

load_dotenv(Path(__file__).parent.parent.parent / ".env")

client   = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


def stream_speech(text: str):
    print(f"\nText: '{text[:80]}...'")
    print("Streaming from ElevenLabs...\n")

    start = time.time()
    first_chunk_time = None
    chunks = []
    total_bytes = 0

    stream = client.text_to_speech.stream(
        text=text, voice_id=VOICE_ID, model_id="eleven_turbo_v2_5",
        output_format="mp3_44100_128",
    )

    for chunk in stream:
        if chunk:
            if first_chunk_time is None:
                first_chunk_time = time.time()
                print(f"First chunk: {first_chunk_time - start:.3f}s  ← voice AI starts HERE")
            chunks.append(chunk)
            total_bytes += len(chunk)
            print(f"\r{len(chunks)} chunks | {total_bytes/1024:.1f} KB", end="", flush=True)

    total = time.time() - start
    ttfa  = (first_chunk_time - start) if first_chunk_time else total
    print(f"\n\nTime-to-first-audio: {ttfa:.3f}s | Total: {total:.3f}s | Size: {total_bytes/1024:.1f} KB")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        for c in chunks:
            f.write(c)
        tmp = f.name

    subprocess.run(["afplay", tmp])
    os.unlink(tmp)


def compare(text: str):
    print("\n=== Streaming vs Regular ===\n")

    print("1. Regular (wait for full file):")
    start = time.time()
    audio = client.text_to_speech.convert(
        text=text, voice_id=VOICE_ID, model_id="eleven_turbo_v2_5",
        output_format="mp3_44100_128",
    )
    reg_chunks = [c for c in audio if c]
    reg_time = time.time() - start
    print(f"   Wait before playback: {reg_time:.3f}s")

    print("\n2. Streaming (first chunk):")
    start = time.time()
    first = None
    all_chunks = []
    for chunk in client.text_to_speech.stream(
        text=text, voice_id=VOICE_ID, model_id="eleven_turbo_v2_5",
        output_format="mp3_44100_128",
    ):
        if chunk:
            if first is None:
                first = time.time()
            all_chunks.append(chunk)
    ttfa = (first - start) if first else 0
    print(f"   Time-to-first-audio: {ttfa:.3f}s  ({reg_time/max(ttfa,0.001):.1f}x faster!)")
    print(f"\n   Streaming starts {reg_time - ttfa:.2f}s earlier.\n")

    print("Playing...")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        for c in all_chunks:
            f.write(c)
        tmp = f.name
    subprocess.run(["afplay", tmp])
    os.unlink(tmp)


if __name__ == "__main__":
    print("=== ElevenLabs - Project 4: Streaming TTS ===\n")
    demo = (
        "Welcome to Mario's Italian Kitchen! I'm your AI assistant. "
        "I can help you make a reservation. What date were you thinking?"
    )
    if "--compare" in sys.argv:
        compare(demo)
    else:
        stream_speech(demo)
        print("\nRun with --compare to see streaming vs regular side by side")
