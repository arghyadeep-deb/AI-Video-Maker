# Mode A — Personal AI Avatar

**Question.** How does "an AI avatar of himself that looks like an astrologer" work, for free?

**Decision.** Two-stage: **(1)** selfie + persona description → styled still portrait via Gemini Flash Image (free tier), with an explicit user-approval gate; **(2)** approved portrait + TTS audio → talking-head video via open-source animation — **Wav2Lip on the server CPU by default, SadTalker on ZeroGPU as the GPU-slot "HD" option**.

## Inputs

| Input | Required | Notes |
|-------|----------|-------|
| Accepted script | Yes | From the review loop |
| Selfie | Yes | Single clear front-facing photo; JPEG/PNG upload with preview |
| Persona description | Yes | Free text ("astrologer in saffron robes, mystical background") + quick-pick presets: Astrologer, Businessman, Teacher, Doctor, News Anchor |
| Voice | Yes | **The user's enrolled voice by default** ([`11-personal-voice.md`](./11-personal-voice.md)) — your face *and* your voice; HD / designed persona / stock as alternatives |
| Subtitles | Optional | Toggle, default ON |

## The approval gate (locked)

The styled portrait is shown to the user **before** any animation starts. User can regenerate with a tweaked persona description or approve. Rationale: animation is the slowest, most compute-expensive step — never spend it on a portrait the user hates. Approved portraits are saved and **reusable across future videos** without regeneration.

## Portrait rules

- The portrait must keep the user's facial identity (it should look like *them* as an astrologer, not a generic astrologer).
- Output: single front-facing, neutral-to-mild-expression portrait, 1024×1024 — the framing SadTalker animates best.

## Consent rule (locked)

Upload screen states the selfie must be of the user themself; a mandatory affirmation is stored as a **logged consent record** (this is a public site). Selfies and portraits live in the user's private server storage, sent only to the Gemini image API for styling, deletable any time. Full public-safety measures (moderation, impersonation guards, reporting) are task-19; risk analysis: [`06-risks-and-future/01-risks.md`](../06-risks-and-future/01-risks.md) R4.

Design: [`03-design/04-mode-a-pipeline.md`](../03-design/04-mode-a-pipeline.md). Model research: [`02-research/03-talking-head-models.md`](../02-research/03-talking-head-models.md), [`02-research/04-free-image-generation.md`](../02-research/04-free-image-generation.md).
