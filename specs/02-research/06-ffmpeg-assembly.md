# Research — FFmpeg Video Assembly

FFmpeg is the free bedrock that turns (images | talking-head clip) + audio + subtitles into the final MP4. No library gaps here — everything below is standard, verified capability.

## Mode B assembly recipe

1. **Per-scene clips with Ken Burns:** `zoompan` filter on each still (slow 1.0→1.08 zoom, alternating pan direction per scene), duration = scene's audio span, `fps=30`, scaled/cropped to 1080×1920 (9:16) or 1920×1080 (16:9).
2. **Concatenate with crossfades:** `xfade=transition=fade:duration=0.5` chain between scene clips.
3. **Audio:** narration MP3 → AAC; `-shortest` guard for rounding drift.
4. **Subtitles:** ASS file burned via `subtitles=` filter (see below).
5. **Encode:** `libx264 -crf 20 -preset medium -pix_fmt yuv420p` + AAC 128k → universally playable MP4.

## Mode A assembly recipe

SadTalker/Wav2Lip already output a talking-head video with audio. FFmpeg pass: scale/pad to target format (blurred-background pad if portrait output on 16:9 canvas), burn optional subtitles, normalize loudness (`loudnorm`), final H.264 encode.

## Subtitles: ASS over SRT

- ASS (`libass`) supports positioning, outline, background box, per-phrase styling, and **font selection** — needed for reels-style look.
- Devanagari rendering requires libass with HarfBuzz shaping (standard in modern FFmpeg builds — verify in task-01 env check) + bundled Noto fonts via `fontsdir`.
- We generate ASS directly from word timings ([`03-design/06-subtitle-timing.md`](../03-design/06-subtitle-timing.md)); SRT also exported as a sidecar file.

## Orchestration from Python

Build filtergraphs with plain `subprocess` + a small typed command builder (own the strings; easier to debug than MoviePy's abstraction and much faster — MoviePy renders frame-by-frame through Python). Parse `-progress pipe:1` output to report render % to the job system.

## Performance expectation

Mode B 60 s / 1080p renders in well under a minute on a typical laptop CPU. Mode A cost is dominated by the talking-head model, not FFmpeg.
