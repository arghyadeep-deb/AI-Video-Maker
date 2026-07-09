# Script Generation

**Question.** How does a rough description become a script?

**Decision.** One LLM call to Gemini Flash produces a **structured, scene-segmented script directly in the target language**.

## Inputs

| Input | Required | Notes |
|-------|----------|-------|
| Description | Yes | Free text, approximate; tone/type inferred from it |
| Language | Yes | `hi` / `en` — chosen once, flows through everything |
| Target duration | Yes | Preset picker: **30 s / 60 s / 2 min / 5 min** (default 60 s). Drives word count (~140 wpm English, ~120 wpm Hindi) |

## Output contract (locked)

The LLM must return JSON, not prose:

```json
{
  "title": "...",
  "language": "hi",
  "scenes": [
    { "id": 1, "text": "narration text in target language", "visual_hint": "english keywords for image search" }
  ]
}
```

- `text` is **in the target language** — generated natively, never translated afterwards.
- `visual_hint` is **always English** regardless of script language, because stock-image APIs search in English. Generated up-front so Mode B needs no second LLM pass.
- Scene granularity: one scene ≈ one sentence-group ≈ 8–15 s of narration.

## Rules

- Script register must match the description's implied persona (astrologer → warm, authoritative; business explainer → crisp).
- No stage directions, emoji, or markdown inside `text` — it goes verbatim to TTS.
- Numbers written out as words in the target language (TTS reads them better).
- One generation per click; no silent retries that burn quota. Regeneration is an explicit user action.

Design: [`03-design/02-script-flow.md`](../03-design/02-script-flow.md). Model facts: [`02-research/01-free-llm-gemini-flash.md`](../02-research/01-free-llm-gemini-flash.md).
