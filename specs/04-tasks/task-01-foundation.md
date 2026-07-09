# Task 01 — Foundation

- **Depends on:** —
- **Estimated effort:** 1 day

## Objective

Monorepo scaffold: FastAPI backend + Next.js frontend + SQLite migrations + config/env handling + an environment "doctor" that verifies the free stack is ready.

## Files

- `backend/app/main.py` — FastAPI app, CORS for localhost frontend
- `backend/app/core/config.py` — pydantic-settings: keys, model IDs, voice table, paths
- `backend/app/db/{connection.py,migrations/001_init.sql}` — schema per [`03-design/08-data-model.md`](../03-design/08-data-model.md)
- `backend/app/api/meta.py` — `/api/meta/health`, `/api/meta/voices`
- `frontend/` — Next.js app scaffold, dark theme base, typed API client stub
- `media/` — gitignored data root
- `.env.example` — `GEMINI_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY`
- `README.md` — 5-minute setup walkthrough (obtaining the 3 free keys)

## Implementation

- Health endpoint reports: ffmpeg present + version, libass/HarfBuzz support probe, `torch.cuda.is_available()`, which keys are configured, DB migrated.
- Migrations: numbered SQL applied at startup, `schema_version` pragma.
- Bundle Noto Sans / Noto Sans Devanagari fonts under `backend/assets/fonts/` (OFL — include license file).

## Tests

- Unit: config parsing; migration idempotency.
- Integration: health endpoint shape with/without keys set.

## Demo

`uvicorn` + `next dev` both start; browser hits the frontend; a setup page renders `/api/meta/health` as green/red checklist.

## Acceptance

- [x] Fresh clone → keys in `.env` → two commands → both servers run.
- [x] Health check correctly detects missing ffmpeg and missing keys.
- [x] SQLite file created with full schema on first boot.

## Completion notes

- **Schema/quota discrepancy flagged for task-15**: `03-design/08-data-model.md`
  and `03-design/07-job-queue-and-progress.md` both model a per-user `credits`
  table as "enforced", but the locked decision in
  `01-requirements/10-hosting-accounts-quotas.md` explicitly *drops* per-user
  credit rationing in favor of global-only provider guards for a 1-2 user
  site. Migration `001_init.sql` creates the `credits` table as specified in
  the data model (harmless either way, and needed if task-15 decides to keep
  it for UI visibility rather than enforcement) plus the `usage` table for
  global per-provider counters. Task-15 must explicitly decide: keep
  `credits` as informational only, or reconcile the docs and drop it.
- Migrations use `PRAGMA user_version` (not a `schema_version` table) to
  track applied migrations — matches the "no Alembic ceremony" spirit and is
  what the task's Implementation section names.
- SQLite access is synchronous (stdlib `sqlite3`) rather than an async
  driver — FastAPI runs sync `def` route handlers in a threadpool, which is
  sufficient at this scale (1-2 users, one VM) and avoids an extra
  dependency; revisit only if the job worker (task-07) shows contention.
- Bundled Noto Sans / Noto Sans Devanagari as their variable-font (`[wdth,wght]`)
  builds pulled from the `google/fonts` OFL repo; renamed to
  `NotoSans-Variable.ttf` / `NotoSansDevanagari-Variable.ttf` (dropped the
  `[...]` from the filename) to avoid shell/fontconfig escaping issues in
  later FFmpeg `fontsdir` usage (task-06).
- Frontend scaffolded with `create-next-app` (Next.js 16.2.10, App Router,
  TypeScript, no Tailwind — plain CSS custom properties for the dark theme
  base per `03-design/10-frontend-pages.md`'s "dark, editorial" direction).
  The nested `.git` repo `create-next-app` initializes was removed since the
  monorepo isn't a git repo yet.
- CI on an ARM runner (mentioned in the root `CLAUDE.md` environment notes)
  is deferred: task-01's own Acceptance criteria don't require it, and there's
  no git remote yet to attach a workflow to. Revisit at task-20 (deployment).
- Verified end-to-end: backend unit/integration tests (12 passing — config,
  migrations incl. idempotency, health/voices endpoint shape with and
  without keys, honest missing-ffmpeg detection), frontend `tsc --noEmit` +
  `next build` clean, and a real browser screenshot of the setup checklist
  confirming red dots for missing ffmpeg/keys/GPU and a green dot for the
  migrated DB.
