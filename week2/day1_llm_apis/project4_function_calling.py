"""
Day 1 - Project 4: Function Calling (Tools)
============================================
What this does:
- Adds "tools" (functions) to the chatbot
- LLM decides WHEN to call a function based on what you ask
- Functions: get_current_time, get_weather, lookup_order
- Shows you exactly when and why a function is called

Why this matters for voice AI:
  This is how a voice receptionist can:
  - Check calendar availability
  - Look up order status
  - Get business hours from a database
  The AI decides when to call these, you don't need to hardcode it.

How to run:
  python project4_function_calling.py

Try asking:
  "What time is it?"                → calls get_current_time
  "What's the weather in Tokyo?"    → calls get_weather
  "What's the status of order 42?"  → calls lookup_order
  "Tell me a joke"                  → NO function called
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent.parent.parent / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─── Define the functions (tools) ────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "The city name"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up the status of a customer order by order number",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID or number"},
                },
                "required": ["order_id"],
            },
        },
    },
]


# ─── Actual function implementations ─────────────────────────────────────────

def get_current_time() -> dict:
    now = datetime.now()
    return {
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "timezone": "local",
    }


def get_weather(city: str) -> dict:
    # Mock data — in production you'd call a real weather API
    mock_weather = {
        "tokyo": {"temp": "18°C", "condition": "Partly cloudy", "humidity": "65%"},
        "new york": {"temp": "22°C", "condition": "Sunny", "humidity": "45%"},
        "london": {"temp": "12°C", "condition": "Rainy", "humidity": "80%"},
    }
    data = mock_weather.get(city.lower(), {"temp": "20°C", "condition": "Clear", "humidity": "55%"})
    return {"city": city, **data}


def lookup_order(order_id: str) -> dict:
    # Mock data — in production you'd query your database
    mock_orders = {
        "42":    {"status": "Shipped", "item": "Wireless Headphones", "eta": "Tomorrow"},
        "100":   {"status": "Processing", "item": "Laptop Stand", "eta": "3-5 days"},
        "999":   {"status": "Delivered", "item": "Phone Case", "eta": "Already delivered"},
    }
    order = mock_orders.get(str(order_id), {"status": "Not found", "item": "Unknown", "eta": "N/A"})
    return {"order_id": order_id, **order}


def execute_function(name: str, arguments: dict) -> str:
    """Call the right function and return JSON result."""
    if name == "get_current_time":
        result = get_current_time()
    elif name == "get_weather":
        result = get_weather(**arguments)
    elif name == "lookup_order":
        result = lookup_order(**arguments)
    else:
        result = {"error": f"Unknown function: {name}"}
    return json.dumps(result)


# ─── Chat loop with function calling ─────────────────────────────────────────

def chat_with_tools(messages: list[dict]) -> str:
    """Send messages, handle any function calls, return final text."""
    start = time.time()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.7,
        max_tokens=400,
    )

    message = response.choices[0].message

    # No function call — just return the text
    if not message.tool_calls:
        elapsed = time.time() - start
        print(f"\nAssistant: {message.content}")
        print(f"[No function called | {elapsed:.2f}s]")
        return message.content

    # Function(s) were called
    print(f"\n[LLM decided to call {len(message.tool_calls)} function(s):]")
    # Convert Pydantic model to plain dict so OpenAI SDK can serialize it
    messages.append({
        "role": "assistant",
        "content": message.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ],
    })

    for tool_call in message.tool_calls:
        func_name = tool_call.function.name
        func_args = json.loads(tool_call.function.arguments)

        print(f"  → {func_name}({func_args})")
        result = execute_function(func_name, func_args)
        print(f"    Result: {result}")

        # Add the function result to messages
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result,
        })

    # Send function results back to LLM for final answer
    final_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=400,
    )

    elapsed = time.time() - start
    final_text = final_response.choices[0].message.content
    print(f"\nAssistant: {final_text}")
    print(f"[Total time including function call: {elapsed:.2f}s]")
    return final_text


def run():
    print("=" * 55)
    print("  Function Calling Demo")
    print("  Try: 'What time is it?', 'Weather in Tokyo?',")
    print("       'Status of order 42?', 'Tell me a joke'")
    print("  Type 'quit' to exit")
    print("=" * 55)

    system_prompt = (
        "You are a helpful assistant with access to tools. "
        "Use the tools when needed to answer questions accurately."
    )
    conversation = [{"role": "system", "content": system_prompt}]

    while True:
        user_input = input("\nYou: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "q", "exit"):
            print("Goodbye!")
            break

        conversation.append({"role": "user", "content": user_input})
        response = chat_with_tools(list(conversation))  # pass a copy
        conversation.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    run()
