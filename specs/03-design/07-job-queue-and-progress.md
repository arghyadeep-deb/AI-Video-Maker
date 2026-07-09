# Job Queue and Progress

## Why not Celery/Redis

Zero-cost + one shared VM ⇒ no external broker. A **SQLite-backed job table + one asyncio worker task** inside the FastAPI process is sufficient, debuggable, and adds nothing to setup. The interface is queue-shaped so a real broker could slot in if the product ever outgrows one VM.

## Job table

```
jobs(id, user_id, project_id, type, status, stage, progress, payload_json,
     result_json, error, engine_notes, created_at, started_at, finished_at)

type   ∈ {avatar_styling, render_mode_a, render_mode_b,
          rerender_scene, rerender_other_mode, voice_clone_prep}
status ∈ {queued, running, awaiting_user, done, failed, cancelled}
```

`awaiting_user` covers the avatar approval gate and the Colab-manual import step — the job is parked, not failed.

## Worker loop

- Single worker, one media job at a time (media jobs saturate the 2-core VM; concurrency would thrash).
- **Fairness (multi-user):** the worker picks the oldest job of the *least-recently-served user* (round-robin across users), not global FIFO — one user queueing 5 jobs cannot starve others. Queue position per user is computed on read and shown in the UI.
- Each pipeline is a list of `(stage_name, coroutine)` steps; the worker updates `stage` + `progress` between steps; long steps (FFmpeg, SadTalker) stream sub-progress via callbacks (FFmpeg `-progress` parsing; SadTalker estimated from audio length).
- Crash safety: any exception → `failed` with `error` = message + last 20 lines of subprocess stderr. On backend restart, `running` jobs are reset to `failed` with a "restart interrupted" note and the spent credit refunded (media steps aren't resumable).
- Cancel: `POST /api/jobs/{id}/cancel` sets a flag the worker checks between stages and kills active subprocesses.

## Progress to the frontend

- `GET /api/jobs/{id}` → `{status, stage, progress, error}`; UI polls every 1.5 s while a job page is open. Polling (not SSE/websocket) is deliberate: dead simple, fine at this scale. The endpoint shape won't change if transport is ever upgraded.
- UI renders the stage list as a checklist (script ✓ → audio ▶ → visuals → assembly) with the current stage's sub-progress bar — honest stages beat a fake smooth bar.

## Quota bookkeeping

Two tables, both **enforced**, not informational:
- `usage(date, counter, n)` — global per-provider counters (Gemini text/image, GPU seconds). Checked by the quota middleware before any credited action; nearing a cap triggers honest degradation (stock-only images, "GPU slots exhausted today").
- `credits(user_id, date, videos, scripts, stylings, gpu_slots)` — per-user daily allowances per [`01-requirements/10-hosting-accounts-quotas.md`](../01-requirements/10-hosting-accounts-quotas.md), decremented atomically with job creation, surfaced in the UI ("2 of 3 videos left today").

Diagram: [`05-flowcharts/06-job-status.mmd`](../05-flowcharts/06-job-status.mmd).
