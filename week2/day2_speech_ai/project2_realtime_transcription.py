"""
Day 2 - Project 2: Real-Time Transcription with Deepgram
=========================================================
Opens your microphone and streams audio to Deepgram via WebSocket.
Words appear on screen as you speak — live transcription!

Requirements (install if missing):
  pip3 install sounddevice numpy websockets

On Mac you may also need:
  brew install portaudio

How to run:
  python3 project2_realtime_transcription.py
  Press Ctrl+C to stop.
"""

import os
import asyncio
import json
import time
from pathlib import Path
from dotenv import load_dotenv

import sounddevice as sd
import numpy as np
from websockets.legacy.client import connect as ws_connect

load_dotenv(Path(__file__).parent.parent.parent / ".env")

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

SAMPLE_RATE = 16000
CHANNELS    = 1
CHUNK_SIZE  = 1024   # samples per chunk sent to Deepgram


async def transcribe_mic():
    url = (
        f"wss://api.deepgram.com/v1/listen"
        f"?model=nova-2"
        f"&language=en-US"
        f"&smart_format=true"
        f"&punctuate=true"
        f"&interim_results=true"
        f"&encoding=linear16"
        f"&sample_rate={SAMPLE_RATE}"
        f"&channels={CHANNELS}"
        f"&endpointing=300"
    )

    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    print(f"Connecting to Deepgram...")

    async with ws_connect(url, extra_headers=headers) as ws:
        print("Connected! Speak into your microphone.\n")
        print("(Words appear as you speak. Ctrl+C to stop.)\n")
        print("─" * 50)

        audio_queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        # Mic callback — runs in a separate thread, puts audio into queue
        def mic_callback(indata, frames, time_info, status):
            pcm_bytes = (indata[:, 0] * 32767).astype(np.int16).tobytes()
            asyncio.run_coroutine_threadsafe(audio_queue.put(pcm_bytes), loop)

        # Task 1: send mic audio to Deepgram
        async def send_audio():
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=CHUNK_SIZE,
                callback=mic_callback,
            ):
                while True:
                    chunk = await audio_queue.get()
                    await ws.send(chunk)

        # Task 2: receive transcripts from Deepgram and print them
        async def receive_transcripts():
            is_finals = []
            async for message in ws:
                data = json.loads(message)
                msg_type = data.get("type", "")

                if msg_type == "Results":
                    alt = data["channel"]["alternatives"][0]
                    text = alt.get("transcript", "")
                    is_final = data.get("is_final", False)

                    if not text:
                        continue

                    if is_final:
                        is_finals.append(text)
                        print(f"\r[FINAL] {text:<70}")
                    else:
                        print(f"\r[  ...] {text:<70}", end="", flush=True)

                elif msg_type == "UtteranceEnd":
                    if is_finals:
                        complete = " ".join(is_finals)
                        print(f"\n{'─'*50}")
                        print(f"You said: {complete}")
                        print(f"{'─'*50}")
                        is_finals = []

                elif msg_type == "Error":
                    print(f"\nDeepgram error: {data}")

        # Run both tasks together
        await asyncio.gather(send_audio(), receive_transcripts())


if __name__ == "__main__":
    print("=== Deepgram - Project 2: Real-Time Transcription ===\n")
    try:
        asyncio.run(transcribe_mic())
    except KeyboardInterrupt:
        print("\n\nStopped. Goodbye!")
