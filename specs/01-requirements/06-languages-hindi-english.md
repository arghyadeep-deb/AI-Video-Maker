# Languages — Hindi, English

**Question.** How is multi-language handled across the pipeline?

**Decision.** Exactly two languages: **Hindi and English** (Bengali was dropped 2026-07 by owner decision — see [`06-risks-and-future/02-explicitly-out.md`](../06-risks-and-future/02-explicitly-out.md)). Language is a **single up-front choice** that every downstream stage reads; no stage ever translates.

## Where the choice applies

| Stage | Effect |
|-------|--------|
| Script generation | Written natively in the chosen language |
| Improve-selection | Rewrites stay in the same language |
| TTS narration | Language-matched neural voice |
| Avatar speech (Mode A) | Same TTS audio drives lip-sync |
| Subtitles | Same language, script text as source of truth |
| UI copy | English UI (localization explicitly out of scope) |

## Voice table (locked base voices, edge-tts)

The narration voice is **the user's own** ([`11-personal-voice.md`](./11-personal-voice.md)); these stock voices are the **prosody base** that OpenVoice converts into the user's timbre, and the explicit fallback when conversion is unavailable.

| Language | Female | Male |
|----------|--------|------|
| Hindi | `hi-IN-SwaraNeural` | `hi-IN-MadhurNeural` |
| English (Indian) | `en-IN-NeerjaNeural` | `en-IN-PrabhatNeural` |
| English (US, alternate accent) | `en-US-AriaNeural` | `en-US-GuyNeural` |

- Base picked automatically to match the user's register (M/F from enrollment sample; overridable). Voice IDs verified against a live `edge-tts --list-voices` at task-05 (all four locked IDs plus the two `en-US` IDs exist).
- English bases are Indian-accent by default to match the audience; `en-US` is exposed as an alternate accent choice — it was zero extra work (same edge-tts call, just a different voice ID), so open decision #6 is resolved as "yes."
- Engine analysis (OpenVoice, Supertonic, VoxCPM): [`02-research/07-voice-engine-alternatives.md`](../02-research/07-voice-engine-alternatives.md) — all behind the same `TTSEngine` interface.

## Script-specific rules

- Hindi in Devanagari — never romanized (TTS mispronounces romanized text).
- Hinglish code-switching in the description is fine as *input*; the generated script normalizes to the chosen language.
- Subtitle font stack: Noto Sans Devanagari / Noto Sans (bundled in repo — OFL license, free).
- LLM quality in Hindi is a selection criterion for the script model — Gemini Flash chosen partly for Indic-language strength ([`02-research/01-free-llm-gemini-flash.md`](../02-research/01-free-llm-gemini-flash.md)).
