# Script Generation Flow

## Sequence

```
POST /api/projects {description, language, duration, format}
  → project row (status=drafting)
POST /api/projects/{id}/script
  → ScriptLLM.generate(description, language, duration)
  → validate JSON contract → script_versions row (v1) → return script
```

Synchronous (Gemini Flash returns in a few seconds); the UI shows a skeleton loader, not a job progress bar.

## Prompt design

System prompt (English) contains:
1. Role: professional scriptwriter for short-form video.
2. **Language directive**: write all `text` natively in the target language/script, never romanized, never translated word-by-word.
3. Duration → word budget table (≈140 wpm en, ≈120 wpm hi).
4. Scene rules: 8–15 s each; first scene is a hook; last is an outro/CTA.
5. `visual_hint` rules: English, concrete and photographable, 2–5 words.
6. TTS hygiene: no digits (words instead), no emoji/markdown/stage directions.
7. Output: JSON matching the response schema (enforced via Gemini structured output).

## Validation gate

Backend validates before persisting: parses against Pydantic model; checks scene count sane for duration; checks `text` fields contain the right Unicode script block (Devanagari for hi — cheap regex sanity check catching silent English fallbacks). Validation failure → one automatic retry with the error appended to the prompt; second failure → honest error to UI (no silent loops burning quota).

## Regeneration & scrap

- **Scrap**: `DELETE /script` marks all versions scrapped, project back to `drafting`; UI returns to create page with description prefilled.
- **Regenerate**: same endpoint as generate; creates v(n+1); explicit user click only.

## Failure modes

| Failure | Handling |
|---------|----------|
| 429 / quota exhausted | Backoff ×2 then surface: "Free daily limit reached — resets midnight PT" |
| Malformed JSON | 1 retry with error feedback, then error |
| Wrong language output | Caught by script-block check → same retry path |

Diagram: part of [`05-flowcharts/02-user-journey.mmd`](../05-flowcharts/02-user-journey.mmd).
