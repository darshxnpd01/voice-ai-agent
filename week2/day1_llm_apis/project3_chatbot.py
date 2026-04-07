"""
Day 1 - Project 3: CLI Chatbot with Memory
==========================================
What this does:
- Interactive chatbot in your terminal
- REMEMBERS the full conversation (multi-turn memory)
- Uses streaming so responses appear token by token
- Shows token count after each reply (watch it grow!)
- Type 'quit' to exit, 'reset' to start a new conversation

Why this matters:
  This is exactly how ChatGPT works internally — it sends ALL
  previous messages every time. When context fills up, old messages
  get dropped. This is the foundation of every AI chat product.

How to run:
  python project3_chatbot.py
"""

import os
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent.parent.parent / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = "You are a helpful assistant. Keep responses concise and conversational."


def chat(messages: list[dict]) -> tuple[str, int]:
    """Send messages to OpenAI with streaming. Returns (response_text, token_count)."""
    start = time.time()
    first_token_time = None
    full_response = ""

    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=500,
        stream=True,
    )

    print("\nAssistant: ", end="", flush=True)
    for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            if first_token_time is None:
                first_token_time = time.time()
            print(token, end="", flush=True)
            full_response += token

    elapsed = time.time() - start
    ttft = (first_token_time - start) if first_token_time else elapsed

    # Rough token count estimate (actual count needs a non-streaming call)
    # 1 token ≈ 4 characters
    approx_tokens = len("".join(m["content"] for m in messages)) // 4 + len(full_response) // 4

    print(f"\n[TTFT: {ttft:.2f}s | Total: {elapsed:.2f}s | ~{approx_tokens} tokens in context]")
    return full_response, approx_tokens


def run_chatbot():
    print("=" * 55)
    print("  CLI Chatbot — Type 'quit' to exit, 'reset' to restart")
    print("=" * 55)
    print("Watch the token count grow — that's your context window filling up.\n")

    conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    turn = 0

    while True:
        user_input = input("\nYou: ").strip()

        if not user_input:
            continue
        if user_input.lower() in ("quit", "q", "exit"):
            print("Goodbye! Session ended.")
            break
        if user_input.lower() == "reset":
            conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]
            turn = 0
            print("\n[Conversation reset — starting fresh]\n")
            continue

        turn += 1
        conversation_history.append({"role": "user", "content": user_input})

        response_text, token_count = chat(conversation_history)

        conversation_history.append({"role": "assistant", "content": response_text})

        # Warn when approaching context limits
        if token_count > 3000:
            print(f"  ⚠️  Context growing large (~{token_count} tokens). Consider 'reset' soon.")


if __name__ == "__main__":
    run_chatbot()
