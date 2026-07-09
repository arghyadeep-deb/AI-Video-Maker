# Task 07 — Job Queue + Progress

- **Depends on:** Task 01
- **Estimated effort:** 1.5 days

## Objective

SQLite-backed job table, single async worker, stage/progress reporting, cancel, and the frontend progress components — per [`03-design/07-job-queue-and-progress.md`](../03-design/07-job-queue-and-progress.md).

## Files

- `backend/app/jobs/{queue.py,worker.py,registry.py}` — enqueue, claim, stage runner, cancel flag, subprocess kill
- `backend/app/api/jobs.py` — GET status, POST cancel
- `frontend/hooks/useJob.ts` — 1.5 s polling, stops on terminal states
- `frontend/components/StageChecklist.tsx` — stages with current sub-progress bar

## Implementation

- Pipelines register as ordered `(stage_name, coroutine)` lists; worker updates `stage`/`progress` between steps; step coroutines get a `report(pct)` callback and a `cancelled()` probe.
- `awaiting_user` status supported (park/resume) — needed by Tasks 10/11.
- Startup sweep: `running` → `failed("interrupted by restart")`.
- Failure captures exception + last 20 lines of any subprocess stderr into `error`.
- Demo pipeline `noop_render` (3 fake stages with sleeps) registered for tests/UI dev.

## Tests

- Unit: state transitions incl. cancel between stages and awaiting_user park/resume; startup sweep.
- Integration: enqueue noop job → poll shows queued→running→stages→done; cancel mid-run kills promptly; induced exception → failed with message.
- Frontend: useJob stops polling on done/failed; checklist renders stages.

## Demo

Kick a noop job from a debug page; watch the checklist tick through stages live; cancel a second one mid-flight.

## Acceptance

- [x] One job at a time, FIFO; queued jobs wait. (implemented as the design doc's actual fairness rule — least-recently-served-user round-robin, which *is* FIFO for a single user; `test_claim_is_round_robin_across_users_not_fifo` proves a 5-job "hog" user can't starve a 1-job "quiet" user)
- [x] Cancel works and kills child processes. (`Worker.request_cancel` sets a flag checked between/during stages *and* kills any subprocess registered via `ctx.register_process`; live-verified in a browser — cancel-while-queued transitions straight to `cancelled` with zero stages marked done)
- [x] No orphaned `running` rows after a hard backend kill + restart. (`sweep_interrupted_jobs` runs in the lifespan startup, before the worker starts; `test_sweep_interrupted_jobs_marks_running_as_failed` simulates the crash by leaving a row `running` with no process behind it)

## Completion notes

- **Acceptance says "FIFO," the design doc says "round-robin by least-recently-served user."** These aren't in tension — I implemented the round-robin rule literally (`app/jobs/queue.py:claim_next_job`), which degenerates to plain FIFO whenever there's only one user (true today, pre-task-14). Went with the more specific design-doc rule rather than literal FIFO since it's a strict superset of correctness and this exact fairness property is called out by name in `03-design/07-job-queue-and-progress.md`.
- **No credit refund on the startup sweep** — the design doc says an interrupted `running` job's "spent credit [is] refunded," but there's no credit/quota system yet (that's task-15). `sweep_interrupted_jobs` marks the row `failed` with `error='restart interrupted'` and does nothing else; task-15 will need to add the refund once credits exist.
- **`register_process` exists on `JobContext` but nothing calls it yet** — no pipeline in this repo shells out to a subprocess yet (FFmpeg/SadTalker pipelines are task-09 onward). The mechanism is wired and cancel already kills anything registered; it's just untested against a *real* subprocess because nothing produces one yet. Whoever writes the first FFmpeg-calling stage must call `ctx.register_process(proc)` right after `asyncio.create_subprocess_exec(...)` for cancel to actually kill it.
- **The debug endpoint `POST /api/jobs/debug/noop`** is explicitly not part of the locked API surface (`03-design/09-api-endpoints.md` has no such route) — it exists only so this task's own Demo ("kick a noop job from a debug page") and the frontend's `useJob`/`StageChecklist` have something real to talk to before any real pipeline exists. Same for `/debug/jobs` on the frontend — not one of the 7 product routes in `10-frontend-pages.md`. Flag for task-21 (launch polish): decide whether to keep, hide behind a dev flag, or delete both before going live.
- **Progress percentage granularity**: `noop_render`'s fake stages report at 25/50/75/100% every ~50ms, which is faster than the frontend's 1.5s poll interval — in practice the UI usually sees a stage jump straight from 0% to done rather than smoothly climbing, which is expected and fine (the demo pipeline is deliberately fast for quick test iteration, not tuned to *look* smooth). Real pipelines (FFmpeg progress parsing, etc.) will report at a cadence the 1.5s poll can actually observe.
- **Worker connections vs. FastAPI request connections**: the worker owns one `sqlite3.Connection` per job run (opened at claim time, closed when the job finishes) plus short-lived ones for polling the queue between jobs; FastAPI routes each get their own via `get_db()`. All use `check_same_thread=False` (the fix from task-03's cross-thread bug), and since the worker's connection is only ever touched from within its own single asyncio task — never concurrently — this is safe.
