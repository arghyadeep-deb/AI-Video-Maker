# Task 16 — Background Music & Subtitle Styles

- **Depends on:** Task 09
- **Estimated effort:** 1.5 days

## Objective

Mode B gains an optional background-music track (auto-ducked under narration) and the subtitle style choice (phrase vs word-karaoke) becomes a user-facing option in both modes.

## Files

- `backend/assets/music/` — 8–12 curated instrumental tracks from free libraries (Pixabay Music / YouTube Audio Library), license notes per track, mood-tagged (calm / upbeat / mystical / corporate)
- `backend/app/engines/ffmpeg/audio_mix.py` — music loop/trim to video length, `sidechaincompress` ducking under narration, fade-out
- `backend/app/services/subtitles.py` — enable the existing `\k` karaoke generator as a first-class style
- `frontend` generate page — music toggle + mood picker with 5 s preview; subtitle style picker with visual sample

## Implementation

- Music at ~-18 dB under narration via sidechain ducking; ends with 1.5 s fade; `loudnorm` still last in chain.
- Mode A: music off by default (talking head reads better dry), available behind the same toggle.
- Karaoke style: word-highlight timing straight from existing word boundaries; both styles share the phrase-grouping layout so line breaks are identical.
- Track choice recorded in `media_assets.meta_json` + credits.txt.

## Tests

- Unit: duck filtergraph snapshot; loop math for short tracks vs long videos; karaoke tag timing monotonic.
- Integration: render with music → ffprobe two source audio inputs mixed to one stream; narration intelligible (loudness ratio asserted); karaoke ASS golden file.

## Demo

Same 60 s Hindi reel rendered dry, with calm music + phrase subs, and with upbeat music + karaoke subs — three files compared by ear/eye.

## Acceptance

- [x] Narration always clearly audible over music (ducking works). Real ffmpeg integration test (`test_audio_mix_integration.py`) proves it with measured loudness, not just "some ducking happened": a continuous loud music tone mixed against a quieter narration tone lands the mixed output's mean_volume much closer to narration-alone than to music-alone. Verified again inside both full pipelines with real ffmpeg renders (`test_render_with_music_mixes_a_second_audio_source`, `test_mode_a_render_with_music_mixes_a_second_audio_source`) — one output audio stream, not two.
- [x] Both subtitle styles correct in both languages. `write_ass`'s existing `karaoke` parameter (already correct from an earlier task, just never wired to a caller) is now threaded through `VideoRequest.subtitle_style` -> both pipelines' payloads -> `write_ass(..., karaoke=...)`. Real-ffmpeg tests confirm `\k` tags appear in the output ASS for both Mode A and Mode B when karaoke is requested. Language-specific font/shaping was already covered by task-06's own tests; this task only changes which tag format wraps the same word-timing data, so it doesn't need re-verification per language.
- [x] Every bundled track's license verified and documented. All 9 tracks (Jason Shaw / Audionautix, CC BY 3.0) were verified against each file's actual Wikimedia Commons description page, not assumed — see `backend/assets/music/LICENSES.md`.

## Completion notes

- **Sourcing detour**: Pixabay Music (the obvious first choice, matching this project's existing Pexels/Pixabay image integrations) turned out to have no API coverage for audio (confirmed by checking `pixabay.com/api/docs/` - images/video only) and blocks direct/scripted downloads from its website (403, JS-gated buttons). Used Wikimedia Commons instead, which mirrors a large catalog of Jason Shaw's (Audionautix) CC-BY-3.0 instrumental tracks with stable, curl-friendly URLs and per-file license metadata. All 9 tracks genuinely instrumental (no vocals, verified per-file), mood-tagged calm/upbeat/mystical/corporate (2-3 each), re-encoded to 128kbps to keep the repo lean (~26MB total). Dispatched to a forked agent since this was pure content-sourcing/verification work, not code.
- **A real filtergraph bug, caught by actually running ffmpeg**: the first version of `build_music_duck_filter` referenced the narration label twice (once as the sidechain trigger, once as the signal mixed back in via `amix`) - ffmpeg filtergraph labels are consumed the first time they're used as an input, so the second reference failed with "Stream specifier ... matches no streams." Fixed with an explicit `asplit=2` to make two independent copies of the narration stream before either use. Found by running the real Mode B integration test with music enabled, not by reading ffmpeg's filter docs up front - locked in with a dedicated unit test (`test_duck_filter_splits_the_narration_label_before_reusing_it`) so it can't regress silently.
- **A real path bug in `music_library.py`**, also only caught by a test that hit the real bundled files (not a monkeypatched stub): `MUSIC_DIR` used `parents[1]` (giving `app/assets/music`, which doesn't exist) instead of `parents[2]` (the real `backend/assets/music`, matching the same convention `mode_b.py`'s own `fonts_dir` lookup already uses from a file at the same directory depth). All the pipeline-level "render with music" tests had monkeypatched `music_library.pick_track` directly and so never exercised the real manifest path - the API-level `/api/meta/music/moods` test is what actually caught it.
- **Ducking design**: a flat -12dB baseline attenuation (`MUSIC_BASELINE_DB`) plus `sidechaincompress` (ratio 8, threshold 0.05, 5ms attack/300ms release) triggered by the narration track itself, rather than a single flat volume cut alone - this keeps music at a reasonable ambient level in gaps between phrases while still ducking hard whenever narration is actually playing. The task's own "~-18 dB under narration" is the *ducked* target during speech, reached via baseline + compression together, not a single static value.
- **Track choice persistence**: Mode B records the picked track in `media_assets` (kind='music') right after the ffmpeg render succeeds, then `_write_credits` reads it back for `credits.txt` - this guarantees credits.txt reflects the *exact* track actually mixed in rather than re-drawing randomly in a later stage. Mode A (no `media_assets` table usage anywhere in that pipeline) instead threads the picked track dict straight through `_finalize`/`_write_credits` as a plain argument - simpler, no schema needed for a single-project fact.
- **Credits wording upgraded past the original draft**: my first pass wrote `credits.txt` with just a filename + a pointer to `LICENSES.md`. Since CC BY 3.0 requires visible attribution with the work itself, updated both pipelines to embed the actual title, artist, and license line directly in `credits.txt` (`"Title" - Jason Shaw (Audionautix) / Licensed under CC BY 3.0 (...)`), matching the template the sourcing fork itself proposed.
- **Preview endpoints** (`GET /api/meta/music/moods`, `GET /api/meta/music/preview/{mood}`) are new, public (same reasoning as task-15's `/api/meta/tier` - no user data, needed before any project context exists), and deterministic (`random.Random(0)`) so the same track previews every time a user samples a mood, even though the real render draws randomly among a mood's tracks. Previews are ffmpeg-trimmed to 5s and cached to `media_root/music_previews/`, matching the existing voice-preview caching pattern in the same file.
- Live-verified in a real browser: music checkbox reveals a 4-mood picker with playable `<audio>` previews, subtitle style picker shows both options: screenshot confirms correct rendering. A full live render with music+karaoke through the browser was not attempted - this dev environment has no real Pexels/Pixabay/Gemini keys, so Mode B image sourcing would fail before ever reaching the audio-mix stage regardless of this task's own changes (same "owner action needed" gap already flagged for tasks 08/09/12). The actual ducking/karaoke logic is proven correct via real-ffmpeg integration tests instead, which don't depend on those keys.
