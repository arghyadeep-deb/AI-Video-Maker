# Research — Free LLM: Gemini Flash

**Sources:** [ai.google.dev/gemini-api/docs/rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits) · verified July 2026.

## Free tier facts (re-verify at build)

- Flash-class models: **~10–15 requests/min, ~1,500 requests/day, ~250 K tokens/min**. No credit card required; key from Google AI Studio.
- As of mid-2026, **only Flash and Flash-Lite are free**; Pro models require billing. Plan assumes Flash only.
- RPD quota resets midnight Pacific.
- Structured output (JSON mode / response schemas) supported — we rely on this for the script contract ([`01-requirements/02-script-generation.md`](../01-requirements/02-script-generation.md)).

## Why Gemini Flash over the alternatives

| Option | Verdict |
|--------|---------|
| **Gemini Flash** | Best free Indic-language quality (Hindi generation is a Google strength); JSON mode; same key also unlocks free image gen — one vendor, one setup step. **Chosen.** |
| Groq (Llama 3.3 70B) | Very fast, generous free tier, but Llama's Hindi output is weaker than Gemini's. **Fallback.** |
| OpenRouter free models | Rotating availability; unreliable as a foundation. Emergency fallback only. |
| Local Ollama | Truly unlimited, but 7–13 B local models produce poor Hindi; not acceptable for the core product artifact. Rejected. |

## Budget math

A video consumes ~2–6 LLM requests (1 script + 0–4 improvements + 1 lazy visual-hint refresh). 1,500 req/day ≈ hundreds of videos/day — quota is a non-issue for single-user local use. The 10–15 RPM limit only matters if we ever batch: keep calls sequential.

## Integration notes

- Use the official `google-genai` Python SDK.
- Wrap in a typed `ScriptLLM` client: one place for model name, retry-with-backoff on 429, and quota-exhausted error mapped to a user-visible message.
- Model ID is a config value, not hardcoded — Flash version names rotate.

## Prompting for Indic languages

- System prompt in English, explicit instruction: "Write the script text entirely in <language> using <script> script; never romanize."
- Ask for words-not-digits numbers; forbid emoji/markdown in `text` fields (TTS reads them literally).
