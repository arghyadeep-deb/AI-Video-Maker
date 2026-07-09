# Free Stack — Locked Choices

**Question.** Which concrete free components implement each capability?

**Decision.** The table below is locked. Substitutions require consulting the fallback column and updating this file first.

| Capability | Locked choice | Free basis | Fallback (also free) |
|-----------|---------------|------------|----------------------|
| Script LLM + improvements | **Gemini Flash** (latest free-tier Flash model) | Free tier ~1,500 req/day, no card | Groq (Llama 3.3 70B free tier); OpenRouter free models |
| Avatar styling (selfie → persona portrait) | **Gemini 2.5 Flash Image** ("nano banana") | Free tier ~500 images/day | Local Stable Diffusion + InstantID (needs GPU) |
| TTS base (hi/en) + word timings | **edge-tts** (Python, unofficial MS Edge voices) | Unmetered, no key | Supertonic (local ONNX, CPU, MIT) — see [`02-research/07`](../02-research/07-voice-engine-alternatives.md) |
| **Personal voice (every render)** | **OpenVoice V2** tone conversion (MIT) | VM CPU, ~3–5× real-time | Stock voices with explicit notice |
| HD voice / designed personas | **VoxCPM** on ZeroGPU (Apache-2.0) | GPU-slot budget | Standard converted voice |
| Subtitle timing | **edge-tts WordBoundary events** | Comes free with TTS | faster-whisper alignment (local, OSS) |
| Talking head | **Wav2Lip** (VM CPU, default) + **SadTalker** (ZeroGPU slots) | OSS + free GPU minutes | Admin Colab escape hatch |
| Background music | Bundled free-library tracks + FFmpeg ducking | Pixabay Music / YT Audio Library | Music off |
| Stock images | **Pexels API** | Free key, 200 req/hr | Pixabay API; then nano banana generation |
| Video assembly | **FFmpeg** (+ Python orchestration) | OSS | — (FFmpeg is the bedrock) |
| Frontend | **Next.js** | OSS | — |
| Backend | **FastAPI** (Python) | OSS | — |
| DB / storage | **SQLite** + local filesystem | OSS | — |
| Job processing | In-process async worker + SQLite job table | OSS | — |

## Why Python backend is non-negotiable

edge-tts, SadTalker, Wav2Lip, and the FFmpeg orchestration ecosystem are all Python. A Node backend would need to shell out to Python for every media step; FastAPI keeps one process family.

## Keys required at setup (all free, no card)

1. `GEMINI_API_KEY` — Google AI Studio.
2. `PEXELS_API_KEY` — pexels.com/api.
3. `PIXABAY_API_KEY` — pixabay.com/api/docs (optional but recommended).

Setup docs must walk through obtaining all three in <5 minutes.
