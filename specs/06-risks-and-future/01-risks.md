# Risks

Ordered by (likelihood × impact). Every risk has a free mitigation — the zero-cost constraint forbids "pay to fix".

## R1 — edge-tts breaks (unofficial API) — HIGH likelihood over product lifetime
Microsoft can change/close the endpoint any day. **Mitigation:** `TTSEngine` interface already isolates it; fallback = **Supertonic** (MIT, CPU-only ONNX, hi+en) + faster-whisper forced alignment for timings (both OSS); Parler-TTS as second reserve. Cost of switch: one engine file. See [`02-research/07-voice-engine-alternatives.md`](../02-research/07-voice-engine-alternatives.md). Watch: `rany2/edge-tts` issues.

## R2 — Free-tier terms change (Gemini text/image) — **TRIGGERED for image, 2026-07-11**
Google has already moved Pro models off the free tier; Flash could follow or quotas shrink. **Mitigation:** model IDs and quotas are config; Groq/OpenRouter fallback for text. Image styling has no equally good free fallback — if nano banana goes paid, Mode A styling degrades to local SD+InstantID (GPU owners) or persona presets without selfie styling. Documented as an accepted product risk.

**Status update (2026-07-11, verified live):** the image half fired. `gemini-2.5-flash-image` returns 429 with `limit: 0` on the free tier (Google shut the free image-preview model on 2026-01-15; current image models are API-paid-only — free image generation survives only in the Gemini *app*). Text (`gemini-flash-latest`) remains free and was live-verified the same day. Consequences applied:
- **Mode B image chain**: unaffected in practice — stock-first (Pexels→Pixabay both live-verified); the genai third leg simply never fires (task-15's quota guard already degrades to stock-only honestly).
- **Mode A styling**: `avatar_styling` now degrades honestly — on `ImageStylerUnavailableError` the RAW selfie is offered as the portrait at the existing approval gate, reason recorded in `jobs.engine_notes` (this is the "persona presets without selfie styling" floor).
- **The wired fallback proper** — local styling on the owner's 5070 Ti (SD/SDXL+InstantID class, a new `styler` capability behind the existing `ImageStyler` interface; the task-20a worker infrastructure it needs now exists) — queued as follow-up work.
- **Text fallback chain: implemented and live-verified same day.** `ScriptLLM` now tries Gemini (key pool) → Groq → OpenRouter (`make_script_llm`); fires on quota AND availability failures; the user-facing error stays the honest Gemini one if every provider fails. Groq verified live (clean Devanagari from `llama-3.3-70b-versatile`); OpenRouter key verified live (`:free` models rate-limit per-model upstream — acceptable for a third-string fallback; model id is config). Fallback output still passes through the script validation gate, so a weaker model degrades to an honest validation error, never silent garbage.

## R3 — GPU capacity is intermittent — MEDIUM (was HIGH before the home worker)
Primary GPU is the owner's RTX 5070 Ti, online only when the PC is on; overflow is a few ZeroGPU minutes daily. **Mitigation (shipped, not theoretical):** three-tier routing (home worker → ZeroGPU → CPU) with lease/heartbeat re-queue, dynamic slot limits, and truthful UI state ("HD available / limited today"); Wav2Lip + OpenVoice CPU paths mean every feature has a zero-GPU floor. Mode B is 100% CPU-safe and is deliberately the default-highlighted mode.

## R12 — Blackwell (RTX 5070 Ti) vs 2023-era research code — MEDIUM
sm_120 needs PyTorch built for CUDA 12.8+; SadTalker/Wav2Lip pin ancient deps and may need patches. **Mitigation:** dependency surgery is explicitly budgeted in task-20a with pinned working versions documented; ZeroGPU Space (maintained runtimes) is the tested fallback for anything that won't run locally.

## R4 — Deepfake/likeness misuse — LOW at current scale (1–2 known users)
The site is invite-only for people the owner knows, so the stranger-abuse surface is gone. What ships (task-19): logged consent records per likeness artifact, persona-prompt impersonation guard, AI-generated metadata tag in outputs, delete-everything controls. **Hard rule recorded:** if the site is ever opened beyond 1–2 users, the full public-safety package (text moderation gates, reports/takedown, abuse throttles) becomes a launch prerequisite — reopening this risk at HIGH.

## R5 — Talking-head licenses are research/non-commercial — MEDIUM
Fine for a free personal tool; **blocks commercialization**. Re-audit licenses (SadTalker, Wav2Lip weights!) before any monetization; MuseTalk/newer permissive models may unblock.

## R6 — Fallback TTS quality untested for Hindi — MEDIUM
If R1 fires, Supertonic becomes the voice of the product, and its 99 M-param Hindi naturalness is unverified (small model, may lag Azure voices noticeably). **Mitigation:** ear-test Supertonic Hindi during task-05 (one afternoon) so the fallback's real quality is known *before* it's ever needed; Parler-TTS stays as the heavier second reserve.

## R7 — Stock images misfire for abstract scenes — MEDIUM, quality-only
Junk visuals for "karma". **Mitigation:** concrete-photographable `visual_hint` prompt rule + genai fallback; the swap-image picker (task-17) lets users fix any miss in seconds.

## R8 — Windows dev vs ARM-Linux prod skew — MEDIUM
Dev machine is Windows; production is aarch64 Linux. **Mitigation:** ffmpeg pinned via setup script; pathlib everywhere; CI runs the test suite on a free GitHub Actions ARM runner from task-01 so wheel/arch surprises surface years before deploy day.

## R9 — Free quotas vs usage — RETIRED at current scale
With 1–2 users, daily free quotas (~750 LLM calls and ~250 images per person) are effectively unlimited; per-user credits were removed from scope. Global guards remain as safety rails. This risk returns (with the credits machinery) only if the audience ever grows.

## R11 — Hindi tone-conversion quality unverified — MEDIUM, product-defining
Every video speaks in its creator's voice via OpenVoice conversion, but OpenVoice's native language list doesn't include Hindi (conversion is cross-lingual by design, so it *should* work on edge-tts Hindi base audio). **Mitigation:** hard ear-test gate inside task-18 (5 Hindi scripts, converted vs base vs VoxCPM); if quality fails, the documented fallback — **VoxCPM-for-Hindi — now has real capacity on the home GPU worker** (task-20a), with stock-voice-for-Hindi as the floor when the worker is offline. The feature's default-ness is contingent on this test, and the spec says so out loud.

## R10 — Free hosting is quota-cuttable and reclaimable — MEDIUM
Oracle halved its free ARM tier in June 2026 with little notice; idle VMs get reclaimed; Vercel Hobby forbids commercial use. **Mitigation:** provisioning is fully scripted + nightly off-VM backups (rebuild < 1 hour, drilled in task-20); keep-alive + uptime monitoring; frontend is host-portable (any static host). If Oracle exits, the runbook documents migration to the next always-free VM.
