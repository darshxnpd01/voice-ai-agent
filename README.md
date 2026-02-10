# Voice AI Agent - Mario's Italian Kitchen 🍝

A conversational Voice AI Agent that handles inbound calls for a restaurant reservation system. Built with real-time audio streaming using Plivo, Deepgram, OpenAI, and ElevenLabs.

## Architecture

```
Inbound Call → Plivo → WebSocket Audio Stream → Deepgram STT → OpenAI GPT → ElevenLabs TTS → Caller
```

## Features

- **Real-time Speech Recognition** - Deepgram Nova-2 streaming STT
- **Natural Conversation** - OpenAI GPT-4o-mini for intelligent responses
- **Human-like Voice** - ElevenLabs text-to-speech
- **Bidirectional Audio** - Plivo WebSocket streaming

## Demo Conversation

```
Agent: "Hi, thanks for calling Mario's Italian Kitchen! I can help you make a reservation. What date were you thinking?"
Caller: "February 10th"
Agent: "Great! What time would you like? We have 5:30 PM, 6:00 PM, 6:30 PM, 7:00 PM, 7:30 PM, and 8:00 PM available."
Caller: "5:30 PM"
Agent: "Perfect! How many people are in your party?"
Caller: "Two"
Agent: "Got it! So, you have a reservation for two on February 10th at 5:30 PM. Can I get a name?"
Caller: "Darshan"
Agent: "Thank you, Darshan! Your reservation is confirmed. Goodbye!"
```

## Prerequisites

- Python 3.9+
- [Plivo Account](https://www.plivo.com/) with a phone number
- [Deepgram API Key](https://deepgram.com/)
- [OpenAI API Key](https://platform.openai.com/)
- [ElevenLabs API Key](https://elevenlabs.io/)
- ffmpeg (for audio conversion)
- ngrok or cloudflared (for tunneling)

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Darshxn001/Claude-Code-AI-voice-Agent.git
   cd Claude-Code-AI-voice-Agent
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   brew install ffmpeg  # macOS
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

4. **Start the server**
   ```bash
   python app.py
   ```

5. **Start a tunnel** (in another terminal)
   ```bash
   # Using cloudflared (recommended)
   cloudflared tunnel --url http://localhost:8000

   # Or using ngrok
   ngrok http 8000
   ```

6. **Configure Plivo webhook**
   ```bash
   python setup_plivo.py <your-tunnel-url>
   ```

7. **Call your Plivo number** and start making reservations!

## Tech Stack

| Component | Technology |
|-----------|------------|
| Voice API | Plivo (Audio Streaming) |
| Speech-to-Text | Deepgram Nova-2 (Streaming) |
| LLM | OpenAI GPT-4o-mini |
| Text-to-Speech | ElevenLabs |
| Backend | FastAPI + WebSockets |

## Project Structure

```
├── app.py              # Main FastAPI application
├── setup_plivo.py      # Plivo webhook configuration
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variables template
└── README.md           # This file
```

## How It Works

1. **Inbound Call**: Caller dials the Plivo number
2. **Audio Stream**: Plivo establishes a bidirectional WebSocket connection
3. **Speech Recognition**: Audio is streamed to Deepgram for real-time transcription
4. **AI Processing**: Transcripts are sent to OpenAI for response generation
5. **Voice Synthesis**: Responses are converted to speech via ElevenLabs
6. **Audio Playback**: Audio is streamed back to the caller through Plivo

## Resources

- [Plivo Audio Streaming Guide](https://www.plivo.com/docs/voice-agents/audio-streaming/concepts/audio-streaming-guide)
- [Deepgram Streaming API](https://developers.deepgram.com/docs/streaming)
- [OpenAI API](https://platform.openai.com/docs)
- [ElevenLabs API](https://elevenlabs.io/docs)

## License

MIT

---

Built with Claude Code 🤖
