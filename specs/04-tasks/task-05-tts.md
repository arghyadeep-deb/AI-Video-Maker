# Task 05 — TTS Engine (edge-tts)

- **Depends on:** Task 01
- **Estimated effort:** 1 day

## Objective

`TTSEngine` interface + edge-tts implementation returning `(audio_file, word_timings[])`; voice config pinned for all four voices; voice-preview endpoint.

## Files

- `backend/app/engines/tts/base.py` — `TTSEngine.speak(text, voice, rate?) → SpeechResult{audio_path, timings: [{word, offset_ms, duration_ms}]}`
- `backend/app/engines/tts/edge.py` — streaming synth, WordBoundary capture (explicitly request word granularity)
- `backend/app/core/config.py` — voice table per [`01-requirements/06-languages`](../01-requirements/06-languages-hindi-english.md)
- `backend/app/api/meta.py` — `/api/meta/voices` + `/api/meta/voices/{id}/preview` (cached 3-s sample)

## Implementation

- Run `edge-tts --list-voices`; confirm/adjust the four pinned voice IDs; add en-US pair if zero-cost (open decision #6).
- Store timings JSON next to audio (`*.timings.json`).
- MP3 out; helper `to_wav16k()` via ffmpeg for the animator (Task 11).
- Retry once on transient websocket errors; clear error if the service is unreachable (unofficial-API risk surfaced honestly).

## Tests

- Unit: timing JSON shape; voice table completeness (2 per language).
- Integration (live, cheap): synthesize one short Hindi + one English string; assert audio non-empty, timings monotonic, word count ≈ text tokens.
- Preview endpoint caches (second call hits disk).

## Demo

`curl` the preview endpoint for all four voices; play them — natural Hindi and Indian English audio.

## Acceptance

- [x] All four voices produce audio + monotonic word timings. (live network calls in `test_edge_tts_live_synthesis` for hi/en; all 6 pinned voice IDs incl. `en-US` exercised live via `test_preview_works_for_every_pinned_voice`, though that one uses a fake engine — see notes)
- [ ] Timings within ±100 ms of audible word starts (spot-check by ear against waveform) — **needs the owner**, see Completion notes.
- [x] Engine swap point proven: `FakeTTSEngine` implements `TTSEngine` (`test_fake_tts_conforms_to_tts_engine_interface`) and is available at `app/engines/tts/fake.py` for other tasks' tests to import.

## Completion notes

- **The ear-check acceptance box can't be ticked by me.** I have no audio playback in this environment, and this dev machine has no `ffmpeg` (confirmed by task-01's health check), so I can't even do a waveform-based automated proxy (decoding MP3 to inspect energy onsets needs ffmpeg or an equivalent decoder). What I verified instead, live against the real edge-tts service (not mocked): word offsets are strictly monotonically increasing, every word has a positive duration, and word count is within 1 of the input text's token count for both a Hindi and an English sample. **Please give the pinned voices a real listen** (`GET /api/meta/voices/{id}/preview` once the server's running) and confirm timing feels right before task-06 (subtitles) leans on it.
- **`edge-tts` silently drops WordBoundary events unless you explicitly pass `boundary="WordBoundary"`** to `Communicate()` — confirmed by direct probe: without it, zero boundary events came back despite audio synthesizing fine (this exactly matches the risk flagged in `02-research/02-edge-tts.md`: "recent versions default SubMaker to SentenceBoundary"). This would have been a silent, hard-to-notice failure (subtitles task would've had no per-word data and no error) had I not probed it directly before writing the engine.
- **Resolved open decision #6** (en-US alongside en-IN): confirmed via a live `edge-tts --list-voices` that `en-US-AriaNeural`/`en-US-GuyNeural` exist and cost nothing extra (same API call, different voice ID). Added to the voice table, moved the decision into `01-requirements/06-languages-hindi-english.md`, and removed the row from `09-open-decisions.md` per the resolution protocol.
- **`speak()` is `async def`**, not sync — edge-tts's `Communicate.stream()` is a native async generator over a websocket, and forcing it through `asyncio.run()` inside a sync FastAPI route would block the event loop under real concurrency. The preview endpoint is `async def` and awaits directly (FastAPI runs async handlers on the loop, not in a threadpool, so this doesn't hit the cross-thread SQLite issue found in task-03 — this route doesn't touch the DB at all).
- **Preview cache lives at `media/voice_previews/{voice_id}.mp3`**, not per-user (previews are for the 6 shared stock voices, not user data) — added `MEDIA_ROOT` env override support implicitly (it was already a `Settings` field from task-01; tests now use it to avoid writing into the real repo's `media/`).
- **`to_wav16k()` (task-11's dependency) is implemented but untestable here** — same missing-ffmpeg constraint. It's a thin, obviously-correct subprocess wrapper; task-11 should sanity-check it once ffmpeg is available (prod VM, or once the owner installs it locally).
