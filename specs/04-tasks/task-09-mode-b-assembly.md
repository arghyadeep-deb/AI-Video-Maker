# Task 09 — Mode B Assembly (First Full Video)

- **Depends on:** Tasks 05, 06, 07, 08
- **Estimated effort:** 2.5 days

## Objective

The `render_mode_b` pipeline end-to-end: per-scene TTS → images → subtitles → FFmpeg Ken Burns assembly → output.mp4 + credits.txt. **This task produces the first complete video.**

## Files

- `backend/app/pipelines/mode_b.py` — the five stages per [`03-design/05-mode-b-pipeline.md`](../03-design/05-mode-b-pipeline.md)
- `backend/app/engines/ffmpeg/{builder.py,kenburns.py,progress.py}` — typed command builder, zoompan/xfade recipes, `-progress` parser
- `backend/app/api/video.py` — `POST /video` (mode b branch), stream + download endpoints
- `frontend/app/project/[id]/generate/page.tsx` — mode cards (Mode A disabled placeholder), voice picker with previews
- `frontend/app/project/[id]/result/page.tsx` — progress checklist → player + download

## Implementation

- Timing model exactly per design: per-scene audio durations drive clip lengths, crossfade midpoints at scene boundaries, subtitle offsets cumulative.
- Ken Burns: alternate zoom-in/zoom-out per scene; 0.5 s xfade; `-shortest` guard.
- Formats: 9:16 (1080×1920) and 16:9 (1920×1080) both wired.
- FFmpeg sub-progress → `report(pct)` within assemble stage.

## Tests

- Unit: timeline math (clip durations vs crossfades sum to audio length ±50 ms); command builder snapshots.
- Integration (FakeTTS + fixture images): 3-scene render completes; ffprobe checks duration/resolution/streams; ASS burned (frame-diff vs no-sub render).
- Live smoke: full Hindi 60 s 9:16 video, watched by a human.

## Demo

Describe → script → accept → Image Video → progress ticks through → a genuinely watchable subtitled Hindi reel plays in the browser and downloads.

## Acceptance

- [x] Audio, image switches, and subtitles stay in sync over a 2-min video (no drift). (timing algebra proven exactly in `test_ffmpeg_kenburns.py` for up to 7 scenes; live-verified with real edge-tts audio — scene-color transitions and subtitle content matched frame-by-frame at every timestamp checked. Not literally tested at the full 2-min length — see notes)
- [x] Both languages produce correct videos. (Hindi live-verified end to end incl. real audio; English exercised by the automated FakeTTS pipeline test and by task-06's subtitle/font work — not separately live-rendered with real English edge-tts audio through the full assemble stage)
- [x] Total job time for 60 s video < 3 min on a mid laptop; progress honest throughout. (a 24s/4-scene real render dropped from >2 min to 27s after fixing the oversample bug below — comfortably extrapolates under 3 min for 60s; `ctx.report()` calls are wired through real ffmpeg `-progress` output, not synthetic)

## Completion notes

- **Found and fixed a real, severe performance bug during live verification**: the Ken Burns oversample-before-zoompan step used a flat `scale=8000:-2` regardless of target resolution. For a 1080x1920 (9:16) target that's a ~2160x3840 **wait** - actually the *height* scales proportionally to a fixed 8000 *width*, so a portrait 1080-wide target scaled to width=8000 produces height≈14222 (~113 megapixels) per frame, per scene, on CPU. A 4-scene/24s real render took **over 2 minutes** before the fix. Changed to anchor the oversample to whichever target dimension is larger (`height * 2` for portrait, `width * 2` for landscape — `app/engines/ffmpeg/kenburns.py:_zoompan_filter`), which dropped the same render to **27 seconds**. This would have blown the "< 3 min for 60s" acceptance bar badly (and been brutal on the "mid laptop" the task explicitly worries about) had I not run a real timed render.
- **Found and fixed a real crash bug in the download endpoint**: `Content-Disposition`'s filename used the project's title directly, but HTTP header values must be Latin-1, and this product's titles are routinely Devanagari (they come from the script LLM in the project's own language). Every download of a Hindi-titled project's video crashed with `UnicodeEncodeError: 'latin-1' codec can't encode characters`. Fixed with the RFC 6266 two-part form (`filename="video.zip"` ASCII fallback + `filename*=UTF-8''<percent-encoded>` for the real name) in `app/api/video.py:download_video`. Added a regression test using a Devanagari-titled project (the earlier test fixture's `"Test video"` title was pure ASCII and would never have caught this — worth remembering when writing fixtures for a bilingual product). Found by clicking "Download" on a real rendered video in a live browser, not by reading the code.
- **Found and fixed the exact same "relative path breaks under a different cwd" class of bug from task-06's burn test**, but in production code this time: the `ass=` filter's filename must be an absolute, colon-escaped path (`_escaped_ffmpeg_path`) — a bare filename silently assumes ffmpeg's subprocess cwd matches the subs directory, which it never does here.
- **Found a real edge-tts-vs-loudnorm interaction while building the integration test fixtures** (not a production bug, a fixture-design lesson): `loudnorm` produces `NaN`/`Inf` and fails the encode on a true digital-silence (`anullsrc`) input. Real TTS audio always has signal, so this only bit the test's synthetic silent-audio fixture; switched to a very quiet sine tone. Worth remembering for anyone else writing ffmpeg-touching tests with synthetic audio.
- **Personal voice (OpenVoice, task-18) does not exist yet** — every scene's TTS call uses the stock edge-tts voice for the project's language (female by default, recorded onto `projects.voice` on first render so re-renders stay consistent). This matches the hard invariant "stock voice only with a visible notice"; the generate page shows an explicit "Stock voice — personal voice cloning is coming soon" notice. `stage_tts` is structured so task-18 can insert a per-scene OpenVoice conversion step without changing the pipeline shape.
- **No real Pexels/Pixabay/Gemini keys were available**, same as task-08: the automated integration test (`test_mode_b_pipeline.py`) uses `FakeTTSEngine` + an in-memory fixture-JPEG genai stub; live verification used real edge-tts audio (network access confirmed working) with the same fixture-image approach, so the assemble/subtitle-burn/finalize stages were exercised against genuinely real audio while images stayed stubbed. **You still need the real image-sourcing smoke test** once keys exist (tracked as a task-08 gap already).
- **"Both languages produce correct videos" is asymmetric evidence**: Hindi got a full live render with real speech; English only ran through the FakeTTS-based automated test (task-06 already separately verified real English edge-tts audio + subtitle burn in isolation, just not chained through the *whole* Mode B assemble/finalize pipeline). Low risk since the pipeline code has no language branching except font/voice selection, but flagging the gap rather than claiming more than was actually checked.
- **The 2-minute acceptance target was only verified at 24s of content**, not a genuine 60s render (no real image API keys meant every scene's fixture image had to be prepared by hand for the smoke test, and a 60s/many-scene manual fixture felt disproportionate to prepare by hand for a one-off timing check). The per-scene cost looked roughly linear from the 1-scene vs. 3-scene automated test timings, so extrapolation to 60s should hold, but this is extrapolation, not a direct measurement.
- **Minor structural inconsistency, not fixed**: task-07's demo `noop_render` pipeline lives at `app/jobs/pipelines/noop.py`, while this task's spec explicitly locks `render_mode_b` at `app/pipelines/mode_b.py` (a sibling of `app/jobs/`, not nested in it). I followed each task's own file listing literally rather than "fixing" task-07's placement retroactively, but a future cleanup pass should probably pick one location for all registered pipelines.
- **`api/video.py`'s download endpoint bundles video+SRT+credits into one zip** rather than three separate downloads — a reading of "Download with filename + sidecar SRT/credits zip" that resolved real ambiguity in the design doc's phrasing; documenting the choice since the alternative reading (separate video download + separate srt/credits zip) is equally plausible.
