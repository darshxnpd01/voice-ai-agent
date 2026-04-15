"""
Day 3 - Project 5: Function Calling in Voice Bot
=================================================
The LLM decides when to call functions based on what you say.
Three functions available:
  - get_current_time()  → called when you ask "what time is it?"
  - tell_joke()         → called when you ask for a joke
  - lookup_order()      → called when you ask about an order (mock data)

How to run:
  source ~/venv-pipecat/bin/activate
  python project5_functions.py

What to say:
  "What time is it?"
  "Tell me a joke"
  "What's the status of order 1234?"
"""

import os
import json
import asyncio
from datetime import datetime
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
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAILLMService
from pipecat.services.openai import OpenAITTSService
from pipecat.transports.local.audio import LocalAudioTransport
from pipecat.transports.base_transport import TransportParams

load_dotenv(Path(__file__).parent.parent.parent / ".env")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tell_joke",
            "description": "Tell the user a short, funny joke.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up the status of a customer order by order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID to look up"},
                },
                "required": ["order_id"],
            },
        },
    },
]

JOKES = [
    "Why don't scientists trust atoms? Because they make up everything!",
    "I told my wife she was drawing her eyebrows too high. She looked surprised.",
    "Why do programmers prefer dark mode? Because light attracts bugs!",
]

MOCK_ORDERS = {
    "1234": {"status": "shipped", "eta": "tomorrow by 5 PM"},
    "5678": {"status": "processing", "eta": "2-3 business days"},
    "9999": {"status": "delivered", "eta": "delivered yesterday"},
}


async def handle_tool_call(function_name: str, args: dict) -> str:
    print(f"\n[FUNCTION] Calling: {function_name}({args})")

    if function_name == "get_current_time":
        now = datetime.now().strftime("%A, %B %d at %I:%M %p")
        return json.dumps({"time": now})

    elif function_name == "tell_joke":
        import random
        joke = random.choice(JOKES)
        return json.dumps({"joke": joke})

    elif function_name == "lookup_order":
        order_id = args.get("order_id", "")
        order = MOCK_ORDERS.get(order_id, {"status": "not found", "eta": "N/A"})
        return json.dumps({"order_id": order_id, **order})

    return json.dumps({"error": "unknown function"})


async def run_function_bot():
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

    messages = [{"role": "system", "content": "You are a helpful voice assistant. Keep responses to 1-2 sentences. Use your tools when appropriate — don't make up time or order data."}]
    context = OpenAILLMContext(messages, tools=TOOLS)
    user_aggregator = LLMUserResponseAggregator(messages)
    assistant_aggregator = LLMAssistantResponseAggregator(messages)

    pipeline = Pipeline([
        transport.input(),
        stt,
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
    print("  Project 5: Function Calling Voice Bot")
    print("  Try saying:")
    print("    'What time is it?'")
    print("    'Tell me a joke'")
    print("    'What is the status of order 1234?'")
    print("  Watch [FUNCTION] logs when LLM calls a function.")
    print("  Press Ctrl+C to stop.")
    print("="*60 + "\n")

    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    try:
        asyncio.run(run_function_bot())
    except (KeyboardInterrupt, AttributeError):
        pass
