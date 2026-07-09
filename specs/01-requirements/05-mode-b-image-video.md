# Mode B — Visual Video with Subtitles

**Question.** What exactly is the "visuals of related topics with script + subtitles" mode?

**Decision.** A scene-driven film: each script scene gets a topic-relevant visual, narrated in the user's voice, with word-timed subtitles burned in, assembled by FFmpeg. The user picks a **visual quality level** at generation time:

| Level | Visuals per scene | Compute | Wait |
|-------|-------------------|---------|------|
| **Photo (fast)** | Stock/AI image + Ken Burns motion + crossfades | VM CPU only | ~2 min |
| **Generated footage ("proper AI video")** | A real **AI-generated video clip** (~5 s, image→video: the scene's image animated by Wan 2.2 5B / LTX-Video on the owner's 5070 Ti) | GPU worker | ~20–60 min for a 60 s video — queued, user notified |

Generated footage is only offered while the GPU worker is online; a mid-render worker loss falls back to Ken Burns for the remaining scenes (honest note in the result). Image→video (not text→video) is deliberate: the stock/styled image anchors each scene's content, and the model adds camera+subject motion — better coherence, cheaper, and scene swaps still work.

## Inputs

Accepted script — narrated in **the user's enrolled voice by default** ([`11-personal-voice.md`](./11-personal-voice.md); HD/persona/stock as alternatives) — plus optional background music (mood-picked, auto-ducked) and subtitle style (phrase / karaoke). No uploads. This is the zero-friction mode and the quality flagship (free stack produces genuinely good results here). After render, any scene's image can be swapped from a candidate picker and single scenes re-rendered ([`01-core-flow-and-modes.md`](./01-core-flow-and-modes.md)).

## Image sourcing (locked order)

1. **Pexels API** search using the scene's English `visual_hint` (see [`02-script-generation.md`](./02-script-generation.md)).
2. **Pixabay API** if Pexels returns nothing usable.
3. **Gemini Flash Image generation** as last resort (counts against the ~500/day free image quota, so stock-first).

Rules: landscape/portrait orientation must match the chosen video format; minimum resolution 1080 px on the short edge; no duplicate image across scenes in one video.

**Attribution (resolved, was open decision #8)**: file metadata only, no visible end-card — photographer/source recorded in each scene's `media_assets.meta_json` and written into `credits.txt`, bundled in every download alongside the video (task-08/task-09).

## Presentation (locked)

- **Photo level**: Ken Burns (slow zoom/pan) on every image — a static slideshow reads as cheap; motion reads as produced.
- **Generated-footage level**: every scene's image becomes a real motion clip; scene duration beyond the clip's ~5 s is bridged by a slow hold/loop tail so audio always rules the timeline.
- Crossfade between scenes (~0.5 s).
- Image switches align to scene boundaries in the audio timeline.

## Subtitles (locked)

- Generated from the script text (source of truth) timed with **word-boundary events from edge-tts** — no speech recognition needed, perfectly accurate by construction.
- Same language as audio; rendered with Noto Sans (Devanagari/Latin — free fonts, full script support).
- Burned into the video (universal playback); styled as reels-standard bottom-center, 2 lines max, current phrase highlighted.
- **Default style (resolved, was open decision #3)**: phrase-at-a-time. Word-by-word karaoke also ships as a user-facing toggle (task-16); phrase stays the default in both modes.

## Output

MP4 (H.264 + AAC), user-chosen format: **9:16** (default — reels/shorts) or **16:9**.

Design: [`03-design/05-mode-b-pipeline.md`](../03-design/05-mode-b-pipeline.md), [`03-design/06-subtitle-timing.md`](../03-design/06-subtitle-timing.md).
