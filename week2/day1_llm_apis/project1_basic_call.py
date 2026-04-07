"""
Day 1 - Project 1: Your First OpenAI API Call
=============================================
What this does:
- Loads your OpenAI API key from .env
- Sends a message to GPT-4o-mini
- Prints the response and how long it took

How to run:
  cd week2/day1_llm_apis
  pip install -r requirements.txt
  python project1_basic_call.py
"""

import os
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load .env from the project root (two folders up)
load_dotenv(Path(__file__).parent.parent.parent / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def make_api_call(prompt: str) -> str:
    print(f"\nSending to OpenAI: '{prompt}'")
    print("-" * 40)

    start = time.time()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Keep answers concise."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=300,
    )

    elapsed = time.time() - start
    answer = response.choices[0].message.content

    print(f"Response:\n{answer}")
    print("-" * 40)
    print(f"Response time : {elapsed:.2f}s")
    print(f"Tokens used   : {response.usage.total_tokens} "
          f"(prompt={response.usage.prompt_tokens}, "
          f"completion={response.usage.completion_tokens})")

    return answer


if __name__ == "__main__":
    print("=== OpenAI API - Project 1: Basic Call ===\n")
    print("Try changing the temperature in the code (0.0 = predictable, 1.5 = creative)\n")

    while True:
        user_input = input("\nEnter a prompt (or 'quit'): ").strip()
        if user_input.lower() in ("quit", "q", "exit"):
            print("Goodbye!")
            break
        if user_input:
            make_api_call(user_input)
