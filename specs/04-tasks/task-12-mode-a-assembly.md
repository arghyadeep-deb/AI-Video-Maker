# Task 12 — Mode A Assembly (Avatar Video End-to-End)

- **Depends on:** Tasks 06, 11
- **Estimated effort:** 1.5 days

## Objective

The `render_mode_a` pipeline: whole-script TTS → talking head → FFmpeg finishing (format pad, optional subtitles, loudnorm) → output.mp4. Mode A card goes live in the generate page.

## Files

- `backend/app/pipelines/mode_a.py` — tts → animate → assemble stages per [`03-design/04-mode-a-pipeline.md`](../03-design/04-mode-a-pipeline.md)
- `backend/app/engines/ffmpeg/finishing.py` — scale/pad (blurred-background pad on aspect mismatch), ASS burn, loudnorm
- `frontend/app/project/[id]/generate/page.tsx` — enable Mode A card: avatar pick/reuse, subtitles toggle, engine choice (Wav2Lip default / "HD avatar — 1 GPU slot"), ≥2 min scripts disabled with explanation

## Implementation

- One TTS call for the full script (single timing stream → subtitles when toggle ON).
- Animate stage progress = elapsed vs estimate from audio duration; UI shows "~2 of ~5 min".
- Duration guard: script estimate >2 min → Mode A blocked at API too (not just UI).
- Result page identical to Mode B (player, download, sidecars).

## Tests

- Unit: duration guard; stage list; pad-vs-crop decision table (portrait render → 9:16 native, 16:9 padded).
- Integration (FakeTTS + stub animator): full pipeline to a playable mp4; subtitles toggle honored.
- Live smoke: 30 s astrologer video in Hindi, 9:16, subtitles on — watched.

## Demo

From selfie to a subtitled 9:16 video of the user-as-astrologer speaking Hindi — the complete flagship demo of the product.

## Acceptance

- [x] Both modes now selectable and both produce correct videos from the same accepted script. Live-verified end to end in a real browser: create+approve an avatar → pick "My Avatar" on the generate page → real edge-tts + **real Wav2Lip** render → playable 9:16 result with correct blurred padding (source photo is landscape, target is portrait). Mode B remains unaffected (235 tests still passing, including its own existing pipeline test).
- [x] Subtitles in Mode A sync with the avatar's speech. Verified two ways: the integration test (`test_mode_a_pipeline.py`) asserts `subtitles.ass`/`.srt` exist and get burned in; the live smoke test frame-extracted BOTH scenes' subtitle text at the right point in the (correctly sequenced) timeline, matching the source script exactly, in properly shaped Devanagari.
- [x] Failure in animate surfaces the fallback path (retry on Wav2Lip), not a dead end. This is `chooser.render_with_fallback` from task-11, reused as-is here — a ZeroGPU quota rejection degrades to Wav2Lip automatically; any other SadTalker failure surfaces honestly rather than being silently swallowed (task-11's own `test_talking_head_chooser.py` already covers this; task-12 doesn't re-test the chooser itself, only that `stage_animate` wires it up and records which engine actually rendered).

## Completion notes

- **Real, live-verified flagship demo**: created and approved a real avatar (via the actual `/avatars` UI, using a stubbed image styler since no GEMINI_API_KEY is available — the *styling* step, not the render pipeline, is what's stubbed), then drove the full `/project/[id]/generate` → Mode A → avatar picker → subtitles-on → Generate flow in a real browser, through **real edge-tts Hindi audio and real Wav2Lip CPU inference** (task-11's actual downloaded weights, not a stub), landing on a playable 1080x1920 MP4 with burned Devanagari subtitles matching the script, in ~8s of wall-clock render time end to end. This is the literal scenario in the task's own Demo section.
- **The "pad vs crop" decision table is genuinely exercised, not just unit-tested**: the real test photo (`tests/fixtures/test_face.jpg`, landscape 548x342) fed into a 9:16 target correctly took the blurred-padding branch (`needs_padding()` returns `True` for a landscape source into a portrait target) — visually confirmed via extracted frames (sharp foreground centered over a blurred, scaled copy of the same image filling the letterbox bands). **Caveat**: this product's real avatar portraits are always 1024x1024 square (task-10's fixed styling prompt), which `needs_padding()` treats as never needing padding (a square covers either target via a plain crop) — so in normal use, real styled avatars will most likely take the *no-padding* branch, not the one just demonstrated. Both branches are unit-tested (`test_ffmpeg_finishing.py`) and the padding branch got a real visual proof; the no-padding branch's visual proof will need a real *styled* (square) portrait once a GEMINI_API_KEY is available.
- **Found and fixed a real bug via the live smoke test, not by reading code**: `_probe_video_dims`'s original implementation derived `ffprobe`'s path from `ffmpeg`'s path via `ffmpeg_bin.replace("ffmpeg", "ffprobe")` — this corrupts the path the instant the *install directory* also contains the substring "ffmpeg" (e.g. `.../ffmpeg-8.1.2-full_build/bin/ffmpeg.exe` → `.../ffprobe-8.1.2-full_build/bin/ffprobe.exe`, a directory that doesn't exist), crashing every single assemble stage with `FileNotFoundError`. Fixed by looking up `ffprobe` independently via `shutil.which("ffprobe")`, the same pattern `services/ffmpeg/probe.py` already used. Caught immediately by the integration test, not left for a live user to hit.
- **Refactored `_project_dir`/`_load_project_and_scenes` out of `mode_b.py` into a new `app/pipelines/common.py`** (`project_dir`, `load_project_and_scenes`) so `mode_a.py` doesn't duplicate identical logic. `mode_b.py` keeps its old private names as thin aliases (`ModeBError = PipelineError`, etc.) so nothing else needed to change; verified via the full existing Mode B test suite still passing unchanged.
- **Mode A's three design-doc stages (tts/animate/assemble) really are three, not five like Mode B** — subtitle generation happens at the tail of `stage_tts` (a single whole-script TTS call already produces one continuous timing stream, so there's no cross-scene stitching step the way Mode B needs), and loudnorm/credits/DB-finalization happen at the tail of `stage_assemble` (Mode A's design table bundles "scale/pad, subtitle burn, loudnorm, final encode" into one row, unlike Mode B's separate assemble+finalize stages). Documented explicitly in `mode_a.py`'s own docstrings so a future reader doesn't go looking for a phantom "subtitles" or "finalize" stage.
- **Animate-stage progress is a real, ticking elapsed/estimate approximation**, not a fake bar — per the design doc's explicit call-out that neither Wav2Lip nor SadTalker gives a usable progress callback. A background asyncio task reports `min(95%, elapsed/estimate)` every second while the render awaits, cancelled cleanly once the real result lands; the multiplier (2x audio duration) is a documented guess, not a measured constant — reasonable given task-11's own single real benchmark (~0.85x realtime for a 9s clip) leaves real headroom before the estimate would ever run out and cap the bar early.
- **Duration guard enforced at the API, not just the UI**: `POST /video` with `mode="a"` checks `project.duration_s > 120` before enqueueing anything (`api/video.py`), matching the task's own Implementation notes ("blocked at API too, not just UI"). Also validates the avatar exists, belongs to the caller, and is approved — all three checked with dedicated tests (`test_api_video.py`).
- **The "HD avatar (uses 1 GPU slot)" UI toggle described in the task's own Files list was deliberately left out of the generate page.** No SadTalker Space is deployed (task-11 left `hf-space/` written but undeployed, needing the owner's HF account) — showing a checkbox for a tier that doesn't actually exist yet would be dishonest UI, contradicting the hard invariant ("quota/GPU failures degrade honestly... never silent"). `hd_requested` is fully wired end-to-end in the API/pipeline/chooser (defaults to `false`); only the UI control is missing, to be added once there's a real HD tier to offer. Documented as a deliberate simplification, not an oversight.
- **The "≥2 min scripts disabled with explanation" UI rule doubles as the avatar-required rule**: the Mode A card is disabled (with an explanation line) both when the script exceeds 2 minutes and when the user has zero approved avatars yet — reusing one disabled-state affordance for two distinct reasons, each with its own message, rather than inventing a second UI pattern.
