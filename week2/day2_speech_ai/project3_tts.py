"""
Day 2 - Project 3: Text-to-Speech with ElevenLabs
===================================================
How to run:
  python3 project3_tts.py "Hello from Mario's Kitchen"
  python3 project3_tts.py --list-voices
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from elevenlabs import ElevenLabs

load_dotenv(Path(__file__).parent.parent.parent / ".env")

client   = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"   # Rachel
OUTPUT   = "/tmp/tts_output.mp3"


def generate_speech(text: str, voice_id: str = VOICE_ID) -> str:
    print(f"\nGenerating: '{text[:80]}{'...' if len(text)>80 else ''}'")
    start = time.time()

    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id="eleven_turbo_v2_5",
        voice_settings={"stability": 0.5, "similarity_boost": 0.8},
        output_format="mp3_44100_128",
    )

    with open(OUTPUT, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)

    elapsed = time.time() - start
    size = Path(OUTPUT).stat().st_size / 1024
    print(f"Generated in {elapsed:.2f}s — {size:.1f} KB")
    return OUTPUT


def play(file_path: str):
    print("Playing...")
    subprocess.run(["afplay", file_path], check=True)
    print("Done.")


def list_voices():
    voices = client.voices.get_all().voices
    print("\nAvailable voices:")
    for v in voices[:10]:
        print(f"  {v.name:<20} — {v.voice_id}")


if __name__ == "__main__":
    print("=== ElevenLabs - Project 3: Text-to-Speech ===\n")

    if "--list-voices" in sys.argv:
        list_voices()
        sys.exit(0)

    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        text = " ".join(sys.argv[1:])
    else:
        text = input("Enter text (or Enter for demo): ").strip() or (
            "Hello! I'm your AI voice assistant for Mario's Italian Kitchen. "
            "How can I help you today?"
        )

    play(generate_speech(text))
    print("\nTip: run with --list-voices to try different voices")
