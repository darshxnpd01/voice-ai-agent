"""
Day 5 Project 2 & 5: LiveKit Agent — Mario's Italian Kitchen AI Receptionist
Pipeline: VAD → Deepgram STT → OpenAI GPT-4o-mini → ElevenLabs TTS
livekit-agents >= 1.0
"""
import asyncio
import os

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
)
from livekit.plugins import deepgram, elevenlabs, openai, silero

load_dotenv()

SYSTEM_PROMPT = """You are the AI receptionist for Mario's Italian Kitchen.
Be extremely brief — maximum 1 sentence per response. Never use filler words.

Facts:
- Hours: Monday–Sunday, 5 PM to 10 PM
- Location: 123 Main Street, Downtown
- Reservations: need name, date, time, party size

Confirm reservation details in one sentence, then end politely."""


def save_reservation(name: str, date: str, time: str, party_size: int) -> str:
    url = os.getenv("POSTGRES_URL", "")
    if not url or "localhost" in url:
        return f"Reservation confirmed for {name}, party of {party_size} on {date} at {time}."
    try:
        import psycopg2
        conn = psycopg2.connect(url)
        cur  = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id SERIAL PRIMARY KEY,
                name TEXT,
                date TEXT,
                time TEXT,
                party_size INTEGER,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute(
            "INSERT INTO reservations (name, date, time, party_size) VALUES (%s, %s, %s, %s)",
            (name, date, time, party_size),
        )
        conn.commit()
        cur.close()
        conn.close()
        return f"Reservation confirmed for {name}, party of {party_size} on {date} at {time}."
    except Exception as e:
        return f"Reservation noted but could not save: {e}"


class MarioReceptionist(Agent):
    def __init__(self):
        super().__init__(instructions=SYSTEM_PROMPT)

    async def make_reservation(
        self,
        name: str,
        date: str,
        time: str,
        party_size: int,
    ) -> str:
        """Save a restaurant reservation. Call this when the caller wants to book a table."""
        return save_reservation(name, date, time, party_size)


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model="nova-2", language="en-US"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=elevenlabs.TTS(
            voice_id="21m00Tcm4TlvDq8ikWAM",  # Rachel — pre-made voice
            model="eleven_turbo_v2_5",          # fastest model
        ),
    )

    await session.start(
        room=ctx.room,
        agent=MarioReceptionist(),
    )

    await session.generate_reply(
        instructions="Say exactly: Welcome to Mario's Italian Kitchen! I'm your AI receptionist. How can I help you today?"
    )


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )
