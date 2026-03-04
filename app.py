import os
import json
import base64
import asyncio
import aiohttp
import subprocess
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response, JSONResponse
import uvicorn
from dotenv import load_dotenv
from openai import OpenAI
import logging
import websockets
import plivo
import asyncpg
import redis.asyncio as aioredis
from typing import Optional

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
PLIVO_NUMBER = os.getenv("PLIVO_NUMBER", "19182150247")
# Support both local (POSTGRES_URL / REDIS_URL) and Vercel-managed databases
# (POSTGRES_URL_NON_POOLING / KV_URL) transparently.
POSTGRES_URL = os.getenv("POSTGRES_URL_NON_POOLING") or os.getenv("POSTGRES_URL")
REDIS_URL = os.getenv("KV_URL") or os.getenv("REDIS_URL")
# When set, WebSocket streams route here instead of the current host.
# Point this at your tunnel (local dev) or Railway URL (production).
WEBSOCKET_BASE_URL = os.getenv("WEBSOCKET_BASE_URL")

# Database and cache clients (initialized in lifespan)
db_pool: asyncpg.Pool = None
redis_client: aioredis.Redis = None

# OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Plivo client for SMS
plivo_client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)

# Store conversation state per call
conversations = {}

SYSTEM_PROMPT = """You are a friendly AI receptionist for Mario's Italian Kitchen restaurant. Help callers make reservations.

You need to collect:
1. Date (when they want to come)
2. Time (preferred time)
3. Party size (number of people)
4. Name (for the reservation)

Available dinner times: 5:30 PM, 6:00 PM, 6:30 PM, 7:00 PM, 7:30 PM, 8:00 PM

IMPORTANT RULES:
- Keep responses to 1-2 SHORT sentences only
- Ask for ONE piece of information at a time
- If the user says something unclear, off-topic, or irrelevant, politely say "Sorry, I didn't catch that. Could you please repeat?"
- If the user says something that doesn't make sense for a reservation (like random words, unrelated topics), ask them to clarify
- Once you have ALL info (date, time, party size, name), confirm the reservation and say "Your reservation is confirmed! Goodbye!"
- Always be polite and patient

Examples of irrelevant input to handle:
- Random words or sounds -> "Sorry, I didn't catch that. Could you please repeat?"
- Unrelated questions -> "I can only help with reservations. What date would you like to book?"
- Unclear responses -> "I didn't understand. Could you say that again?"
"""

GREETING = "Hi, thanks for calling Mario's Italian Kitchen! I can help you make a reservation. What date were you thinking?"


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize PostgreSQL pool and Redis client on startup; close on shutdown."""
    global db_pool, redis_client

    if POSTGRES_URL:
        try:
            db_pool = await asyncpg.create_pool(POSTGRES_URL)
            logger.info("✅ PostgreSQL connected")
        except Exception as e:
            logger.error(f"❌ PostgreSQL connection failed: {e}")
    else:
        logger.warning("⚠️  POSTGRES_URL not set — call logging disabled")

    if REDIS_URL:
        try:
            redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
            await redis_client.ping()
            logger.info("✅ Redis connected")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
    else:
        logger.warning("⚠️  REDIS_URL not set — session management disabled")

    yield

    if db_pool:
        await db_pool.close()
    if redis_client:
        await redis_client.aclose()


app = FastAPI(title="Voice AI Agent - Mario's Italian Kitchen", lifespan=lifespan)


# ─── Conversation State ───────────────────────────────────────────────────────

class ConversationState:
    def __init__(self, call_uuid: str, caller_number: str = None):
        self.call_uuid = call_uuid
        self.caller_number = caller_number
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.reservation = {
            "date": None,
            "time": None,
            "party_size": None,
            "name": None
        }
        self.misheard_count = 0
        self.is_speaking = False
        self.reservation_confirmed = False
        self.barge_in_counter = 0
        self.call_log_id = None  # Tracks DB row for post-call updates

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    def increment_misheard(self):
        self.misheard_count += 1
        return self.misheard_count

    def reset_misheard(self):
        self.misheard_count = 0


# ─── IVR XML Helpers ─────────────────────────────────────────────────────────

IVR_MENU = (
    "Welcome to Mario's Italian Kitchen. "
    "Press 1 for Reservations. "
    "Press 2 for Hours and Location. "
    "Press 3 to speak with someone."
)


def build_menu_xml(host: str, preamble: str = None) -> str:
    """Return Plivo XML that reads an IVR menu and waits for a digit."""
    speak_text = f"{preamble} {IVR_MENU}" if preamble else IVR_MENU
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetDigits action="https://{host}/handle-input" method="POST" numDigits="1" timeout="10" retries="3">
        <Speak>{speak_text}</Speak>
    </GetDigits>
    <Speak>We did not receive your input. Goodbye!</Speak>
</Response>"""


# ─── PostgreSQL Helpers ───────────────────────────────────────────────────────

async def log_call_start(from_number: str, to_number: str) -> Optional[int]:
    """Insert a new call_logs row and return its id."""
    if not db_pool:
        return None
    try:
        return await db_pool.fetchval(
            """INSERT INTO call_logs (caller_number, called_number, call_status, created_at)
               VALUES ($1, $2, 'started', NOW()) RETURNING id""",
            from_number, to_number
        )
    except Exception as e:
        logger.error(f"DB log_call_start error: {e}")
        return None


async def update_call_intent(call_log_id: int, intent: str, status: str = None):
    """Update detected_intent (and optionally call_status) on a call_logs row."""
    if not db_pool or not call_log_id:
        return
    try:
        if status:
            await db_pool.execute(
                "UPDATE call_logs SET detected_intent=$1, call_status=$2 WHERE id=$3",
                intent, status, call_log_id
            )
        else:
            await db_pool.execute(
                "UPDATE call_logs SET detected_intent=$1 WHERE id=$2",
                intent, call_log_id
            )
    except Exception as e:
        logger.error(f"DB update_call_intent error: {e}")


async def finalize_call_log(call_log_id: int, duration_seconds: int, summary: str = None):
    """Mark a call as completed with duration and optional transcript summary."""
    if not db_pool or not call_log_id:
        return
    try:
        await db_pool.execute(
            """UPDATE call_logs
               SET call_status='completed', duration_seconds=$1, transcript_summary=$2
               WHERE id=$3 AND call_status='started'""",
            duration_seconds, summary, call_log_id
        )
    except Exception as e:
        logger.error(f"DB finalize_call_log error: {e}")


# ─── Redis Session Helpers ────────────────────────────────────────────────────

SESSION_TTL = 1800  # 30 minutes


async def create_session(call_uuid: str, caller_number: str, call_log_id: int = None):
    """Create a new call session in Redis with 30-minute TTL."""
    if not redis_client:
        return
    try:
        session = {
            "caller_id": caller_number,
            "step": "main_menu",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "call_log_id": str(call_log_id) if call_log_id else ""
        }
        await redis_client.setex(f"session:{call_uuid}", SESSION_TTL, json.dumps(session))
    except Exception as e:
        logger.error(f"Redis create_session error: {e}")


async def get_session(call_uuid: str) -> dict:
    """Retrieve a call session from Redis; returns {} if not found."""
    if not redis_client:
        return {}
    try:
        data = await redis_client.get(f"session:{call_uuid}")
        return json.loads(data) if data else {}
    except Exception as e:
        logger.error(f"Redis get_session error: {e}")
        return {}


async def update_session_step(call_uuid: str, step: str):
    """Update the step field of an existing session (preserves other fields, resets TTL)."""
    if not redis_client:
        return
    try:
        session = await get_session(call_uuid)
        if session:
            session["step"] = step
            await redis_client.setex(f"session:{call_uuid}", SESSION_TTL, json.dumps(session))
    except Exception as e:
        logger.error(f"Redis update_session_step error: {e}")


async def delete_session(call_uuid: str):
    """Remove a call session from Redis."""
    if not redis_client:
        return
    try:
        await redis_client.delete(f"session:{call_uuid}")
    except Exception as e:
        logger.error(f"Redis delete_session error: {e}")


# ─── TTS / LLM ───────────────────────────────────────────────────────────────

async def text_to_speech_elevenlabs(text: str) -> bytes:
    """Convert text to speech using ElevenLabs."""
    voice_id = "21m00Tcm4TlvDq8ikWAM"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }

    data = {
        "text": text,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            if response.status == 200:
                return await response.read()
            logger.error(f"TTS error: {response.status}")
            return None


def get_llm_response(conversation: ConversationState, user_input: str) -> str:
    """Get a response from OpenAI with error handling for irrelevant input."""
    if len(user_input.strip()) < 2:
        conversation.increment_misheard()
        return "Sorry, I didn't catch that. Could you please repeat?"

    conversation.add_message("user", user_input)

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=conversation.messages,
            max_tokens=150,
            temperature=0.7
        )
        assistant_message = response.choices[0].message.content
        conversation.add_message("assistant", assistant_message)

        clarification_phrases = [
            "didn't catch", "didn't understand", "could you repeat",
            "say that again", "please repeat"
        ]
        if any(phrase in assistant_message.lower() for phrase in clarification_phrases):
            conversation.increment_misheard()
        else:
            conversation.reset_misheard()

        if "confirmed" in assistant_message.lower() and "goodbye" in assistant_message.lower():
            conversation.reservation_confirmed = True
            extract_reservation_details(conversation)

        return assistant_message
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "Sorry, I'm having trouble understanding. Could you please repeat that?"


def extract_reservation_details(conversation: ConversationState):
    """Extract reservation details from conversation for SMS confirmation."""
    try:
        extract_prompt = """Based on the conversation, extract the reservation details in JSON format:
        {"date": "...", "time": "...", "party_size": "...", "name": "..."}
        Only return the JSON, nothing else."""

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=conversation.messages + [{"role": "user", "content": extract_prompt}],
            max_tokens=100,
            temperature=0
        )

        details = json.loads(response.choices[0].message.content)
        conversation.reservation = details
        logger.info(f"📋 Reservation extracted: {details}")
    except Exception as e:
        logger.error(f"Failed to extract reservation: {e}")


async def send_sms_confirmation(conversation: ConversationState):
    """Send SMS confirmation after reservation is complete."""
    if not conversation.caller_number or not conversation.reservation_confirmed:
        return

    try:
        r = conversation.reservation
        sms_message = f"""🍝 Mario's Italian Kitchen - Reservation Confirmed!

📅 Date: {r.get('date', 'N/A')}
🕐 Time: {r.get('time', 'N/A')}
👥 Party Size: {r.get('party_size', 'N/A')}
📛 Name: {r.get('name', 'N/A')}

Thank you for choosing Mario's! We look forward to seeing you.

To modify or cancel, call us at +1 (918) 215-0247"""

        plivo_client.messages.create(
            src=PLIVO_NUMBER,
            dst=conversation.caller_number,
            text=sms_message
        )
        logger.info(f"📱 SMS confirmation sent to {conversation.caller_number}")
    except Exception as e:
        logger.error(f"SMS error: {e}")


def convert_mp3_to_mulaw(mp3_data: bytes) -> bytes:
    """Convert MP3 to mu-law 8kHz for Plivo."""
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
        f.write(mp3_data)
        mp3_path = f.name

    raw_path = mp3_path.replace('.mp3', '.raw')

    try:
        subprocess.run([
            'ffmpeg', '-y', '-i', mp3_path,
            '-ar', '8000', '-ac', '1', '-f', 'mulaw', raw_path
        ], capture_output=True, check=True)

        with open(raw_path, 'rb') as f:
            return f.read()
    except Exception as e:
        logger.error(f"FFmpeg error: {e}")
        return None
    finally:
        try:
            os.unlink(mp3_path)
            os.unlink(raw_path)
        except:
            pass


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "running"}


@app.get("/api/recent-calls")
async def recent_calls():
    """Return the 20 most recent call log entries."""
    if not db_pool:
        return JSONResponse({"error": "Database not configured"}, status_code=503)
    try:
        rows = await db_pool.fetch(
            """SELECT id, caller_number, called_number, call_status, detected_intent,
                      transcript_summary, duration_seconds, created_at
               FROM call_logs ORDER BY created_at DESC LIMIT 20"""
        )
        calls = []
        for row in rows:
            r = dict(row)
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
            calls.append(r)
        return {"total": len(calls), "calls": calls}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/setup-db")
async def setup_db():
    """One-time endpoint to create the call_logs table. Safe to call multiple times."""
    if not db_pool:
        return JSONResponse({"error": "Database not configured"}, status_code=503)
    try:
        await db_pool.execute("""
            CREATE TABLE IF NOT EXISTS call_logs (
                id                 SERIAL PRIMARY KEY,
                caller_number      VARCHAR(20),
                called_number      VARCHAR(20),
                call_status        VARCHAR(50),
                detected_intent    VARCHAR(50),
                transcript_summary TEXT,
                duration_seconds   INTEGER,
                created_at         TIMESTAMP DEFAULT NOW()
            )
        """)
        return {"message": "call_logs table created successfully"}
    except Exception as e:
        logger.error(f"setup_db error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/health")
async def health_check():
    """Return connectivity status for Redis and PostgreSQL."""
    result = {
        "status": "healthy",
        "redis": "ok",
        "postgres": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    if redis_client:
        try:
            await redis_client.ping()
        except Exception as e:
            result["redis"] = "error"
            result["status"] = "unhealthy"
            logger.error(f"Redis health check failed: {e}")
    else:
        result["redis"] = "not configured"
        result["status"] = "unhealthy"

    if db_pool:
        try:
            await db_pool.fetchval("SELECT 1")
        except Exception as e:
            result["postgres"] = "error"
            result["status"] = "unhealthy"
            logger.error(f"PostgreSQL health check failed: {e}")
    else:
        result["postgres"] = "not configured"
        result["status"] = "unhealthy"

    return result


@app.get("/call-history/{phone_number}")
async def call_history(phone_number: str):
    """Return all past calls for a given phone number as JSON."""
    if not db_pool:
        return JSONResponse({"error": "Database not configured"}, status_code=503)
    try:
        rows = await db_pool.fetch(
            """SELECT id, caller_number, called_number, call_status, detected_intent,
                      transcript_summary, duration_seconds, created_at
               FROM call_logs
               WHERE caller_number=$1
               ORDER BY created_at DESC""",
            phone_number
        )
        calls = []
        for row in rows:
            row_dict = dict(row)
            if row_dict.get("created_at"):
                row_dict["created_at"] = row_dict["created_at"].isoformat()
            calls.append(row_dict)
        return {"phone_number": phone_number, "calls": calls}
    except Exception as e:
        logger.error(f"Call history error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/webhook/answer")
async def answer_call(request: Request):
    """Handle incoming call — log to DB, create Redis session, serve IVR menu."""
    form_data = await request.form()
    call_uuid = form_data.get("CallUUID", "unknown")
    from_number = form_data.get("From", "unknown")
    to_number = form_data.get("To", PLIVO_NUMBER)

    logger.info(f"📞 Incoming call: {call_uuid} from {from_number}")

    call_log_id = await log_call_start(from_number, to_number)
    await create_session(call_uuid, from_number, call_log_id)

    host = request.headers.get("host", "localhost:8000")
    return Response(content=build_menu_xml(host), media_type="application/xml")


@app.post("/handle-input")
async def handle_input(request: Request):
    """Process DTMF digit from IVR menu and route the call."""
    form_data = await request.form()
    call_uuid = form_data.get("CallUUID", "unknown")
    from_number = form_data.get("From", "unknown")
    digit = form_data.get("Digits", "")

    host = request.headers.get("host", "localhost:8000")
    logger.info(f"🔢 DTMF '{digit}' from {from_number} (call: {call_uuid})")

    # Read session to get call_log_id
    session = await get_session(call_uuid)
    call_log_id_str = session.get("call_log_id", "")
    call_log_id = int(call_log_id_str) if call_log_id_str else None

    if digit == "1":
        # ── Reservations → launch AI voice agent ──────────────────────────
        await update_session_step(call_uuid, "reservations")
        await update_call_intent(call_log_id, "reservations")

        conversations[call_uuid] = ConversationState(call_uuid, from_number)
        conversations[call_uuid].call_log_id = call_log_id

        ws_base = WEBSOCKET_BASE_URL or f"wss://{host}"
        ws_url = f"{ws_base}/ws/audio/{call_uuid}"
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">{ws_url}</Stream>
</Response>"""
        return Response(content=xml, media_type="application/xml")

    elif digit == "2":
        # ── Hours & Location → speak info, replay menu ────────────────────
        await update_session_step(call_uuid, "faq")
        await update_call_intent(call_log_id, "faq")

        preamble = (
            "We are open Tuesday through Sunday from 5 PM to 10 PM, closed on Mondays. "
            "We are located at 123 Main Street, downtown."
        )
        return Response(content=build_menu_xml(host, preamble), media_type="application/xml")

    elif digit == "3":
        # ── Transfer → farewell and hang up ───────────────────────────────
        await update_session_step(call_uuid, "transfer")
        await update_call_intent(call_log_id, "transfer", status="transferred")

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak>Please hold while we connect you. Goodbye.</Speak>
    <Hangup/>
</Response>"""
        return Response(content=xml, media_type="application/xml")

    else:
        # ── Invalid digit → error message, replay menu ────────────────────
        await update_call_intent(call_log_id, "invalid")

        return Response(
            content=build_menu_xml(host, "Invalid option, please try again."),
            media_type="application/xml"
        )


@app.post("/webhook/hangup")
async def hangup_call(request: Request):
    """Handle call end — finalize DB log, clean up Redis session."""
    form_data = await request.form()
    call_uuid = form_data.get("CallUUID", "unknown")
    logger.info(f"📴 Call ended: {call_uuid}")

    session = await get_session(call_uuid)
    if session:
        call_log_id_str = session.get("call_log_id", "")
        call_log_id = int(call_log_id_str) if call_log_id_str else None

        duration_seconds = None
        started_at_str = session.get("started_at")
        if started_at_str:
            started_at = datetime.fromisoformat(started_at_str)
            duration_seconds = int((datetime.now(timezone.utc) - started_at).total_seconds())

        # Build transcript summary if a reservation was confirmed
        summary = None
        if call_uuid in conversations:
            conv = conversations[call_uuid]
            if conv.reservation_confirmed:
                r = conv.reservation
                summary = (
                    f"Reservation confirmed for {r.get('name')} on {r.get('date')} "
                    f"at {r.get('time')} for {r.get('party_size')} people."
                )

        await finalize_call_log(call_log_id, duration_seconds, summary)
        await delete_session(call_uuid)

    # Send SMS if reservation was confirmed
    if call_uuid in conversations:
        conversation = conversations[call_uuid]
        if conversation.reservation_confirmed:
            asyncio.create_task(send_sms_confirmation(conversation))
        conversations.pop(call_uuid, None)

    return {"status": "ok"}


@app.websocket("/ws/audio/{call_uuid}")
async def audio_websocket(websocket: WebSocket, call_uuid: str):
    """Handle bidirectional audio streaming with Plivo."""
    await websocket.accept()
    logger.info(f"🔌 WebSocket connected: {call_uuid}")

    if call_uuid not in conversations:
        conversations[call_uuid] = ConversationState(call_uuid)
    conversation = conversations[call_uuid]

    greeting_sent = False
    processing_lock = asyncio.Lock()

    deepgram_ws = None
    transcript_queue = asyncio.Queue()

    async def connect_deepgram():
        url = (
            "wss://api.deepgram.com/v1/listen"
            "?encoding=mulaw&sample_rate=8000&channels=1"
            "&model=nova-2&punctuate=true&interim_results=false&endpointing=300"
        )
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
        try:
            ws = await websockets.connect(url, extra_headers=headers)
            logger.info("🎤 Deepgram connected")
            return ws
        except Exception as e:
            logger.error(f"Deepgram connection error: {e}")
            return None

    async def receive_deepgram_transcripts(dg_ws):
        try:
            async for message in dg_ws:
                data = json.loads(message)
                if data.get("type") == "Results":
                    transcript = (
                        data.get("channel", {})
                            .get("alternatives", [{}])[0]
                            .get("transcript", "")
                    )
                    if transcript.strip():
                        logger.info(f"📝 Transcript: {transcript}")
                        await transcript_queue.put(transcript)
        except Exception as e:
            logger.error(f"Deepgram receive error: {e}")

    async def send_audio_to_plivo(audio_bytes: bytes):
        conversation.is_speaking = True
        max_chunk_raw = 8000  # 8KB raw ≈ 11KB base64

        for i in range(0, len(audio_bytes), max_chunk_raw):
            if not conversation.is_speaking:
                logger.info("🛑 Stopping audio send (interrupted)")
                break

            chunk = audio_bytes[i:i + max_chunk_raw]
            payload = base64.b64encode(chunk).decode()

            msg = {
                "event": "playAudio",
                "media": {
                    "contentType": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "payload": payload
                }
            }

            try:
                await websocket.send_text(json.dumps(msg))
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Send error: {e}")
                break

        conversation.is_speaking = False

    async def process_and_respond(transcript: str):
        async with processing_lock:
            logger.info(f"🤖 Processing: {transcript}")

            response_text = get_llm_response(conversation, transcript)
            logger.info(f"💬 Response: {response_text}")

            if conversation.misheard_count >= 3:
                response_text = (
                    "I'm having trouble understanding. "
                    "Let me transfer you to a staff member. Please hold."
                )
                logger.info("⚠️ Too many misheard attempts")

            audio = await text_to_speech_elevenlabs(response_text)
            if audio:
                mulaw = await asyncio.get_event_loop().run_in_executor(
                    None, convert_mp3_to_mulaw, audio
                )
                if mulaw:
                    logger.info(f"🔊 Sending {len(mulaw)} bytes")
                    await send_audio_to_plivo(mulaw)

    async def send_greeting():
        logger.info("🎙️ Sending greeting...")
        audio = await text_to_speech_elevenlabs(GREETING)
        if audio:
            mulaw = await asyncio.get_event_loop().run_in_executor(
                None, convert_mp3_to_mulaw, audio
            )
            if mulaw:
                logger.info(f"📤 Greeting: {len(mulaw)} bytes")
                await send_audio_to_plivo(mulaw)
                logger.info("✅ Greeting sent")

    deepgram_ws = await connect_deepgram()
    deepgram_task = None
    if deepgram_ws:
        deepgram_task = asyncio.create_task(receive_deepgram_transcripts(deepgram_ws))

    try:
        while True:
            try:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                    msg = json.loads(data)
                    event = msg.get("event")

                    if event == "start":
                        logger.info("▶️ Stream started")
                        if not greeting_sent:
                            greeting_sent = True
                            asyncio.create_task(send_greeting())

                    elif event == "media":
                        payload = msg.get("media", {}).get("payload", "")
                        if payload:
                            chunk = base64.b64decode(payload)
                            if deepgram_ws:
                                try:
                                    await deepgram_ws.send(chunk)
                                except:
                                    pass

                    elif event == "stop":
                        logger.info("⏹️ Stream stopped")
                        break

                except asyncio.TimeoutError:
                    pass

                try:
                    transcript = transcript_queue.get_nowait()
                    asyncio.create_task(process_and_respond(transcript))
                except asyncio.QueueEmpty:
                    pass

            except Exception as e:
                if "disconnect" in str(e).lower():
                    break
                logger.error(f"Loop error: {e}")

    except WebSocketDisconnect:
        logger.info(f"🔌 Disconnected: {call_uuid}")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
    finally:
        if deepgram_ws:
            await deepgram_ws.close()
        if deepgram_task:
            deepgram_task.cancel()

        if conversation.reservation_confirmed:
            asyncio.create_task(send_sms_confirmation(conversation))

        conversations.pop(call_uuid, None)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
