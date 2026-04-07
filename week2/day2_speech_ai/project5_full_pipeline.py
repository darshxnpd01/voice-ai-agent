"""
Day 2 - Project 5: Full Pipeline — Voice In → AI Brain → Voice Out
====================================================================
1. Records 5 seconds from your microphone
2. Transcribes with Deepgram REST API
3. Sends transcript to OpenAI for a response
4. Generates speech from response with ElevenLabs
5. Plays the audio back

This is your FIRST end-to-end voice AI pipeline!
It will be slow (~5-15 seconds total). Days 3-4 fix that with Pipecat.

How to run:
  python3 project5_full_pipeline.py
"""

import os
import asyncio
import time
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv

import httpx
import sounddevice as sd
import soundfile as sf
import numpy as np
from openai import OpenAI
from elevenlabs import ElevenLabs

load_dotenv(Path(__file__).parent.parent.parent / ".env")

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID       = "21m00Tcm4TlvDq8ikWAM"
SAMPLE_RATE    = 16000
RECORD_SECS    = 5

openai_client     = OpenAI(api_key=OPENAI_API_KEY)
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_KEY)

conversation_history = [
    {
        "role": "system",
        "content": (
            "You are a helpful assistant. Keep answers to 1-3 short sentences "
            "since your response will be spoken aloud."
        ),
    }
]


def record_audio() -> str:
    print(f"\n🎤  Recording {RECORD_SECS} seconds... SPEAK NOW!")
    audio_data = sd.rec(
        int(RECORD_SECS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype=np.int16,
    )
    sd.wait()
    print("   Done recording.")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(tmp.name, audio_data, SAMPLE_RATE)
    return tmp.name


def transcribe(audio_path: str) -> str:
    print("📝  Transcribing with Deepgram...", end="", flush=True)
    t0 = time.time()

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    response = httpx.post(
        "https://api.deepgram.com/v1/listen",
        content=audio_bytes,
        headers={
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "audio/wav",
        },
        params={"model": "nova-2", "punctuate": "true", "smart_format": "true"},
        timeout=30.0,
    )

    elapsed = time.time() - t0
    result = response.json()
    transcript = result["results"]["channels"][0]["alternatives"][0]["transcript"]

    print(f" {elapsed:.2f}s")
    print(f"   You said: \"{transcript}\"")
    return transcript


def get_ai_response(transcript: str) -> str:
    if not transcript.strip():
        return "I'm sorry, I didn't catch that. Could you please repeat?"

    print("🧠  Getting AI response...", end="", flush=True)
    t0 = time.time()

    conversation_history.append({"role": "user", "content": transcript})
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conversation_history,
        temperature=0.7,
        max_tokens=150,
    )
    ai_text = response.choices[0].message.content
    conversation_history.append({"role": "assistant", "content": ai_text})

    print(f" {time.time() - t0:.2f}s")
    print(f"   AI says: \"{ai_text}\"")
    return ai_text


def speak(text: str):
    print("🔊  Generating speech...", end="", flush=True)
    t0 = time.time()

    audio = elevenlabs_client.text_to_speech.stream(
        text=text,
        voice_id=VOICE_ID,
        model_id="eleven_turbo_v2_5",
        voice_settings={"stability": 0.5, "similarity_boost": 0.8},
        output_format="mp3_44100_128",
    )

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    for chunk in audio:
        if chunk:
            tmp.write(chunk)
    tmp.close()

    print(f" {time.time() - t0:.2f}s")
    print("   Playing...")
    subprocess.run(["afplay", tmp.name])
    os.unlink(tmp.name)


def run_turn():
    total_start = time.time()

    audio_path = record_audio()
    transcript  = transcribe(audio_path)
    os.unlink(audio_path)

    if not transcript.strip():
        print("No speech detected. Try again.")
        return

    ai_response = get_ai_response(transcript)
    speak(ai_response)

    print(f"\n  Total end-to-end latency: {time.time() - total_start:.1f}s")
    print("  (This is why Pipecat in Day 3 is such an improvement!)")


if __name__ == "__main__":
    print("=== Full Pipeline: Voice In → AI → Voice Out ===\n")
    print("Speak a question during the 5-second recording window.\n")

    turn = 1
    while True:
        print(f"\n{'='*50}  Turn {turn}")
        print("Get ready — recording starts in 2 seconds...")
        time.sleep(2)
        run_turn()

        cont = input("\nPress Enter to go again, or type 'quit': ").strip()
        if cont.lower() in ("quit", "q"):
            print("Goodbye!")
            break
        turn += 1
