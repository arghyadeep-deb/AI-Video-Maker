# AI Video Maker

Topic in → AI script (Hindi/English) → your review → video narrated in your
own voice. Zero-cost stack, invite-only. Full plan: [`specs/`](./specs/README.md).

## Setup (5 minutes)

### 1. Get the three free API keys

| Key | Where | Notes |
|-----|-------|-------|
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Sign in with any Google account, click "Create API key". No card. |
| `PEXELS_API_KEY` | [pexels.com/api/new](https://www.pexels.com/api/new/) | Sign up, request a key, it's issued instantly. |
| `PIXABAY_API_KEY` | [pixabay.com/api/docs](https://pixabay.com/api/docs/) | Sign up, your key is on your account page. Optional but recommended. |

Copy `.env.example` to `.env` at the repo root and paste your keys in:

```
cp .env.example .env
```

### 2. Run the two servers

**Backend** (FastAPI, needs Python 3.11+):

```
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt        # macOS/Linux
.venv\Scripts\uvicorn app.main:app --reload         # Windows
# .venv/bin/uvicorn app.main:app --reload           # macOS/Linux
```

Runs at http://localhost:8000. Applies SQLite migrations automatically on
first boot (`media/app.db`).

**Frontend** (Next.js, needs Node 20+):

```
cd frontend
npm install
npm run dev
```

Runs at http://localhost:3000 and shows the environment-doctor checklist —
green means that piece of the free stack is ready.

### 3. ffmpeg

Install ffmpeg and make sure it's on `PATH` (`ffmpeg -version`). The health
check on the frontend's home page tells you honestly if it's missing —
media pipelines (from task-06 onward) need it.

## Repo layout

- `backend/` — FastAPI + SQLite + media pipelines
- `frontend/` — Next.js UI
- `media/` — gitignored per-user data root (created on first backend boot)
- `specs/` — the complete build plan; **start at [`specs/AGENT-PLAYBOOK.md`](./specs/AGENT-PLAYBOOK.md)** if you're picking up development
