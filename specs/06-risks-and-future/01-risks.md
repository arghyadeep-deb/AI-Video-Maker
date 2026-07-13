# Risks

Ordered by (likelihood × impact). Every risk has a free mitigation — the zero-cost constraint forbids "pay to fix".

## R1 — edge-tts breaks (unofficial API) — HIGH likelihood over product lifetime
Microsoft can change/close the endpoint any day. **Mitigation:** `TTSEngine` interface already isolates it; fallback = **Supertonic** (MIT, CPU-only ONNX, hi+en) + faster-whisper forced alignment for timings (both OSS); Parler-TTS as second reserve. Cost of switch: one engine file. See [`02-research/07-voice-engine-alternatives.md`](../02-research/07-voice-engine-alternatives.md). Watch: `rany2/edge-tts` issues.

## R2 — Free-tier terms change (Gemini text/image) — **TRIGGERED for image, 2026-07-11**
Google has already moved Pro models off the free tier; Flash could follow or quotas shrink. **Mitigation:** model IDs and quotas are config; Groq/OpenRouter fallback for text. Image styling has no equally good free fallback — if nano banana goes paid, Mode A styling degrades to local SD+InstantID (GPU owners) or persona presets without selfie styling. Documented as an accepted product risk.

**Status update (2026-07-11, verified live):** the image half fired. `gemini-2.5-flash-image` returns 429 with `limit: 0` on the free tier (Google shut the free image-preview model on 2026-01-15; current image models are API-paid-only — free image generation survives only in the Gemini *app*). Text (`gemini-flash-latest`) remains free and was live-verified the same day. Consequences applied:
- **Mode B image chain**: unaffected in practice — stock-first (Pexels→Pixabay both live-verified); the genai third leg simply never fires (task-15's quota guard already degrades to stock-only honestly).
- **Mode A styling**: `avatar_styling` now degrades honestly — on `ImageStylerUnavailableError` the RAW selfie is offered as the portrait at the existing approval gate, reason recorded in `jobs.engine_notes` (this is the "persona presets without selfie styling" floor).
- **The wired fallback proper — implemented and live-verified, 2026-07-13 (task-22).** Local styling on the owner's 5070 Ti via IP-Adapter FaceID (SDXL) - `worker_agent/engines/styler.py`, a `styler` capability behind the existing `ImageStyler` interface. Real end-to-end proof: Gemini fails (confirmed still exhausted) → home worker → genuine styled portrait produced, `engine_notes` records which tier. InsightFace's `buffalo_l` weights are non-commercial-only (licenses page updated); fine for this free product, re-audit before any monetization.
- **Text fallback chain: implemented and live-verified same day.** `ScriptLLM` now tries Gemini (key pool) → Groq → OpenRouter (`make_script_llm`); fires on quota AND availability failures; the user-facing error stays the honest Gemini one if every provider fails. Groq verified live (clean Devanagari from `llama-3.3-70b-versatile`); OpenRouter key verified live (`:free` models rate-limit per-model upstream — acceptable for a third-string fallback; model id is config). Fallback output still passes through the script validation gate, so a weaker model degrades to an honest validation error, never silent garbage.

## R3 — GPU capacity is intermittent — MEDIUM (was HIGH before the home worker)
Primary GPU is the owner's RTX 5070 Ti, online only when the PC is on; overflow is a few ZeroGPU minutes daily. **Mitigation (shipped, not theoretical):** three-tier routing (home worker → ZeroGPU → CPU) with lease/heartbeat re-queue, dynamic slot limits, and truthful UI state ("HD available / limited today"); Wav2Lip + OpenVoice CPU paths mean every feature has a zero-GPU floor. Mode B is 100% CPU-safe and is deliberately the default-highlighted mode.

## R12 — Blackwell (RTX 5070 Ti) vs 2023-era research code — RETIRED, resolved 2026-07-13
sm_120 needs PyTorch built for CUDA 12.8+; SadTalker/Wav2Lip pin ancient deps and may need patches. **Resolved (task-22):** SadTalker runs clean in a separate Python 3.11 pins venv with torch cu128 - the anticipated surgery (basicsr's `functional_tensor` import) plus two more found live (a stale `imageio` pin's `RecursionError`, a subprocess pipe-deadlock in the engine wrapper itself) are all fixed and documented in `worker-agent/setup.md`. Real render verified end-to-end, both directly and live through the full chooser/fallback chain. ZeroGPU Space remains the fallback for anything that won't run locally, though it wasn't needed here.

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

## R13 — Free `trycloudflare.com` quick tunnels have no uptime guarantee — MEDIUM, **triggered 3x, 2026-07-12/13**
The PC-hosted deploy (task-20's fallback for the Oracle card-decline) uses `cloudflared tunnel --url` — a free, unauthenticated "quick tunnel" with a randomly-assigned hostname and no official uptime SLA. Died three times total in about 24 hours: once after ~20h uptime (generic connection failure), once after ~9h (same signature), once with an explicit `wsasendto: A socket operation was attempted to an unreachable network` error specifically on IPv6 edge addresses. Each time: fresh tunnel, new `NEXT_PUBLIC_API_BASE_URL` on Vercel, frontend redeploy - every restart mints a new hostname, so recovery always needs that same manual Vercel update; there is no way to pin a stable URL without a real (paid-domain-backed) Cloudflare Tunnel. **Mitigation applied 2026-07-13:** both launcher scripts (`run_backend_tunnel.cmd`, `run_tunnel.cmd`) now pass `--edge-ip-version 4`, forcing IPv4-only connections to Cloudflare's edge - the third failure's signature was IPv6-specific, so this should meaningfully reduce (not necessarily eliminate) recurrence. **Still not done:** an uptime monitor (e.g. a scheduled health-check hitting `/api/meta/health` through the public URL) so a genuine drop is caught within minutes instead of whenever someone happens to check; switching to the self-restarting loop launcher (`run_tunnel.cmd`) was attempted but `cmd.exe` invocation misbehaved from this environment - worth another attempt with a cleaner approach. Oracle migration (R10) would retire this risk entirely.
