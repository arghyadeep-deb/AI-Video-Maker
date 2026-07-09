# Mode B Pipeline — Image Video

Single job `render_mode_b`, five stages.

| Stage | % | What happens |
|-------|---|--------------|
| tts | 0–25 | Per-scene TTS calls (`TTSEngine.speak(scene.text, user's voice profile)`) → per-scene base speech + word timings from edge-tts, **then OpenVoice tone conversion per scene (VM CPU) → the user's own voice**. Per-scene (not whole-script) so scene boundaries in the audio timeline are exact by construction |
| images | 25–45 | For each scene: refresh stale `visual_hint`s (one batch LLM call) → `StockImages.find(hint, orientation)` → download best candidate → nano banana fallback if none. Cached per project |
| subtitles | 45–55 | Word timings (offset per scene by cumulative audio start) → phrase-grouped ASS + sidecar SRT ([`06-subtitle-timing.md`](./06-subtitle-timing.md)) |
| assemble | 55–95 | FFmpeg: per-scene Ken Burns clip (duration = scene audio length + half of each adjacent crossfade) → xfade chain → concat audio track → burn ASS → H.264 MP4 ([`02-research/06-ffmpeg-assembly.md`](../02-research/06-ffmpeg-assembly.md)) |
| finalize | 95–100 | loudnorm, faststart flag, write `credits.txt` (photographer attributions), move to `media/projects/<id>/output.mp4`, job done |

## Timing model (the backbone)

```
scene[i].audio_start = Σ duration(scene[0..i-1])
scene[i].clip = image[i] shown for duration(scene[i])
word_timing[w].absolute = scene.audio_start + w.offset
```

Everything — image switches, crossfade midpoints, subtitle cues — derives from per-scene audio durations. There is no drift possible because there is no second clock.

## Image QA pass

Before assembly, UI-free sanity checks: orientation matches format; short edge ≥1080 px (else upscale-crop); no duplicates. The first render does **not** show the user the images beforehand (keep flow simple); a bad image is fixed afterwards with the **swap-image picker + scene re-render** (task-17) — the 5 scored candidates are cached for exactly this.

## Performance

60 s / 1080p ≈ tens of seconds of FFmpeg on a laptop CPU; TTS+downloads a few seconds each. Whole job typically < 2 min — communicate stages honestly in the progress UI.

Diagram: [`05-flowcharts/05-mode-b-pipeline.mmd`](../05-flowcharts/05-mode-b-pipeline.mmd).
