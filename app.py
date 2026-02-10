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
import plivo

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
PLIVO_NUMBER = os.getenv("PLIVO_NUMBER", "19182150247")

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
        self.misheard_count = 0  # Track consecutive misheard inputs
        self.is_speaking = False  # Track if agent is currently speaking (for barge-in)
        self.reservation_confirmed = False
        self.barge_in_counter = 0  # Count consecutive high-energy chunks for barge-in

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    def increment_misheard(self):
        self.misheard_count += 1
        return self.misheard_count

    def reset_misheard(self):
        self.misheard_count = 0


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
    """Get response from OpenAI with error handling for irrelevant input"""

    # Check for very short or potentially misheard input
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

        # Check if this is a clarification request (misheard handling)
        clarification_phrases = ["didn't catch", "didn't understand", "could you repeat", "say that again", "please repeat"]
        if any(phrase in assistant_message.lower() for phrase in clarification_phrases):
            conversation.increment_misheard()
        else:
            conversation.reset_misheard()

        # Check if reservation is confirmed
        if "confirmed" in assistant_message.lower() and "goodbye" in assistant_message.lower():
            conversation.reservation_confirmed = True
            # Extract reservation details from conversation
            extract_reservation_details(conversation)

        return assistant_message
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "Sorry, I'm having trouble understanding. Could you please repeat that?"


def extract_reservation_details(conversation: ConversationState):
    """Extract reservation details from conversation for SMS confirmation"""
    try:
        # Use GPT to extract details
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
    """Send SMS confirmation after reservation is complete"""
    if not conversation.caller_number or not conversation.reservation_confirmed:
        return

    try:
        # Format the SMS message
        r = conversation.reservation
        sms_message = f"""🍝 Mario's Italian Kitchen - Reservation Confirmed!

📅 Date: {r.get('date', 'N/A')}
🕐 Time: {r.get('time', 'N/A')}
👥 Party Size: {r.get('party_size', 'N/A')}
📛 Name: {r.get('name', 'N/A')}

Thank you for choosing Mario's! We look forward to seeing you.

To modify or cancel, call us at +1 (918) 215-0247"""

        # Send SMS via Plivo
        plivo_client.messages.create(
            src=PLIVO_NUMBER,
            dst=conversation.caller_number,
            text=sms_message
        )
        logger.info(f"📱 SMS confirmation sent to {conversation.caller_number}")
    except Exception as e:
        logger.error(f"SMS error: {e}")


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

    # Store caller number for SMS follow-up
    conversations[call_uuid] = ConversationState(call_uuid, from_number)

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

    # Send SMS confirmation if reservation was made
    if call_uuid in conversations:
        conversation = conversations[call_uuid]
        if conversation.reservation_confirmed:
            asyncio.create_task(send_sms_confirmation(conversation))
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

    greeting_sent = False
    processing_lock = asyncio.Lock()

    # Deepgram streaming connection
    deepgram_ws = None
    transcript_queue = asyncio.Queue()

    async def connect_deepgram():
        """Connect to Deepgram streaming STT"""
        url = f"wss://api.deepgram.com/v1/listen?encoding=mulaw&sample_rate=8000&channels=1&model=nova-2&punctuate=true&interim_results=false&endpointing=300"
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

    async def clear_audio_queue():
        """Send clearAudio event to stop current playback (barge-in)"""
        try:
            msg = {"event": "clearAudio"}
            await websocket.send_text(json.dumps(msg))
            logger.info("🛑 Audio cleared (barge-in)")
        except Exception as e:
            logger.error(f"Clear audio error: {e}")

    async def send_audio_to_plivo(audio_bytes: bytes):
        """Send audio to Plivo in proper chunks (≤16KB base64)"""
        conversation.is_speaking = True
        max_chunk_raw = 8000  # 8KB raw = ~11KB base64

        for i in range(0, len(audio_bytes), max_chunk_raw):
            # Check if we should stop (barge-in detected)
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
        """Process transcript and send response"""
        async with processing_lock:
            logger.info(f"🤖 Processing: {transcript}")

            # Get LLM response with error handling
            response_text = get_llm_response(conversation, transcript)
            logger.info(f"💬 Response: {response_text}")

            # Check if too many misheard attempts
            if conversation.misheard_count >= 3:
                response_text = "I'm having trouble understanding. Let me transfer you to a staff member. Please hold."
                logger.info("⚠️ Too many misheard attempts")

            # Convert to speech
            audio = await text_to_speech_elevenlabs(response_text)
            if audio:
                mulaw = await asyncio.get_event_loop().run_in_executor(
                    None, convert_mp3_to_mulaw, audio
                )
                if mulaw:
                    logger.info(f"🔊 Sending {len(mulaw)} bytes")
                    await send_audio_to_plivo(mulaw)

    async def send_greeting():
        """Send initial greeting"""
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

    # Connect to Deepgram
    deepgram_ws = await connect_deepgram()

    # Start Deepgram transcript receiver
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
                        logger.info(f"▶️ Stream started")
                        if not greeting_sent:
                            greeting_sent = True
                            asyncio.create_task(send_greeting())

                    elif event == "media":
                        payload = msg.get("media", {}).get("payload", "")
                        if payload:
                            chunk = base64.b64decode(payload)

                            # Send to Deepgram (barge-in disabled - was too sensitive)
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
        if deepgram_ws:
            await deepgram_ws.close()
        if deepgram_task:
            deepgram_task.cancel()

        # Send SMS if reservation confirmed
        if conversation.reservation_confirmed:
            asyncio.create_task(send_sms_confirmation(conversation))

        conversations.pop(call_uuid, None)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
