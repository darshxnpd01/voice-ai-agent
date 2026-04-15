"""
Day 3 - Project 3: SmartTurn for Better Turn Detection
=======================================================
Adds turn detection logging to show WHEN the bot decides the user has
finished speaking — comparing simple VAD silence vs semantic turn end.

How to run:
  source ~/venv-pipecat/bin/activate
  python project3_smartturn.py

What to test:
  - Say a sentence with a natural pause mid-way, e.g.:
    "I'd like to make a reservation... for Saturday night."
  - Watch if the bot interrupts at the pause (bad) or waits (good).
  - Longer stop_secs = fewer false triggers but more perceived delay.
"""

import os
import asyncio
import time
from pathlib import Path
from dotenv import load_dotenv

from pipecat.vad.silero import SileroVADAnalyzer
from pipecat.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.aggregators.llm_response import (
    LLMAssistantResponseAggregator,
    LLMUserResponseAggregator,
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import Frame, TranscriptionFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMService
from pipecat.services.openai import OpenAITTSService
from pipecat.transports.local.audio import LocalAudioTransport
from pipecat.transports.base_transport import TransportParams

load_dotenv(Path(__file__).parent.parent.parent / ".env")


class TurnDetectionLogger(FrameProcessor):
    """
    Logs turn detection events so you can observe when VAD decides
    the user has started and stopped speaking.
    """
    def __init__(self):
        super().__init__()
        self._speech_start: float = 0.0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, UserStartedSpeakingFrame):
            self._speech_start = time.time()
            print(f"\n[TURN] User started speaking")

        elif isinstance(frame, UserStoppedSpeakingFrame):
            duration = time.time() - self._speech_start if self._speech_start else 0
            print(f"[TURN] User stopped speaking — speech duration: {duration:.2f}s")
            print(f"[TURN] → Turn handed to LLM now\n")

        elif isinstance(frame, TranscriptionFrame):
            print(f"[TRANSCRIPT] '{frame.text}'")

        await self.push_frame(frame, direction)


async def run_smartturn_bot():
    # stop_secs: how long silence before VAD declares turn over
    # Lower = faster response but more false triggers on pauses
    # Higher = fewer false triggers but more perceived delay
    # 0.8s is a good balance for conversational speech
    transport = LocalAudioTransport(
        TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_audio_passthrough=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.8)),
        )
    )

    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
    )

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini",
    )

    tts = OpenAITTSService(
        api_key=os.getenv("OPENAI_API_KEY"),
        voice="nova",
    )

    messages = [{"role": "system", "content": "You are a helpful assistant. Keep responses under 2 sentences."}]
    context = OpenAILLMContext(messages)
    user_aggregator = LLMUserResponseAggregator(messages)
    assistant_aggregator = LLMAssistantResponseAggregator(messages)

    pipeline = Pipeline([
        transport.input(),
        stt,
        TurnDetectionLogger(),   # <-- logs turn detection events
        user_aggregator,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
    )

    print("\n" + "="*60)
    print("  Project 3: Turn Detection Logger")
    print("  Watch the [TURN] logs as you speak.")
    print("  Try pausing mid-sentence to see if bot waits correctly.")
    print("  VAD stop_secs = 0.8s")
    print("  Press Ctrl+C to stop.")
    print("="*60 + "\n")

    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    try:
        asyncio.run(run_smartturn_bot())
    except (KeyboardInterrupt, AttributeError):
        pass
