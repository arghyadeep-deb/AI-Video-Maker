# Research — Free Stock Image APIs (Mode B)

## Pexels — primary

- Free API key, instant signup. Limit ~**200 requests/hour, 20 K/month** (generous for our use: 1 search per scene ≈ 6–20 requests per video).
- `GET /v1/search?query=...&orientation=portrait|landscape&per_page=5` — orientation filter maps directly to our 9:16/16:9 format choice.
- License: free for commercial/personal use, no attribution legally required — we still write a `credits.txt` (photographer + URL) next to every output video (decision #8 in [`09-open-decisions`](../01-requirements/09-open-decisions.md)).
- Search is **English-only in practice** → this is why every scene carries an English `visual_hint` regardless of script language ([`02-script-generation.md`](../01-requirements/02-script-generation.md)).

## Pixabay — secondary

- Free API key; ~100 requests/min rate limit. Similar search shape (`q`, `orientation`, `min_width`).
- Slightly weaker photo quality on average; used when Pexels returns no acceptable hit.

## Unsplash — rejected

API now gates production access behind an approval process and tight demo limits; not worth the friction when Pexels + Pixabay suffice.

## Selection heuristics (design input for task-08)

1. Query = scene `visual_hint`; request 5 candidates.
2. Score: resolution ≥1080 px short edge → orientation match → not already used in this video.
3. Abstract topics ("karma", "compound interest") often return junk — the script prompt instructs `visual_hint` to be *concrete and photographable* ("night sky with planets", "stack of coins growing") precisely to avoid this.
4. Zero usable results from both APIs → nano banana generation ([`04-free-image-generation.md`](./04-free-image-generation.md)).

## Caching

Cache downloaded images per project under `media/projects/<id>/images/`; a regenerate with unchanged scenes reuses them (saves quota and time).
