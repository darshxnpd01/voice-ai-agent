"""
Day 3 - Project 4: Measure and Optimize Latency
================================================
Logs precise timestamps at every stage of the pipeline so you can
see exactly where latency comes from.

Measured stages:
  T0 → User stops speaking (VAD end-of-speech)
  T1 → STT transcript received
  T2 → LLM first token arrives
  T3 → First TTS audio chunk plays

How to run:
  source ~/venv-pipecat/bin/activate
  python project4_latency.py

Target: under 1.5 seconds end-to-end (T0 → T3)
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
from pipecat.frames.frames import (
    Frame, TranscriptionFrame, TextFrame,
    UserStoppedSpeakingFrame, AudioRawFrame,
)
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMService
from pipecat.services.openai import OpenAITTSService
from pipecat.transports.local.audio import LocalAudioTransport
from pipecat.transports.base_transport import TransportParams

load_dotenv(Path(__file__).parent.parent.parent / ".env")


class LatencyTracker(FrameProcessor):
    """Tracks and prints latency at each pipeline stage."""

    def __init__(self):
        super().__init__()
        self._t0: float = 0.0   # VAD end-of-speech
        self._t1: float = 0.0   # STT transcript
        self._t2: float = 0.0   # LLM first token
        self._t3: float = 0.0   # First audio out
        self._first_audio = True

    async def process_frame(self, frame: Frame, direction: FrameDirection):

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._t0 = time.time()
            self._first_audio = True
            print(f"\n{'─'*50}")
            print(f"[T0] VAD: user stopped speaking")

        elif isinstance(frame, TranscriptionFrame) and frame.text.strip():
            self._t1 = time.time()
            stt_ms = (self._t1 - self._t0) * 1000 if self._t0 else 0
            print(f"[T1] STT transcript: '{frame.text.strip()}' (+{stt_ms:.0f}ms)")

        elif isinstance(frame, TextFrame) and self._t2 == 0.0 and self._t1 > 0:
            self._t2 = time.time()
            llm_ms = (self._t2 - self._t1) * 1000 if self._t1 else 0
            print(f"[T2] LLM first token (+{llm_ms:.0f}ms from STT)")

        elif isinstance(frame, AudioRawFrame) and self._first_audio and self._t2 > 0:
            self._first_audio = False
            self._t3 = time.time()
            tts_ms  = (self._t3 - self._t2) * 1000
            total_ms = (self._t3 - self._t0) * 1000 if self._t0 else 0
            print(f"[T3] First audio playing (+{tts_ms:.0f}ms TTS)")
            print(f"{'─'*50}")
            print(f"  TOTAL latency T0→T3: {total_ms:.0f}ms  ({'✅ GOOD' if total_ms < 1500 else '⚠️ HIGH'})")
            print(f"{'─'*50}\n")
            # reset for next turn
            self._t0 = self._t1 = self._t2 = 0.0

        await self.push_frame(frame, direction)


async def run_latency_bot():
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

    messages = [{"role": "system", "content": "You are a helpful assistant. Keep responses under 1 sentence."}]
    context = OpenAILLMContext(messages)
    user_aggregator = LLMUserResponseAggregator(messages)
    assistant_aggregator = LLMAssistantResponseAggregator(messages)

    tracker_in  = LatencyTracker()   # measures T0, T1 (before LLM)
    tracker_mid = LatencyTracker()   # measures T2 (LLM first token)
    tracker_out = LatencyTracker()   # measures T3 (first audio)

    pipeline = Pipeline([
        transport.input(),
        stt,
        tracker_in,                       # measure T0, T1 here
        user_aggregator,
        llm,
        tracker_mid,                      # measure T2 here (LLM output)
        tts,
        tracker_out,                      # measure T3 here (audio out)
        transport.output(),
        assistant_aggregator,
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
    )

    print("\n" + "="*60)
    print("  Project 4: Latency Measurement")
    print("  Speak and watch T0→T3 latency breakdown after each turn.")
    print("  Target: under 1500ms total")
    print("  Press Ctrl+C to stop.")
    print("="*60 + "\n")

    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    try:
        asyncio.run(run_latency_bot())
    except (KeyboardInterrupt, AttributeError):
        pass
