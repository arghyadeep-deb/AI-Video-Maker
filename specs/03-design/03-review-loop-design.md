# Review Loop Design

## State machine

```
drafting → script_ready ⟲ (improve | edit | regenerate) → accepted → generating → done
                └─ scrap → drafting
```

`accepted` freezes the script version referenced by the render; later edits would create a new version and require re-accept (the UI simply hides editing after accept).

## Improve-selection mechanics

Request: `POST /script/improve { version_id, scene_id, start_offset, end_offset, instruction? }`

1. Backend extracts the selected span from the scene text.
2. Prompt = full script (context) + the span + instruction + hard rule: *return replacement text for the span only, same language, similar length unless instructed otherwise*.
3. Response is the replacement string; backend splices it into a **proposed** scene text.
4. Return `{ old_span, new_span, proposed_scene_text }` — **not yet persisted**.
5. UI renders old vs new inline; **Keep** → `POST /script/apply` creates version n+1; **Revert** → discard, nothing stored.

Selections crossing scene boundaries: selection is restricted to within one scene (editor enforces); multi-scene rewrite = select nothing and use the instruction-only "improve whole script" button (same endpoint, span = whole script).

## Manual edit mechanics

Scene text is directly editable (per-scene textarea). Debounced save creates a version only on blur/explicit save, not per keystroke. `visual_hint` marked stale when text changes; refreshed in one batch LLM call at generation start.

## Versioning

`script_versions`: `(id, project_id, n, scenes_json, origin ∈ {generated, improved, edited}, created_at)`. Keep last 10 per project, prune older. UI exposes single-step undo (restore v n−1 as new version); full history visible in a side panel (simple list, click to restore).

## Editor UI contract

- Scene cards, each showing scene number, text (editable), and estimated seconds.
- Text selection inside a card raises a floating "✨ Improve" button + instruction popover.
- Sticky footer: word count, estimated duration vs target, **Scrap** (confirm), **Accept & continue**.

Diagram: [`05-flowcharts/03-script-review-loop.mmd`](../05-flowcharts/03-script-review-loop.mmd).
