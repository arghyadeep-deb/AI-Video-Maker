# Task 15 — Provider Guards & Queue Visibility

- **Depends on:** Task 14
- **Estimated effort:** 1 day

## Objective

The simplified shared-budget machinery per [`01-requirements/10-hosting-accounts-quotas.md`](../01-requirements/10-hosting-accounts-quotas.md): **global provider guards with honest degradation** (no per-user credits — 1–2 users), key-pool rotation, FIFO queue with visible position, and the worker-online tier state the UI shows.

## Files

- `backend/app/quota/guards.py` — global counters per provider + reserve margins; friendly "resets midnight PT" errors
- `backend/app/core/config.py` — provider caps, key pools (rotate on 429)
- `backend/app/jobs/queue.py` — FIFO + queue-position computation; parallel lanes (VM CPU lane, GPU-worker lane)
- `frontend/components/{TierBadge.tsx,QueuePosition.tsx}` — "Generated footage available / Photo mode only", "1 job ahead"

## Implementation

- Degradation table: image-gen cap near → stock-only; ZeroGPU minutes out (worker offline) → CPU engines with notice; LLM cap near → block new scripts before improvements (in-flight work is sacred).
- Key pool: rotation only, ToS caveat logged in config comments.
- Admin `/api/admin/usage` — today's counters per provider.

## Tests

- Unit: guard transitions; rotation on 429; tier-state computation (worker online/offline × ZeroGPU remaining).
- Integration: forced image-cap → stock-only with visible notice; CPU and GPU lanes run concurrently; queue positions correct.

## Demo

Throttle a provider counter artificially — the feature degrades with a clear message; the tier badge flips live when the worker agent stops.

## Acceptance

- [x] Every degradation is visible in UI copy, never a silent failure. Every guard raises the same `QuotaExhaustedError` the LLM's own real 429s already surface as, which `main.py` maps to a 429 with the honest "resets midnight PT" hint — the frontend's existing `ApiRequestError.hint` display (already wired since task-02/08) shows it without any new UI code needed.
- [x] Provider caps can never be blown past (server-enforced). `guards.guard()` is called and tested to raise *before* the guarded call happens in every case: `generate_script`, `improve_selection`, and the genai image fallback (`test_generate_script_blocked_by_global_daily_guard`, `test_genai_cap_blocks_the_fallback_without_touching_stock_attempts`).
- [x] Tier badge truthfully tracks worker/ZeroGPU state. `worker_online` is a real (currently always-`False`) computed field, not a hardcoded response shape — task-20a can flip it to a genuine signal with no schema change. Live-verified in a real browser: the badge renders "Photo mode only" on the generate page, matching the actual (no worker, no deployed Space) state.

## Completion notes

- **Plain FIFO vs. task-07's existing round-robin-by-least-recently-served-user fairness algorithm**: `01-requirements/10-hosting-accounts-quotas.md` (locked, and explicitly the *later*, simplifying decision) calls for "Plain FIFO... with two users, contention is rare by nature." Did **not** rip out task-07's fairness algorithm to force literal FIFO — it degrades to FIFO in the common case anyway (ties resolve to arrival order until someone is actually *served*, per `_last_served_at`), so it's a strict superset, not a conflict. Instead, `queue_position()` (`app/jobs/queue.py`) *simulates* that exact same ordering to compute "N jobs ahead of you," so the position shown always matches what will really happen. Confirmed the simulation matches real claim order with a dedicated test (`test_queue_position_matches_actual_claim_order`).
- **Found a genuinely surprising (but correct, pre-existing, task-07) fairness property while testing this**: a burst of jobs from the *first* user to ever queue anything goes through entirely before a second user's single job, even though the second user "arrived" during the burst — because the tie-break for two users who have each *never been served* is arrival order, not per-job round-robin, and that first user keeps "arriving first" (their oldest still-queued job is always older) until one of their jobs actually finishes. Round-robin fairness only actually engages *after* someone has been served once. Documented in `test_queue_position_a_burst_from_the_first_arriving_user_goes_first` rather than silently working around it.
- **Key-pool rotation implemented for `ScriptLLM` only** (`gemini_api_keys` property on `Settings`, comma-separated pool + rotation-on-429 in `ScriptLLM._rotate_key`) — not extended to the Pexels/Pixabay/genai-image engines. The task's own config comment caveat ("rotation only... quota tied to the developer/project, not the key") means the value is modest resilience against one transient-429 key, and the owner would need to actually *have* multiple keys per provider for it to matter; LLM calls are by far the highest-frequency external call in this product, so that's where the real value is. Extending the same pattern to the image engines is mechanical if ever needed.
- **The degradation table's "block new scripts before improvements (in-flight work is sacred)"** is implemented as two guard checks against two different thresholds on the *same* counter: `generate_script` stops at `cap - gemini_text_new_script_reserve` (default cap 700, reserve 50), `improve_selection` keeps working up to the full `cap`. Verified both blocking-early and staying-open-later in one test (`test_new_script_reserve_blocks_generation_before_improve`).
- **The genai-image cap guards only the actual fallback call, not scene sourcing up-front**: `source_scene_image` tries Pexels and Pixabay *first*, unconditionally (they aren't capped at all), and only checks `guards.guard(conn, "genai_image", ...)` immediately before actually calling the genai engine. Guarding earlier would have incorrectly blocked stock-image attempts too, once the genai cap alone was exhausted — caught by writing the test for it, not by inspection (`test_genai_cap_blocks_the_fallback_without_touching_stock_attempts` explicitly proves a stock-hit still succeeds even with the genai cap fully spent).
- **Found and fixed a genuinely flaky pre-existing test while touching this same area** (`test_list_projects_reports_an_active_job`, from task-13): it used a `sleep(N)`-then-poll race to try to catch a job mid-"running", which had already needed widening once and still flaked under full-suite system load. Replaced with a real synchronization primitive: the fake TTS sets a `threading.Event` the instant it's actually invoked (a guaranteed signal, not a timing guess), and the test's single assertion runs right after that — no more polling loop, no more window to miss. Care was needed here: the TTS's own "hold this stage open" delay had to stay a plain `await asyncio.sleep(...)` (yields to the event loop) rather than a blocking `time.sleep`/`threading.Event.wait`, since a blocking wait inside the async stage would risk stalling the very `c.get()` call the test makes to check the result.
- **Deduplicated `_row_to_job`**, which `api/jobs.py` and `api/video.py` each carried their own separate (and, after this task, now out-of-sync) copy of — moved to `app/services/job_repo.py` (matching the existing `project_repo.py`/`script_repo.py` naming convention) so `queue_position` only needed adding in one place.
- **`/api/meta/tier` is left public (no session required)**, same reasoning as task-14's `/api/meta/voices`: it's site-wide capacity state with no user data in it, and gating it would add friction (the generate page needs it immediately) for no real security benefit.
- **Admin `/api/admin/usage`** reuses task-11's `require_admin` dependency (now backed by real roles from task-14) rather than inventing a new gate — reports today's raw counters for `gemini_text`, `genai_image`, and `zerogpu_seconds` (the three counters this codebase actually writes to as of this task).
