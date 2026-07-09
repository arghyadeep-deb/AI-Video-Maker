# Subtitle Timing Design

## Source of truth

The **script text** is what is spoken (TTS reads it verbatim), and **edge-tts WordBoundary events** say exactly when each word lands in the audio. Subtitles are therefore derived, never recognized — zero ASR, zero mismatch.

```
TTSEngine.speak(text, voice_profile) → (audio.mp3, [{word, offset_ms, duration_ms}, ...])
```

**Personal-voice note:** timings are captured from the edge-tts *base* audio; the OpenVoice tone-color conversion that follows is waveform-to-waveform and duration-preserving, so the timings remain valid for the converted audio (asserted in tests: converted duration within ±50 ms of base). VoxCPM HD voices regenerate speech instead, so their timings come from forced alignment (below).

## Phrase grouping algorithm

Raw word cues are too fast to read. Group into display phrases:

1. Split scene text into phrase candidates at punctuation (।, ।।, ., ,, ?, ! — Devanagari danda included) and conjunction gaps.
2. Merge/split so each phrase is **≤ 42 chars per line, ≤ 2 lines, ≥ 0.8 s on screen**.
3. Phrase start = first word's offset; end = last word's offset + duration (+120 ms hang).
4. Style (open decision #3 default): phrase-at-a-time display, current phrase in highlight color; word-level karaoke kept behind a config flag (ASS `\k` tags — timings already word-accurate, so it's free to enable later).

## ASS generation

- Template: Noto Sans (Devanagari/Latin per language) via `fontsdir`, bold, white with black outline + subtle shadow, bottom-center, `MarginV` ≈ 12% of height (safe above platform UI chrome).
- 9:16 gets larger font (mobile viewing) than 16:9.
- Sidecar `subtitles.srt` always exported next to the MP4 (re-upload platforms accept it).

## Mode A vs Mode B

Identical machinery. Mode B: per-scene timings offset by cumulative scene start. Mode A: one whole-script TTS call → single timing stream. The subtitle module takes `[(word, abs_start, abs_end)]` and doesn't know which mode called it.

## Fallback path

If a non-edge TTS path is active (Supertonic fallback, or VoxCPM cloned/designed voices), word timings come from **forced alignment** (faster-whisper on the generated audio with the known script text). Same output type; downstream unchanged. Alignment quality is good when the reference text is known.

## Verification (task-06 acceptance)

Render test strings in both languages; check: correct glyph shaping (matras, conjuncts, ligatures), no tofu boxes, phrase boundaries at natural pauses, timing within ±100 ms of audible word starts.
