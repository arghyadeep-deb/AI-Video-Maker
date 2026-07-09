# Research — edge-tts (Free Neural TTS)

**Source:** [github.com/rany2/edge-tts](https://github.com/rany2/edge-tts) · PyPI `edge-tts` · verified July 2026.

## What it is

Python library + CLI that calls the **online neural TTS service used by Microsoft Edge's read-aloud** — no API key, no Windows, no Edge required. ~322 voices across 74 languages, including multiple Hindi (`hi-IN-*`) and Indian English (`en-IN-*`) neural voices. Voices are the same Azure neural voices Microsoft sells — quality is genuinely high for both of our languages.

## The killer feature: word boundaries

The streaming API emits **WordBoundary events** (word text + audio offset + duration) alongside audio chunks. The bundled `SubMaker` converts these into SRT/VTT. This gives us **perfectly accurate subtitle timing for free, with zero speech recognition** — the script is the text, the TTS tells us exactly when each word is spoken. Note: recent versions default `SubMaker` to SentenceBoundary; we must explicitly request WordBoundary granularity for karaoke-style phrasing.

## Controls

`--rate`, `--pitch`, `--volume` accepted per request (e.g. `rate=-10%` for a calmer astrologer read). Output format: MP3 stream (24 kHz); convert to WAV via FFmpeg where SadTalker requires it.

## Risk: unofficial

edge-tts reverse-engineers an endpoint Microsoft doesn't officially offer for this. It has been stable for years and is very widely used, but Microsoft could break it.

**Fallback chain (all free):**
1. **Supertonic** ([github.com/supertone-inc/supertonic](https://github.com/supertone-inc/supertonic)) — MIT-licensed, 99 M-param ONNX TTS, real-time on plain CPU, Hindi + English covered; needs forced alignment (faster-whisper) to recover word timings. See [`07-voice-engine-alternatives.md`](./07-voice-engine-alternatives.md).
2. AI4Bharat Indic Parler-TTS — heavier local model, kept as second reserve.
3. gTTS — trivial, but robotic; last resort.

**Design consequence:** all TTS access goes through a `TTSEngine` interface returning `(audio_file, word_timings[])`, so the backend can swap without touching the pipeline ([`03-design/06-subtitle-timing.md`](../03-design/06-subtitle-timing.md)).

## Voice inventory task

Task-05 must run `edge-tts --list-voices`, confirm the four voices in [`01-requirements/06-languages`](../01-requirements/06-languages-hindi-english.md), and pin them in config.
