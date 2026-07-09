# Task 08 — Image Sourcing

- **Depends on:** Task 02
- **Estimated effort:** 1.5 days

## Objective

`StockImages` engine: scene `visual_hint` → best Pexels image → Pixabay fallback → nano banana generation last resort; caching, credits collection, QA heuristics.

## Files

- `backend/app/engines/images/{base.py,pexels.py,pixabay.py,genai_fallback.py}`
- `backend/app/services/image_service.py` — per-project orchestration: stale-hint refresh (batch LLM), fetch, score, dedupe, cache
- `backend/app/engines/images/scoring.py` — resolution/orientation/dedupe heuristics per [`02-research/05-stock-image-apis.md`](../02-research/05-stock-image-apis.md)

## Implementation

- Search 5 candidates; score: short edge ≥1080, orientation match, not used in project; download winner to `media/projects/<id>/images/scene-<n>.jpg`.
- Credits accumulated per asset into `media_assets.meta_json` (photographer, URL, source) → `credits.txt` at assembly (Task 09).
- nano banana fallback adds a consistent style suffix; increments image usage counter.
- Batch visual-hint refresh: single LLM call listing only stale scenes.

## Tests

- Unit: scoring/dedupe; credits accumulation; stale-batch prompt includes only stale scenes.
- Integration (recorded fixtures): Pexels hit; Pexels empty → Pixabay; both empty → genai stub.
- Live smoke (manual): 6-scene Hindi script → 6 relevant, distinct, correctly oriented images.

## Demo

Run sourcing for a real script; open the project folder — six sensible portrait images and their credit entries.

## Acceptance

- [x] Every scene gets exactly one image meeting the QA bar. (`pick_best` always returns a candidate when any usable one exists across the whole chain, genai as absolute last resort raises rather than silently skipping a scene)
- [x] Fallback chain order verified; generation only when both stocks fail. (`test_pexels_hit_stops_the_chain`, `test_pexels_empty_falls_to_pixabay`, `test_both_stocks_empty_falls_to_genai`, `test_provider_exception_falls_through_to_next` — provider exceptions degrade the same as an honest empty result, never abort sourcing)
- [x] Re-run with unchanged scenes downloads nothing (cache hit). (`test_rerun_with_unchanged_scene_downloads_nothing` — asserts the stub engine's query count doesn't increase; `test_stale_scene_is_resourced_even_if_cached` proves the cache is correctly invalidated by `visual_hint_stale`)

## Completion notes

- **No live smoke test was possible**: this environment has no real `PEXELS_API_KEY`, `PIXABAY_API_KEY`, or `GEMINI_API_KEY`. Every engine (`PexelsImages`, `PixabayImages`, `GenaiFallbackImages`) is unit-tested against mocked HTTP responses / a no-key honest-empty-list path, and the orchestration (`image_service.py`) is tested with stub engines standing in for "recorded fixtures" exactly as task-08's own Tests section anticipates. **You still need to run the actual live smoke test** (a real 6-scene Hindi script → 6 relevant, distinct, correctly-oriented images) once real keys are in `.env`.
- **"Not already used" is a tiebreak preference, not a hard filter** — re-read `02-research/05-stock-image-apis.md`'s "Score: resolution → orientation → not used" as a lexicographic priority order rather than three independent hard gates. A resolution-qualified-but-already-used candidate still beats leaving a scene with no image at all (`test_pick_best_falls_back_to_reuse_rather_than_none`). If the owner wants "never reuse, ever" as a hard rule instead, that's a one-line change to `pick_best`'s priority tuple.
- **`ImageCandidate.url` is `Optional`** (not on `StockImageEngine`'s original conceptual shape) because nano banana returns raw image bytes in-memory, not a hosted URL — added `image_bytes: Optional[bytes]` instead and branched `download_candidate` on which one is populated. Pexels/Pixabay always set `url`; genai always sets `image_bytes`.
- **Credits are written to `media_assets.meta_json` only** (photographer, URL, source, engine) — the actual `credits.txt` file bundled with the download is task-09's job at assembly time, per this task's own Implementation notes ("→ `credits.txt` at assembly (Task 09)").
- **No new API endpoint or frontend files** — task-08's Files list is engines + service only; nothing in `03-design/09-api-endpoints.md` exposes image sourcing directly at this stage (it's invoked as a job-pipeline stage once task-09 builds Mode B assembly; the swap-image picker endpoint is task-17's scope).
- **Provider failures (timeouts, 5xx) are swallowed the same way as legitimate empty results** in `source_scene_image` — a broad `except Exception` around each stock engine's `search()` call. This trades some observability (a real Pexels outage looks identical to "no relevant photos") for resilience (sourcing never hard-fails a scene just because one provider hiccuped). If this needs to be distinguishable later (e.g. for the health check or admin visibility), the exception types (`PexelsUnavailableError`, `PixabayUnavailableError`) already exist — a future task just needs to catch and log them instead of catching bare `Exception`.
