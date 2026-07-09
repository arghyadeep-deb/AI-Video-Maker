# The Zero-Cost Constraint

**Hard rule: the product must cost ₹0 to build, ₹0 to host, and ₹0 per video — for the owner and the users.** This is a first-class requirement, not an optimization. Every architecture decision in `03-design/` is downstream of it.

## What "free" means here

| Allowed | Not allowed |
|---------|-------------|
| Free-tier API keys (no credit card) | Anything metered per request/video |
| Open-source models on free compute | "Free trial" that expires or requires a card |
| Always-free hosting tiers (Oracle, Vercel, HF) | Paid GPUs / cloud rendering farms |
| Free stock-media APIs (attribution OK) | Scraping services against their ToS |

## The free budget (verified July 2026 — re-verify at build time)

| Resource | Free quota | Used for |
|----------|-----------|----------|
| Gemini Flash API | ~10–15 req/min, 1,500 req/day | Script generation + improvements, scene segmentation, image keywords |
| Gemini 2.5 Flash Image ("nano banana") | ~500 images/day | Selfie → styled persona portrait; AI image fallback for Mode B |
| edge-tts | Unmetered (unofficial) | Hindi/English narration + word timings |
| Pexels / Pixabay APIs | 200 req/hr / ~100 req/min | Mode B stock images |
| Oracle Always Free VM | 2 OCPU / 12 GB / 200 GB, always-on | Backend, worker, FFmpeg, Wav2Lip, SQLite, media |
| Vercel Hobby | Free SSL/CDN | Next.js frontend |
| HF ZeroGPU Space | ~minutes of H200/day | SadTalker, VoxCPM cloning, MuseTalk pass |
| SadTalker / Wav2Lip / VoxCPM / FFmpeg (OSS) | Compute above | Animation, cloning, assembly |

## The defining consequence: **the budget is shared**

This is a public site running on the **owner's** keys. 1,500 LLM calls and 500 images a day are the whole site's allowance, not one person's. Therefore:

1. **Per-user daily credits** (videos, scripts, stylings, GPU slots) are a core product mechanic, enforced server-side and shown in the UI ([`01-requirements/10-hosting-accounts-quotas.md`](../01-requirements/10-hosting-accounts-quotas.md)).
2. **Global guards** per provider degrade features honestly (stock-only images, "GPU slots exhausted — Wav2Lip today") instead of failing silently.
3. **No call is wasted**: nothing generates without an explicit user action; everything cacheable is cached.
4. **Honest queueing**: one shared VM renders everything; users see their queue position, not a spinner.
5. **Unofficial dependency risk** (edge-tts) and **quota-cut risk** (Oracle halved its free ARM tier in June 2026) are absorbed by interfaces + fallbacks, never by paying.
