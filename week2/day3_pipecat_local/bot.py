"""
Day 3 - Pipecat Local Voice Bot
================================
Real-time voice AI bot using your microphone and speakers.
Pipeline: Mic → MicGate → VAD → Deepgram STT → OpenAI LLM → OpenAI TTS → Speaker

MicGate completely silences mic input while the bot is speaking, so the bot
never hears its own voice — no headphones required.

How to run:
  source ~/venv-pipecat/bin/activate
  python bot.py

Press Ctrl+C to stop.
"""

import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.processors.aggregators.llm_response import (
    LLMAssistantResponseAggregator,
    LLMUserResponseAggregator,
)
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMService, OpenAITTSService
from pipecat.transports.local.audio import LocalAudioTransport
from pipecat.transports.base_transport import TransportParams
from pipecat.vad.silero import SileroVADAnalyzer
from pipecat.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    LLMMessagesFrame, TranscriptionFrame, Frame,
    LLMFullResponseStartFrame, TTSStoppedFrame,
    AudioRawFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

load_dotenv(Path(__file__).parent.parent.parent / ".env")

SYSTEM_PROMPT = """You are a helpful assistant for Mario's Italian Kitchen.
Keep responses under 2 sentences."""

# How long after TTS stops before mic opens again (seconds).
# Increase this if echo still leaks through on loud speakers.
_REOPEN_DELAY: float = 1.5


class MicGate(FrameProcessor):
    """
    Sits between transport.input() and STT.
    Blocks ALL audio frames while the bot is speaking so STT never
    hears the bot's own voice through the mic.
    """
    def __init__(self, state: dict):
        super().__init__()
        self._state = state

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if self._state.get("bot_speaking"):
            # Drop raw audio and VAD events — mic is closed
            if isinstance(frame, (AudioRawFrame,
                                  UserStartedSpeakingFrame,
                                  UserStoppedSpeakingFrame)):
                return
        await self.push_frame(frame, direction)


class BotSpeakingTracker(FrameProcessor):
    """
    Sits after LLM (before TTS).
    Sets bot_speaking=True when LLM starts, schedules bot_speaking=False
    after TTS finishes + a short delay.
    """
    def __init__(self, state: dict):
        super().__init__()
        self._state = state
        self._reopen_task = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, LLMFullResponseStartFrame):
            # Cancel any pending reopen — bot is speaking again
            if self._reopen_task and not self._reopen_task.done():
                self._reopen_task.cancel()
            self._state["bot_speaking"] = True
            print("[MIC] Bot speaking — mic CLOSED")

        elif isinstance(frame, TTSStoppedFrame):
            # Schedule mic reopen after delay
            self._reopen_task = asyncio.create_task(self._reopen_mic())

        await self.push_frame(frame, direction)

    async def _reopen_mic(self):
        await asyncio.sleep(_REOPEN_DELAY)
        self._state["bot_speaking"] = False
        print("[MIC] Cooldown done — mic OPEN")


class EchoFilter(FrameProcessor):
    """
    Backup filter: drops any stray transcript that slips through
    while bot_speaking is still True (race condition edge case).
    Also drops single-word noise transcripts.
    """
    def __init__(self, state: dict):
        super().__init__()
        self._state = state

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            if self._state.get("bot_speaking"):
                print(f"[FILTER] Dropped echo: '{text}'")
                return
            if len(text.split()) < 2:
                print(f"[FILTER] Dropped noise: '{text}'")
                return
            print(f"\n>>> YOU SAID: '{text}'\n")
        await self.push_frame(frame, direction)


async def run_bot():
    transport = LocalAudioTransport(
        TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_audio_passthrough=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.8)),
        )
    )

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini",
    )

    tts = OpenAITTSService(
        api_key=os.getenv("OPENAI_API_KEY"),
        voice="nova",
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    context = OpenAILLMContext(messages)
    user_aggregator      = LLMUserResponseAggregator(messages)
    assistant_aggregator = LLMAssistantResponseAggregator(messages)

    shared_state    = {"bot_speaking": False}
    mic_gate        = MicGate(shared_state)
    speaking_tracker = BotSpeakingTracker(shared_state)
    echo_filter     = EchoFilter(shared_state)

    pipeline = Pipeline([
        transport.input(),
        mic_gate,           # ← closes mic while bot speaks (before STT)
        stt,
        echo_filter,        # ← backup: drops any stray echo transcripts
        user_aggregator,
        llm,
        speaking_tracker,   # ← opens/closes mic flag around TTS
        tts,
        transport.output(),
        assistant_aggregator,
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=False),
    )

    await task.queue_frames([
        LLMMessagesFrame(messages + [{"role": "user", "content": "Greet me warmly. One sentence only."}])
    ])

    print("\n" + "="*55)
    print("  Pipecat Voice Bot — No headphones needed")
    print("  Mic is auto-muted while bot speaks.")
    print("  Speak into your microphone.")
    print("  Press Ctrl+C to quit.")
    print("="*55 + "\n")

    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, AttributeError):
        pass
