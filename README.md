# Voice Fairy — Local Real-Time Voice Assistant

A fully local, real-time voice assistant in the browser.
Press and hold the pink fairy to speak — the agent answers in streaming audio, sentence by sentence, before it has even finished thinking.
No cloud APIs. No subscriptions. Everything runs on your machine.

---

## How It Works

```
Browser (hold fairy button)
    │ WebM audio (WebSocket binary frame)
    ▼
faster-whisper base.en          →  speech → text transcript
    │
    ▼
Ollama llama3.2:3b (streaming)  →  token stream
    │
    ▼
Sentence splitter               →  sentence 1 ready → macOS TTS → PCM audio → browser ▶
                                →  sentence 2 ready → macOS TTS → PCM audio → browser ▶
                                →  ...
    ▼
Web Audio API AnalyserNode      →  amplitude → pink fairy dot pulses in real time
```

- First audio plays within ~1 second of you finishing speaking
- Speak while the agent is talking to **interrupt it** (barge-in)
- The fairy dot pulses and glows to the agent's voice amplitude
- All UI surfaces use a **liquid glass** (glassmorphism) aesthetic

---

## Stack

| Role | Technology |
|------|-----------|
| Web UI | React 18 + TypeScript + Vite |
| API / WebSocket | FastAPI + uvicorn |
| Audio capture | `MediaRecorder` API (push-to-talk) |
| Speech-to-text | `faster-whisper` (`base.en`) |
| Language model | [Ollama](https://ollama.com) — `llama3.2:3b` (streaming) |
| Text-to-speech | macOS `say` + `afconvert` (Apple Neural TTS) |
| Audio playback | Web Audio API (`AudioContext`, `AnalyserNode`) |

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| macOS | TTS uses built-in `say` / `afconvert` commands |
| Python 3.11 | 3.12+ not supported (Coqui dependency chain) |
| [Ollama](https://ollama.com/download) | Must be running before starting the app |
| Node.js 18+ | For building / running the frontend |
| Chrome / Firefox / Safari | Desktop browser with microphone access |

---

## Installation

```bash
# 1. Create a Python 3.11 virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 2. Install Python dependencies
pip install -e ".[dev]"

# 3. Pull the language model
ollama pull llama3.2:3b

# 4. Install frontend dependencies
cd frontend && npm install && cd ..
```

---

## Configuration

Create a `.env` file in the project root (all values are optional — defaults shown):

```env
# Language model
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

# Speech-to-text
WHISPER_MODEL=base.en
WHISPER_DEVICE=cpu          # or cuda
WHISPER_COMPUTE_TYPE=int8   # or float16 on GPU

# Text-to-speech — macOS voice name
# List available voices: say -v '?' | grep en_
MACOS_TTS_VOICE=Samantha    # other options: Karen, Moira, Fiona, Daniel

# Server
API_PORT=8000
API_HOST=0.0.0.0
```

---

## Running the App

```bash
# Terminal 1: start Ollama
ollama serve

# Terminal 2: start the backend
source .venv/bin/activate
python src/app.py
```

Open **http://localhost:8000** in your browser and grant microphone permission.

**Development mode** (Vite HMR):

```bash
# Terminal 3
cd frontend && npm run dev
# Open http://localhost:5173
```

**Build the frontend** (required before production use):

```bash
cd frontend && npm run build
```

---

## Usage

1. Open the page — the pink fairy appears, idle-pulsing
2. **Hold** the fairy dot to speak your message
3. **Release** to send — the agent begins responding immediately
4. **Speak while the agent is talking** to interrupt it (barge-in)
5. The fairy pulses and glows in sync with the agent's voice

The status badge in the bottom-left shows the current state: Ready → Listening → Thinking → Speaking.

---

## Project Structure

```
.
├── src/                            # Python backend
│   ├── app.py                      # FastAPI + uvicorn entry point
│   ├── config.py                   # Settings loaded from .env
│   ├── api/
│   │   ├── websocket.py            # WebSocket endpoint /ws/{session_id}
│   │   ├── routes.py               # GET /health + static file serving
│   │   └── session_manager.py      # In-memory session registry
│   ├── pipeline/
│   │   ├── stream_orchestrator.py  # STT → LLM → TTS, fully streaming
│   │   ├── sentence_splitter.py    # Token stream → sentence boundaries
│   │   ├── stt.py                  # faster-whisper transcribe()
│   │   ├── llm.py                  # Ollama stream_chat() + chat()
│   │   └── tts.py                  # macOS say + afconvert synthesise()
│   └── session/
│       └── history.py              # In-memory ConversationHistory
├── frontend/                       # React + TypeScript frontend
│   ├── src/
│   │   ├── App.tsx                 # Root layout — fairy + badge + overlays
│   │   ├── components/
│   │   │   ├── FairyDot.tsx        # Amplitude-driven pink SVG dot
│   │   │   ├── StatusBadge.tsx     # Glassmorphism state pill
│   │   │   ├── MicPermission.tsx   # Mic denied overlay
│   │   │   └── ErrorBoundary.tsx   # Catches render errors
│   │   ├── hooks/
│   │   │   ├── useVoiceSession.ts  # WebSocket state machine
│   │   │   ├── useAudioCapture.ts  # MediaRecorder push-to-talk
│   │   │   ├── useAudioPlayer.ts   # Web Audio PCM queue player
│   │   │   └── useFairyAmplitude.ts # AnalyserNode → 0–1 amplitude
│   │   └── services/
│   │       └── wsClient.ts         # WebSocket with exponential backoff
│   └── package.json
├── tests/
│   ├── unit/
│   │   ├── test_history.py
│   │   ├── test_sentence_splitter.py
│   │   └── test_streaming_pipeline.py
│   └── integration/
│       └── test_pipeline.py
├── .env                            # Local config (not committed)
└── pyproject.toml
```

---

## WebSocket Protocol

All real-time communication uses a single WebSocket at `ws://localhost:8000/ws/{session_id}`.

| Frame type | Direction | Meaning |
|------------|-----------|---------|
| Binary | client → server | WebM audio (user utterance) |
| `end_utterance` JSON | client → server | User released the button |
| `barge_in` JSON | client → server | User spoke while agent was playing |
| Binary | server → client | Raw PCM audio chunk (16-bit, 16 kHz, mono) |
| `state_change` JSON | server → client | Session state update |
| `transcript` JSON | server → client | STT result |
| `agent_text_chunk` JSON | server → client | One synthesised sentence |
| `agent_done` JSON | server → client | All sentences sent |
| `error` JSON | server → client | Error with code + message |

---

## Running Tests

```bash
# Unit tests (no external services required)
PYTHONPATH=. .venv/bin/python3.11 -m pytest tests/unit/ -v

# Integration tests (requires Ollama running)
PYTHONPATH=. .venv/bin/python3.11 -m pytest tests/integration/ -v
```

---

## Behaviour

- **Streaming responses**: the agent starts speaking after the first sentence is synthesised, not after the full response is ready
- **Barge-in**: speak while the agent is talking to interrupt it mid-sentence
- **Session memory**: conversation history is kept for the duration of the browser session; reloading starts fresh
- **Fully local**: STT, LLM, and TTS run on your machine with no external API calls

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: No module named 'src'` | Running from wrong directory | Run from project root: `python src/app.py` |
| "Connection refused" from LLM | Ollama not running | `ollama serve` |
| Microphone not working | Browser blocked mic | Browser site settings → allow mic for localhost |
| Agent not speaking | `say` / `afconvert` not found | Only macOS is supported for TTS |
| High STT latency | Large Whisper model on CPU | Set `WHISPER_MODEL=base.en` in `.env` |
| "No speech detected" | Too short or silent recording | Hold the fairy longer and speak clearly |
| Blank frontend page | Frontend not built | `cd frontend && npm run build` |

---

## Acknowledgements

- [Ollama](https://ollama.com) — local LLM runtime
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — efficient Whisper inference
- [FastAPI](https://fastapi.tiangolo.com) — async Python web framework
- [Vite](https://vitejs.dev) + [React](https://react.dev) — frontend tooling
- Apple Neural TTS (`say`) — fast, high-quality on-device speech synthesis
