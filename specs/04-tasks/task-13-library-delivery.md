# Task 13 — Library & Delivery

- **Depends on:** Tasks 09, 12
- **Estimated effort:** 1.5 days

## Objective

The home library, polished result delivery, avatar shelf management, and project/asset deletion — turning the pipeline into a product you return to.

## Files

- `frontend/app/page.tsx` — project grid, status badges, thumbnails, avatar shelf, empty state
- `backend/app/services/thumbnails.py` — ffmpeg frame-grab thumbnail on job completion
- `backend/app/api/projects.py` — list enrichment (thumbnail, duration, mode), DELETE with folder cleanup
- `frontend/components/{ProjectCard.tsx,AvatarShelf.tsx,DeleteConfirm.tsx}`
- `backend/app/api/video.py` — download bundle (mp4 + srt + credits.txt as zip); range-request streaming verified

## Implementation

- Thumbnail: frame at 10% of duration (Mode B) or portrait (Mode A pre-render).
- Delete: project row + media folder; avatar delete blocked if referenced by a project (or cascade with warning — pick simplest honest behavior and document).
- Selfie delete button on avatar detail (open decision #9 default: keep with delete button).
- Library shows in-flight jobs (generating badge with live % via the existing poll hook).

## Tests

- Unit: delete cascade rules; bundle contents.
- Integration: full lifecycle — create → render → appears in library with thumbnail → delete removes row + folder.
- Frontend: empty state, badge states, confirm dialog.

## Demo

Library with a few finished videos and one generating live; download a zip; delete a project and watch its folder vanish.

## Acceptance

- [x] Everything ever generated is findable, playable, and deletable from `/`. Live-verified: empty state, a populated grid (done/accepted/drafting/failed projects, newest-first), delete confirm dialog, and actual DB-row + media-folder removal all confirmed in a real browser.
- [x] Approved avatars visible, reusable, and deletable (with selfie removal). The library's Avatars shelf links to `/avatars` (task-10's page); `DELETE /api/avatars/{id}/selfie` removes just the selfie file, keeping the avatar/portrait usable, per open decision #9's default (keep for restyle, but offer a delete button).
- [x] Video streaming supports seeking (range requests confirmed). `test_stream_video_supports_range_requests` proves a `Range: bytes=100-199` request returns `206 Partial Content` with the correct `Content-Range` header and exact byte slice.

## Completion notes

- **Found and fixed a real gap: a failed render left the project stuck showing "generating" forever.** Neither pipeline (`mode_a.py`/`mode_b.py`) nor the generic, pipeline-agnostic worker (`jobs/worker.py`) ever reverts `projects.status` when a job fails or is cancelled - only success paths update it. Rather than teaching the worker about "projects" (out of scope, and would touch code shared by every future job type), `GET /api/projects` derives an honest *display* status: if a project shows `generating` but has no active (queued/running) job, it looks at the most recent job for that project and reports `failed`/`cancelled` instead. The underlying DB row is untouched — this is a read-time correction, not a data migration. Caught by writing the failure-path test first (`test_list_projects_shows_failed_status_instead_of_stuck_generating`), not by noticing it in the UI.
- **Found and fixed a second real ordering bug, live in the browser, not by reading code**: `ORDER BY created_at DESC` alone ties for any two projects created within the same millisecond (`created_at`'s actual precision) - SQLite then falls back to an unspecified tie-break, so "newest first" silently stopped being true for a batch of projects seeded in one Python script. Fixed by adding `id DESC` as a secondary sort key — UUIDv7 ids are themselves time-ordered, so this is a correct, not just cosmetic, tiebreaker. Added a regression test that forces two rows to share a timestamp and asserts the id-based order.
- **Deletion order matters and is now guarded by a test**: `PRAGMA foreign_keys = ON` is set for every connection, and `projects.accepted_version_id` references `script_versions(id)` — deleting `script_versions` before nulling out that reference on the `projects` row raises a real `FOREIGN KEY constraint failed`. Delete order: null the reference → `media_assets` → `jobs` → `script_versions` → `projects` → then remove the media folder. `test_delete_project_with_accepted_script_does_not_violate_fk_constraint` locks this in (this is the same class of bug task-09 hit in its own test fixtures — worth remembering as a recurring trap in this schema).
- **Thumbnails are genuinely generated, not placeholder files**: Mode B grabs a real frame at 10% into the finished render via `ffmpeg -ss`; Mode A copies the avatar's own approved portrait bytes (no ffmpeg needed - the task's own Implementation notes call this out explicitly: "portrait (Mode A pre-render)"). Both pipelines' own integration tests now assert a real `thumbnail.jpg` exists and, for Mode B, that it's a genuinely decodable image (`ffprobe`), not just a file that happens to be there.
- **`DELETE /api/avatars/{id}/selfie` guards the restyle path**: if a user deletes their selfie (keeping the approved avatar/portrait usable) and later hits "Regenerate", the styling job now fails with a clear message ("no selfie on file - restyling isn't possible") instead of crashing on `Path(None)`. Found by working through the open-decision-#9 default's consequences rather than by hitting the crash first.
- **`/` moved from task-01's placeholder "environment doctor" page to the real library** — that checklist still has real diagnostic value (confirms ffmpeg/keys/schema before building on top of the stack), so it moved to `/debug/setup` rather than being deleted, matching the existing `/debug/jobs` pattern from task-07.
- **The "Voices shelf" mentioned in `03-design/10-frontend-pages.md`'s `/` spec is deliberately absent** — personal/designed voice cloning doesn't exist until task-18; there's nothing to shelve yet. The credits header ("2/3 videos" per the same spec) is also absent, since per-user credits were dropped from scope entirely (`01-requirements/10-hosting-accounts-quotas.md`, locked) in favor of global-only guards — showing a credits counter that doesn't correspond to any real enforcement would be dishonest UI.
- **`ProjectCard` reuses the existing `useJob` polling hook directly** for any project whose status is `generating`, rather than inventing a separate polling mechanism for the library grid — the same hook already used on the result page, just pointed at a different job id per card.
