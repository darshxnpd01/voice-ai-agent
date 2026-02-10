import os
import json
import base64
import asyncio
import aiohttp
import subprocess
import tempfile
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response
import uvicorn
from dotenv import load_dotenv
from openai import OpenAI
import logging
import websockets

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice AI Agent - Mario's Italian Kitchen")

# Configuration
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Store conversation state per call
conversations = {}

SYSTEM_PROMPT = """You are a friendly AI receptionist for Mario's Italian Kitchen restaurant. Help callers make reservations.

Collect: date, time, party size, and name for the reservation.

Available dinner times: 5:30 PM, 6:00 PM, 6:30 PM, 7:00 PM, 7:30 PM, 8:00 PM

Rules:
- Keep responses to 1-2 SHORT sentences
- Ask for ONE piece of info at a time
- Once you have all info, confirm and say goodbye"""

GREETING = "Hi, thanks for calling Mario's Italian Kitchen! I can help you make a reservation. What date were you thinking?"


class ConversationState:
    def __init__(self, call_uuid: str):
        self.call_uuid = call_uuid
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})


async def text_to_speech_elevenlabs(text: str) -> bytes:
    """Convert text to speech using ElevenLabs"""
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
    """Get response from OpenAI"""
    conversation.add_message("user", user_input)

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=conversation.messages,
            max_tokens=100,
            temperature=0.7
        )
        assistant_message = response.choices[0].message.content
        conversation.add_message("assistant", assistant_message)
        return assistant_message
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "Sorry, could you repeat that?"


def convert_mp3_to_mulaw(mp3_data: bytes) -> bytes:
    """Convert MP3 to mu-law 8kHz for Plivo"""
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


@app.get("/")
async def root():
    return {"status": "running"}


@app.post("/webhook/answer")
async def answer_call(request: Request):
    """Handle incoming call"""
    form_data = await request.form()
    call_uuid = form_data.get("CallUUID", "unknown")
    from_number = form_data.get("From", "unknown")

    logger.info(f"📞 Incoming call: {call_uuid} from {from_number}")

    conversations[call_uuid] = ConversationState(call_uuid)

    host = request.headers.get("host", "localhost:8000")
    ws_url = f"wss://{host}/ws/audio/{call_uuid}"

    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">{ws_url}</Stream>
</Response>"""

    return Response(content=xml_response, media_type="application/xml")


@app.post("/webhook/hangup")
async def hangup_call(request: Request):
    form_data = await request.form()
    call_uuid = form_data.get("CallUUID", "unknown")
    logger.info(f"📴 Call ended: {call_uuid}")
    conversations.pop(call_uuid, None)
    return {"status": "ok"}


@app.websocket("/ws/audio/{call_uuid}")
async def audio_websocket(websocket: WebSocket, call_uuid: str):
    """Handle bidirectional audio streaming with Plivo"""
    await websocket.accept()
    logger.info(f"🔌 WebSocket connected: {call_uuid}")

    if call_uuid not in conversations:
        conversations[call_uuid] = ConversationState(call_uuid)
    conversation = conversations[call_uuid]

    # Audio buffer for collecting speech
    audio_buffer = bytearray()
    is_speaking = False
    silence_count = 0
    greeting_sent = False
    processing_lock = asyncio.Lock()

    # Deepgram streaming connection
    deepgram_ws = None
    transcript_queue = asyncio.Queue()

    async def connect_deepgram():
        """Connect to Deepgram streaming STT"""
        url = f"wss://api.deepgram.com/v1/listen?encoding=mulaw&sample_rate=8000&channels=1&model=nova-2&punctuate=true&interim_results=false"
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

        try:
            ws = await websockets.connect(url, extra_headers=headers)
            logger.info("🎤 Deepgram connected")
            return ws
        except Exception as e:
            logger.error(f"Deepgram connection error: {e}")
            return None

    async def receive_deepgram_transcripts(dg_ws):
        """Receive transcripts from Deepgram"""
        try:
            async for message in dg_ws:
                data = json.loads(message)
                if data.get("type") == "Results":
                    transcript = data.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")
                    if transcript.strip():
                        logger.info(f"📝 Transcript: {transcript}")
                        await transcript_queue.put(transcript)
        except Exception as e:
            logger.error(f"Deepgram receive error: {e}")

    async def send_audio_to_plivo(audio_bytes: bytes):
        """Send audio to Plivo in proper chunks (≤16KB base64)"""
        # 16KB base64 = ~12KB raw bytes (base64 expands by ~33%)
        max_chunk_raw = 8000  # 8KB raw = ~11KB base64, safe margin

        for i in range(0, len(audio_bytes), max_chunk_raw):
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
                # Wait a bit to not overwhelm the buffer
                # 8000 bytes at 8kHz = 1 second of audio
                await asyncio.sleep(0.5)  # Send chunks with some spacing
            except Exception as e:
                logger.error(f"Send error: {e}")
                break

    async def process_and_respond(transcript: str):
        """Process transcript and send response"""
        async with processing_lock:
            logger.info(f"🤖 Processing: {transcript}")

            # Get LLM response
            response_text = get_llm_response(conversation, transcript)
            logger.info(f"💬 Response: {response_text}")

            # Convert to speech
            audio = await text_to_speech_elevenlabs(response_text)
            if audio:
                mulaw = await asyncio.get_event_loop().run_in_executor(
                    None, convert_mp3_to_mulaw, audio
                )
                if mulaw:
                    logger.info(f"🔊 Sending {len(mulaw)} bytes in chunks")
                    await send_audio_to_plivo(mulaw)

    async def send_greeting():
        """Send initial greeting"""
        logger.info("🎙️ Generating greeting...")
        audio = await text_to_speech_elevenlabs(GREETING)
        if audio:
            mulaw = await asyncio.get_event_loop().run_in_executor(
                None, convert_mp3_to_mulaw, audio
            )
            if mulaw:
                logger.info(f"📤 Sending greeting: {len(mulaw)} bytes")
                await send_audio_to_plivo(mulaw)
                logger.info("✅ Greeting sent")

    # Connect to Deepgram
    deepgram_ws = await connect_deepgram()

    # Start Deepgram transcript receiver
    deepgram_task = None
    if deepgram_ws:
        deepgram_task = asyncio.create_task(receive_deepgram_transcripts(deepgram_ws))

    try:
        while True:
            try:
                # Use wait_for with a short timeout to allow checking transcript queue
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                    msg = json.loads(data)
                    event = msg.get("event")

                    if event == "start":
                        logger.info(f"▶️ Stream started")

                        # Send greeting
                        if not greeting_sent:
                            greeting_sent = True
                            asyncio.create_task(send_greeting())

                    elif event == "media":
                        payload = msg.get("media", {}).get("payload", "")
                        if payload:
                            chunk = base64.b64decode(payload)

                            # Send to Deepgram for real-time transcription
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

                # Check for transcripts
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
        # Cleanup
        if deepgram_ws:
            await deepgram_ws.close()
        if deepgram_task:
            deepgram_task.cancel()
        conversations.pop(call_uuid, None)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
