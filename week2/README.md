# Week 2: AI Voice Agents — Complete Guide

This folder contains all Week 2 projects, organized by day.
Each day builds on the previous one, ending with a production AI receptionist.

---

## Before You Start — Sign Up for These Services

| Service | URL | What to get |
|---------|-----|-------------|
| OpenAI | platform.openai.com | API key + add $5-10 credit |
| Deepgram | console.deepgram.com | API key (free $200 credit) |
| ElevenLabs | elevenlabs.io | API key (free tier) |
| Railway | railway.app | Account (for Day 6) |

Add all keys to your `.env` file at the project root (already there from Week 1):
```
OPENAI_API_KEY=sk-...
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=...
```

---

## Day 1: LLM APIs

**Folder:** `day1_llm_apis/`

**Install once:**
```bash
cd day1_llm_apis
pip install -r requirements.txt
```

**Run in order:**
```bash
python project1_basic_call.py          # Basic OpenAI call
python project2_streaming.py           # Streaming — watch tokens arrive
python project3_chatbot.py             # Multi-turn CLI chatbot
python project4_function_calling.py    # LLM decides when to call functions
```

**What you'll learn:**
- How to call OpenAI API and get responses
- What streaming is and why TTFT (time-to-first-token) matters
- How conversation history works (why the chatbot remembers things)
- How function/tool calling works — the LLM picks when to call functions

**Verify:** After project4, ask "What time is it?" — watch it call `get_current_time` automatically.

---

## Day 2: Speech AI (STT + TTS)

**Folder:** `day2_speech_ai/`

**Install once:**
```bash
cd day2_speech_ai
pip install -r requirements.txt
```

**On Mac, also run:**
```bash
brew install portaudio    # needed for microphone access
```

**Run in order:**
```bash
# Project 1: Transcribe an audio file
# First record something: open QuickTime → New Audio Recording → save
python project1_transcribe_file.py your_recording.m4a

# Project 2: Real-time mic transcription
python project2_realtime_transcription.py   # Speak and watch words appear

# Project 3: Text to speech
python project3_tts.py "Hello, this is Mario's Italian Kitchen"

# Project 4: Streaming TTS
python project4_streaming_tts.py
python project4_streaming_tts.py --compare  # Side-by-side comparison

# Project 5: FULL PIPELINE — voice in → AI → voice out
python project5_full_pipeline.py   # Speak a question, hear an AI response!
```

**What you'll learn:**
- Deepgram STT (speech-to-text) for both file and real-time
- ElevenLabs TTS (text-to-speech) streaming and non-streaming
- The full voice pipeline and where latency comes from (~5-15s here)

---

## Day 3: Pipecat Local Voice Bot

**Folder:** `day3_pipecat_local/`

**Install once:**
```bash
cd day3_pipecat_local
pip install -r requirements.txt
```

**Run:**
```bash
# Basic voice bot — talk to it through your microphone
python bot.py

# Restaurant receptionist (function calling for hours, reservations)
python bot_receptionist.py
```

**What you'll learn:**
- Pipecat's pipeline architecture (frames flowing through processors)
- How real-time voice AI works — latency drops from 15s to under 2s
- Interruption handling — speak while AI is talking → it stops
- Function calling in a voice context

**Verify:**
- Talk to the bot — latency should be under 2 seconds
- Try interrupting mid-sentence — it should stop and listen
- Ask "what time is it?" → it calls the function and answers

---

## Day 4: Pipecat + Plivo (Real Phone Calls)

**Folder:** `day4_pipecat_plivo/`

**Install once:**
```bash
cd day4_pipecat_plivo
pip install -r requirements.txt
```

**Run:**
```bash
python server.py    # Starts on port 8000
```

**Setup steps (do this while server is running):**

1. **Start ngrok** (in a new terminal):
   ```bash
   ngrok http 8000
   ```
   Copy the ngrok URL (e.g., `https://abc123.ngrok.io`)

2. **Set the URL in your .env:**
   ```
   WEBSOCKET_BASE_URL=abc123.ngrok.io
   ```
   Restart the server after this.

3. **Configure Plivo:**
   - Go to Plivo console → Phone Numbers → click your number
   - Answer URL: `https://abc123.ngrok.io/answer`
   - Method: POST
   - Click Save

4. **Call your Plivo number!**

**What you'll learn:**
- How Plivo WebSocket streaming works with Pipecat
- End-to-end phone AI pipeline
- Call logging to Postgres, sessions in Redis

**Verify:**
- Call your number → hear the greeting
- Ask about hours → AI uses the function tool
- Make a reservation → it confirms and logs it
- Check the `/reservations` endpoint: `http://localhost:8000/reservations`

---

## Day 5: LiveKit (Optional)

Day 5 is an optional alternative approach using LiveKit + SIP instead of Pipecat + WebSocket.
This is more complex to set up and the plan marks it as optional.
Come back to this after Days 1-4 are working.

---

## Day 6: Deploy to Railway

**Folder:** `day6_railway/`

This deploys your Day 4 server to Railway so it runs 24/7 without your laptop.

**Steps:**

1. **Install Railway CLI:**
   ```bash
   npm install -g @railway/cli
   railway login
   ```

2. **Create project on Railway:**
   ```bash
   cd day4_pipecat_plivo   # Deploy from here (where server.py lives)
   railway init
   ```
   Select "Create a new project" when prompted.

3. **Add environment variables in Railway dashboard:**
   - Go to railway.app → your project → Variables
   - Add ALL of these:
     ```
     OPENAI_API_KEY=sk-...
     DEEPGRAM_API_KEY=...
     ELEVENLABS_API_KEY=...
     PLIVO_AUTH_ID=...
     PLIVO_AUTH_TOKEN=...
     PLIVO_NUMBER=...
     POSTGRES_URL=<copy your POSTGRES_URL_NON_POOLING from Vercel>
     REDIS_URL=<copy your KV_URL from Vercel>
     ```
   - Leave WEBSOCKET_BASE_URL blank for now (add it after deploy)

4. **Create a Dockerfile in day4_pipecat_plivo:**
   Copy the Dockerfile from `day6_railway/Dockerfile` into `day4_pipecat_plivo/`:
   ```bash
   cp ../day6_railway/Dockerfile .
   cp ../day6_railway/railway.toml .
   ```

5. **Deploy:**
   ```bash
   railway up
   ```

6. **After deploy:**
   - Go to Railway dashboard → your service → Settings → Generate Domain
   - Note your domain: `your-app.up.railway.app`
   - Add to Railway Variables: `WEBSOCKET_BASE_URL=your-app.up.railway.app`
   - Redeploy: `railway up`

7. **Update Plivo:**
   - Plivo console → Phone Numbers → your number
   - Answer URL: `https://your-app.up.railway.app/answer`
   - No more ngrok!

8. **Test:** Call your Plivo number → works 24/7 even with your laptop off!

---

## Day 7: Polish + Demo

Things to enhance for your demo:

1. **Add a voice** — try different ElevenLabs voices
2. **Improve the system prompt** — make the AI more specific to your use case
3. **Add more functions** — menu lookup, wait times, directions
4. **Test externally** — have a friend call your number
5. **Record a demo video** — use QuickTime to record your screen + audio

---

## Troubleshooting

**"No module named pipecat"**
→ Run `pip install -r requirements.txt` in the right folder

**"Invalid API key"**
→ Check your `.env` at the project root has the right keys

**Pipecat version errors (import not found)**
→ Run `pip install pipecat-ai --upgrade`

**No audio from microphone (Days 2-3)**
→ Run `brew install portaudio` then `pip install sounddevice`
→ Check System Preferences → Security → Microphone → allow Terminal

**Plivo not connecting to WebSocket**
→ Make sure ngrok is running and WEBSOCKET_BASE_URL is set correctly
→ Check server logs for "Plivo WebSocket connected"

**For any other error:**
→ Copy the full error message and tell Claude Code what you were running
