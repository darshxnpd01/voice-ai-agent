#!/usr/bin/env python3
"""
Setup script to configure Plivo application webhooks
"""

import sys
import os
import plivo
from dotenv import load_dotenv

load_dotenv()

PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")
PLIVO_NUMBER = os.getenv("PLIVO_NUMBER", "19182150247")

def setup_plivo_app(ngrok_url: str):
    """Create or update Plivo application with webhooks"""

    client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)

    answer_url = f"{ngrok_url}/webhook/answer"
    hangup_url = f"{ngrok_url}/webhook/hangup"

    app_name = "VoiceAIAgent-MarioRestaurant"

    try:
        # List existing applications to find if one exists
        apps = client.applications.list(limit=20)
        existing_app = None

        for app in apps:
            if app.app_name == app_name:
                existing_app = app
                break

        if existing_app:
            # Update existing application
            client.applications.update(
                existing_app.app_id,
                answer_url=answer_url,
                answer_method="POST",
                hangup_url=hangup_url,
                hangup_method="POST"
            )
            app_id = existing_app.app_id
            print(f"Updated existing application: {app_id}")
        else:
            # Create new application
            response = client.applications.create(
                app_name=app_name,
                answer_url=answer_url,
                answer_method="POST",
                hangup_url=hangup_url,
                hangup_method="POST"
            )
            app_id = response.app_id
            print(f"Created new application: {app_id}")

        # Link phone number to application
        client.numbers.update(
            PLIVO_NUMBER,
            app_id=app_id
        )
        print(f"Linked number {PLIVO_NUMBER} to application")

        print(f"\n✅ Setup complete!")
        print(f"Answer URL: {answer_url}")
        print(f"Hangup URL: {hangup_url}")
        print(f"Phone Number: +1 {PLIVO_NUMBER[:3]}-{PLIVO_NUMBER[3:6]}-{PLIVO_NUMBER[6:]}")

        return app_id

    except Exception as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python setup_plivo.py <ngrok-url>")
        print("Example: python setup_plivo.py https://abc123.ngrok.io")
        sys.exit(1)

    ngrok_url = sys.argv[1].rstrip('/')

    if not ngrok_url.startswith("https://"):
        print("Error: ngrok URL must start with https://")
        sys.exit(1)

    setup_plivo_app(ngrok_url)
