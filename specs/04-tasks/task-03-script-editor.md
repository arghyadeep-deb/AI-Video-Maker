# Task 03 — Script Editor (Review Loop Core)

- **Depends on:** Task 02
- **Estimated effort:** 2 days

## Objective

The `/project/[id]/script` page: scene cards with inline manual editing, version history + undo, Accept and Scrap. (AI improve-selection is Task 04.)

## Files

- `frontend/app/project/[id]/script/page.tsx` — editor layout
- `frontend/components/SceneCard.tsx` — editable text, ~seconds estimate
- `frontend/components/VersionHistory.tsx` — dropdown list, restore
- `backend/app/api/script.py` — add scene PUT, restore, accept, scrap (DELETE)
- `backend/app/services/script_service.py` — version create/prune (keep 10), duration estimator (wpm per language)

## Implementation

- Manual edit: textarea per scene, save on blur → new version; `visual_hint_stale=true` on changed scenes.
- Accept: freezes version id on project, status → `accepted`, navigates to generate page (stub for now).
- Scrap: confirm dialog → DELETE → back to `/create` with description prefilled.
- Sticky footer: total words, estimated vs target duration (warn >±20%).
- Undo = restore v(n−1) as new version.

## Tests

- Unit: version pruning; duration estimate per language; stale-flag logic.
- Integration: edit → new version; restore → correct content; accept locks; scrap resets status.
- Frontend: SceneCard edit/save cycle; footer math.

## Demo

Edit scene 2's Hindi text, blur → version bump visible in history; restore v1; accept → status chip flips to Accepted; scrap another project → lands on prefilled create page.

## Acceptance

- [x] Every mutation creates a version; history restores exactly. (edit -> v2, restore v1 -> v3 with byte-identical scene content; live-verified in browser + `test_restore_creates_new_version_with_old_content`)
- [x] Accept/scrap state machine matches [`03-design/03-review-loop-design.md`](../03-design/03-review-loop-design.md). (live-verified: accept freezes `accepted_version_id` + navigates to the generate stub; scrap resets to `drafting` + redirects to `/create` prefilled)
- [x] Hindi (Devanagari) text renders and edits correctly (no mojibake) end to end. (typed, edited, saved, restored, and displayed correctly in a real browser — see Completion notes)

## Completion notes

- **Found and fixed a real concurrency bug during live verification**: `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`. FastAPI resolves each sync dependency via `run_in_threadpool`, and successive dependencies on one request (`get_db` then `get_current_user_id`) can land on different worker threads — intermittently, not on every request, which is why it slipped through the task-02 test suite and only showed up under real browser use. Fixed in `backend/app/db/connection.py` by opening connections with `check_same_thread=False` (safe here: access within a request is strictly sequential, never concurrent). Added a regression test, `test_connection_usable_from_a_different_thread`, and verified it fails without the fix and passes with it.
- **Found and fixed a frontend robustness bug during the same session**: `/project/[id]/script` unconditionally replaced the *entire page* with a bare error message whenever any mutation's post-save refresh failed, discarding the user's already-loaded scenes with no way back short of a hard reload. Changed so only the *initial* load-failure (nothing loaded yet) takes over the page; a refresh failure after edit/restore/accept/scrap now shows an inline dismissable-on-next-success banner while keeping the last-known-good scenes fully visible and editable.
- **`react-hooks/set-state-in-effect` (new stricter ESLint rule in this Next.js/React version)** flagged the standard "call a local async callback from `useEffect`, have it setState" pattern used successfully elsewhere in this repo (works fine when the callback is an *imported* function, e.g. `setup-checklist.tsx`'s `getHealth().then(setHealth)`; the rule appears to trace into locally-defined callbacks but not across module boundaries). Fixed by inlining the initial-load fetch chain directly in the effect. Separately, `SceneCard`'s "reset local edit buffer when the prop changes" effect was replaced with React's officially recommended alternative for that exact case: keying each `SceneCard` on `` `${scene.id}:${scene.text}` `` so it remounts with a fresh initial value instead of syncing via an effect.
- **Added `GET /{project_id}/script/versions`** (not in the task's own Files list or the locked `09-api-endpoints.md` table) — the `VersionHistory` dropdown needs a data source and nothing else provided one. Returns lightweight summaries (id/n/origin/created_at), not full scenes.
- **Restore's `origin` is stored as `"edited"`** — the `script_versions.origin` enum (`generated|improved|edited`) has no dedicated "restored" value, and "edited" is the closest existing fit for "a human action reverted content, no AI involved."
- **No backend-side block on editing an already-`accepted` project.** The spec says "the UI simply hides editing after accept," implying this is a UI-only gate; the editor already disables scene textareas and Scrap/Accept when `project.status === "accepted"`. If the owner wants a hard backend invariant here later, that's a one-line addition to `edit_scene`/`restore_version`.
- **Scrap does not delete/mark `script_versions` rows** despite `03-design/03-review-loop-design.md`'s "marks all versions scrapped" phrasing — the schema (`08-data-model.md`) has no such flag, and deleting history on scrap would contradict the version-pruning design's own "keep history for undo" philosophy. Scrap just resets `projects.status` to `drafting` and clears `accepted_version_id`; the scrapped project's rows become an inert orphan (acceptable — there's no route back to a `drafting` project until task-13's library exists, and regenerate on a fresh project is cheap).
