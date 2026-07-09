# Personal Voice — Every Video Speaks as Its Creator

**Question.** Whose voice narrates the videos?

**Decision.** **The user's own.** Voice enrollment is part of onboarding: the user records themself once, we build a reusable voice profile, and **every render — Mode A and Mode B — is narrated in their voice by default.** Stock neural voices are a fallback/degradation path, never the default.

## Enrollment (once per user, before their first render)

1. After registration (or at first "Generate video"), the user is asked to **record ~30–45 s** in the browser (MediaRecorder): reading a provided passage in their chosen language, written to cover a wide phoneme/intonation range — this is the "complete voice understanding" sample.
2. Upload-a-file alternative for users who prefer it (same validation).
3. Validation: 15–60 s of detected speech, one speaker, acceptable noise floor; converted to mono 16 kHz.
4. **Logged consent record** (it must be their own voice) — same class as the selfie gate; task-19 machinery.
5. Tone-color embedding extracted once and stored; the profile appears in their Voices shelf. Re-record any time; delete any time (deletes sample + embedding).

## How it speaks (the two-stage pipeline — [`02-research/07-voice-engine-alternatives.md`](../02-research/07-voice-engine-alternatives.md))

| Stage | Engine | Where | Why |
|-------|--------|-------|-----|
| 1. Base speech + word timings | edge-tts (stock hi/en voice as prosody base) | free cloud | Natural prosody, and the **word timings that drive subtitles survive unchanged** |
| 2. Tone-color conversion → user's timbre | **OpenVoice V2** converter (MIT) | **VM CPU, ~3–5× real-time** | Every render can afford it — no GPU dependency |
| Optional "HD voice" | **VoxCPM** full generative cloning | ZeroGPU slot | Higher fidelity for special videos; spends a daily GPU slot |

Male/female stock-voice pick still exists — it selects the **prosody base** that gets converted (closest match to the user's register sounds best).

## Fallback rules (locked)

- Conversion failure or unvalidatable sample → render offers the stock voice **with an explicit notice**, never silently.
- "Skip for now" at enrollment exists (user can try the product) but the UI keeps steering to enrollment; the product's identity is *your* face and *your* voice.
- Designed personas ("elderly wise astrologer voice", VoxCPM text-to-voice) remain available as a deliberate choice **instead of** the personal voice for a given render.

## Language note

OpenVoice tone conversion is cross-lingual by design (reference language ≠ speech language is fine); native support is strongest for en/es/fr/zh/ja/ko — **Hindi conversion quality must be ear-tested in task-18 before launch** (risk R11).
