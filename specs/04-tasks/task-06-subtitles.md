# Task 06 — Subtitle Generation

- **Depends on:** Task 05
- **Estimated effort:** 1.5 days

## Objective

Word timings → phrase-grouped, styled ASS (burn-ready) + sidecar SRT, correct for Devanagari and Latin scripts.

## Files

- `backend/app/services/subtitles.py` — phrase grouping algorithm per [`03-design/06-subtitle-timing.md`](../03-design/06-subtitle-timing.md); ASS + SRT writers
- `backend/app/assets/subtitle_template.ass` — style templates for 9:16 and 16:9
- `backend/app/services/ffmpeg/probe.py` — libass/HarfBuzz capability probe (extends health check)

## Implementation

- Grouping: split at punctuation (incl. Devanagari danda ।), merge/split to ≤42 chars/line, ≤2 lines, ≥0.8 s; +120 ms hang.
- Input type `[(word, abs_start_ms, abs_end_ms)]` — mode-agnostic; offsetting per scene happens in callers.
- Fonts: bundled Noto via `fontsdir`; per-language font pick.
- Word-karaoke (`\k`) generation behind a config flag, off by default (open decision #3).

## Tests

- Unit: grouping properties (no phrase >2 lines, none <0.8 s, no overlaps, full coverage of words); danda splitting; SRT round-trip parse.
- Golden files: one scripted example per language → committed expected ASS.
- Render test: burn each language's ASS onto a color background via ffmpeg; visually verify shaping (conjuncts, matras) — no tofu.

## Demo

A 15-second Hindi audio + timings → burned test clip with correctly shaped (conjuncts, matras), readable, phrase-timed subtitles.

## Acceptance

- [x] Both scripts render with correct shaping in burned output. (installed ffmpeg with libass/HarfBuzz/freetype/fribidi via winget since this dev machine had none; live-burned real edge-tts output onto color backgrounds and visually inspected the frames myself — conjuncts (व्य, स्त), matras, nukta (ज़), candrabindu (पाँच) all shaped correctly, no tofu, for both Hindi and English)
- [x] Phrase timing feels natural against audio (spot-check three samples). (inspected the actual phrase boundaries from live edge-tts timings — see Completion notes; I have no audio playback so this is a text/timestamp read, not an ear check)
- [ ] SRT sidecar loads correctly in VLC — **needs the owner** (no VLC/media player available to me here); the format itself is round-trip-tested against the SRT block spec (`TestSrtRoundTrip`).

## Completion notes

- **Installed ffmpeg via `winget install Gyan.FFmpeg`** (free, OSS, zero-cost — exactly what `01-requirements/07-free-stack-lock.md` already locks in) since this dev machine had none, which was blocking any real verification of this task's core deliverable. It's now in the user-level PATH permanently (confirmed via the registry), so any new terminal/session picks it up automatically; only my own already-running tool session needed a manual PATH prefix for the rest of this session (a session-only quirk, not a codebase or environment issue).
- **Found and fixed a real, significant bug via live verification**: edge-tts's `WordBoundary` events **strip punctuation** from each word's `text` field. Confirmed by direct probe: source text "...दोस्तों, आज..." synthesizes fine, but the `WordBoundary` for that word comes back as `"दोस्तों"` with the comma silently gone. Since `group_into_phrases` splits on trailing punctuation, feeding it raw TTS word output directly would have made every phrase boundary invisible in production — despite all my hand-built unit-test fixtures (which had punctuation manually attached to `WordCue.word`) passing perfectly. **Added `realign_with_source_text()`** to `subtitles.py`, which re-attaches punctuation from the original (validated, task-02) script text by positional whitespace-token alignment — confirmed 1:1 reliable against real edge-tts output for a 20-word live sample. This is the function every future caller (Mode A/B pipelines, task-09/12) must use between `TTSEngine.speak()` and `group_into_phrases()`; calling `group_into_phrases()` directly on raw `WordTiming`s from an engine will silently lose punctuation-based splitting.
- **Comma is treated as a hard split candidate**, same as danda/period/?/!, per the design doc's literal list. In practice the min-duration merge pass glues back together any resulting too-short fragments, so this reads naturally rather than choppy (verified in the live Hindi/English samples: `"नमस्ते दोस्तों,"` stood alone since 1.3s already clears the 0.8s floor, while shorter comma fragments elsewhere would merge forward).
- **Line-wrapping is approximated by a combined char budget** (`42 chars/line × 2 lines = 84 chars` total), not actual line-break placement — real wrapping happens at render time via libass based on `PlayResX`/font size/`WrapStyle`. Verified indirectly: the live-burned frames show single-line, readable phrases well under the pixel width at both resolutions; a phrase that's exactly at the 84-char boundary hasn't been visually spot-checked for exactly-2-line wrapping.
- **Karaoke (`\k`) mode is implemented and unit-tested** (`karaoke=True` on `write_ass`) but not live-burned/visually verified — it's explicitly off by default (open decision #3) and not touched by any Acceptance box.
- **ffmpeg filter-graph path escaping on Windows was non-obvious**: `fontsdir=C:/Users/.../fonts` breaks ffmpeg's filtergraph parser (colon is a field separator) — needs the drive letter's colon escaped as `C\:/...`. Documented directly in `test_subtitle_burn.py` since it'll bite again the moment task-09/12 build the real burn pipeline on Windows dev machines (prod Linux VM paths have no drive-letter colon, so this is dev-machine-only).
