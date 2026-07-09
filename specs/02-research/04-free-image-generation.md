# Research — Free Image Generation (Avatar Styling)

**Sources:** Google AI pricing/rate-limit docs; free-tier surveys — verified July 2026.

## Gemini 2.5 Flash Image ("nano banana") — chosen

- **Free tier: ~500 images/day** at 1024×1024, no credit card — the most generous free image API in 2026.
- Same `GEMINI_API_KEY` as the script LLM — no extra setup.
- Crucially it supports **image input + editing instructions**: send the selfie plus "restyle this person as a Vedic astrologer, saffron robes, mystical study, keep the face identity, front-facing, neutral expression, photorealistic" → styled portrait that still looks like the user. This is exactly the Mode A styling step.
- Caution: the **Pro** image model (nano banana Pro) has **no free tier** — do not upgrade the model name casually.

## Identity preservation

Nano banana is known for strong subject consistency in edits, but identity drift is possible. Mitigations:
- Prompt template pins: "same person, same facial structure, do not beautify or change age/gender".
- The approval gate ([`01-requirements/04-mode-a-avatar.md`](../01-requirements/04-mode-a-avatar.md)) makes drift a retry, not a failure.
- Regeneration burns ~1 image of a 500/day budget — trivial.

## Alternatives considered

| Option | Verdict |
|--------|---------|
| Local SDXL + InstantID/IP-Adapter | Best identity control, fully offline — but needs an 8 GB+ GPU and heavy setup; rejected (no server GPU) |
| Pollinations.ai | Free & keyless but primarily text→image; weak for identity-preserving edits |
| Cloudflare Workers AI / Replicate free | Small or trial-shaped quotas; not foundation-grade |

## Also used for Mode B fallback

When stock search fails for a scene, generate the scene image with nano banana from `visual_hint` (+ style suffix for visual consistency across generated images in one video). Stock-first policy keeps this rare — budget impact negligible.
