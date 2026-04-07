"""
Day 1 - Project 2: Streaming Responses
=======================================
What this does:
- Sends a prompt to OpenAI using STREAMING mode
- Prints tokens as they arrive (like ChatGPT does)
- Measures time-to-first-token (TTFT) — critical for voice AI!

Why streaming matters for voice AI:
  With streaming, we can START generating speech the moment
  the first few words arrive, instead of waiting for the full response.
  This reduces perceived latency from ~3s to ~0.5s.

How to run:
  python project2_streaming.py
"""

import os
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent.parent.parent / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def stream_response(prompt: str) -> str:
    print(f"\nPrompt: '{prompt}'")
    print("Response (streaming — watch it appear token by token):")
    print("-" * 50)

    start_time = time.time()
    first_token_time = None
    full_response = ""

    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Keep answers concise."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=400,
        stream=True,
    )

    for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            if first_token_time is None:
                first_token_time = time.time()
            print(token, end="", flush=True)
            full_response += token

    total_time = time.time() - start_time
    ttft = (first_token_time - start_time) if first_token_time else total_time

    print("\n" + "-" * 50)
    print(f"Time-to-first-token (TTFT) : {ttft:.3f}s  ← voice AI starts speaking HERE")
    print(f"Total response time        : {total_time:.3f}s")
    print(f"Tokens generated           : {len(full_response.split())}")

    return full_response


if __name__ == "__main__":
    print("=== OpenAI API - Project 2: Streaming Responses ===\n")
    print("Notice: text appears token-by-token, just like ChatGPT.\n")
    print("The TTFT number tells you when a voice AI could START speaking.\n")

    test_prompts = [
        "Explain what Python is in 3 sentences.",
        "Tell me a very short story about a robot.",
        "What are 5 tips for better sleep?",
    ]

    print("Running with 3 test prompts to compare TTFT...\n")
    for prompt in test_prompts:
        stream_response(prompt)
        print()

    print("\nNow try your own prompt:")
    while True:
        user_input = input("\nEnter a prompt (or 'quit'): ").strip()
        if user_input.lower() in ("quit", "q", "exit"):
            break
        if user_input:
            stream_response(user_input)
