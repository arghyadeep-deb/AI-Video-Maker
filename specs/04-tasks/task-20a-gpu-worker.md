# Task 20a — Home GPU Worker Agent

- **Depends on:** Tasks 11, 15, 18 (engines + slot accounting); pairs with 20 (needs the VM reachable)
- **Estimated effort:** 3 days

## Objective

The worker agent per [`03-design/11-gpu-worker.md`](../03-design/11-gpu-worker.md): the owner's RTX 5070 Ti PC pulls GPU jobs from the VM over outbound HTTPS, runs SadTalker / VoxCPM / MuseTalk / LTX locally, uploads results — making HD the default experience whenever the PC is online.

## Files

- `worker-agent/` — standalone Python service: long-poll loop, lease/heartbeat, signed-URL download/upload, engine plugin registry, capability manifest, tray icon (pause/resume), config (`token`, `vm_url`, bandwidth cap)
- `backend/app/api/worker.py` — `/api/worker/{poll,heartbeat,complete,fail}` (worker-token auth, separate from user auth)
- `backend/app/jobs/gpu_router.py` — three-tier routing (worker → ZeroGPU → CPU), dynamic slot limits, worker-online state for the UI, mid-job loss re-queue
- `worker-agent/engines/{sadtalker.py,voxcpm.py,musetalk.py,scene_gen.py}` — subprocess/diffusers wrappers, VRAM-probed enablement; `scene_gen` = **Wan 2.2 TI2V-5B vs LTX-Video bake-off** (pick by quality-per-minute on the 5070 Ti; verdict recorded here) powering generated-footage Mode B
- `worker-agent/setup.md` + `scripts/setup_worker.ps1` — Windows install: CUDA 12.8+ PyTorch (Blackwell/sm_120), model weights, pinned deps (R12 surgery documented as found)

## Implementation

- Long-poll 25 s cycles; 3 missed heartbeats → lease expires → job re-queued and re-routed (a sleeping PC is normal, not an error).
- **Owner-first GPU sharing** per the design doc: auto-yield on GPU-busy (util/VRAM thresholds), instant-reclaim pause, work-hours schedule in config — all three tested (start a GPU-heavy app mid-queue → agent stops leasing; pause mid-job → job re-routes cleanly).
- Files deleted from the PC after successful upload; agent keeps no media library (privacy page states transit through owner hardware — task-21).
- Generated-footage Mode B: for each scene, image + motion-hint prompt → ~5 s clip; hold/loop tail bridges longer scenes; assembly already accepts per-scene clips. A 60 s video ≈ 12 clips ≈ 20–60 min on the 5070 Ti — queued with honest ETA, fine at 1–2-user scale.
- Benchmarks recorded in this file on completion: SadTalker/VoxCPM/LTX minutes-per-job on the 5070 Ti → feeds queue estimates and slot defaults.

## Tests

- Unit: router tier selection matrix (online/offline × slots × engine); lease expiry; capability negotiation.
- Integration (fake agent against dev VM): poll → lease → heartbeat → complete; kill agent mid-job → re-queue to ZeroGPU/CPU path; token misuse rejected.
- Live: real agent on the owner's PC against the deployed VM; HD avatar + HD voice + animated hero scene rendered end-to-end from a phone.

## Demo

PC on: a user gets a SadTalker HD avatar speaking in their VoxCPM HD voice with an animated opening scene, in minutes. PC put to sleep mid-queue: jobs visibly re-route, site keeps working.

## Acceptance

- [x] Worker online/offline transitions are seamless — no stuck jobs, no user-visible errors, UI state truthful. Proven at the protocol level in `tests/test_api_worker.py` (dead agent mid-job → lease expiry → requeue → `GpuTaskFailed` → tier fallback; tier badge flips on poll recency) and `tests/test_talking_head_chooser.py` (worker lost mid-render still produces a video via Wav2Lip). Live PC-sleep/wake verification against a deployed VM remains owner-gated with the rest of the live checklist.
- [ ] All four engines run on the 5070 Ti with recorded benchmarks (Blackwell/PyTorch issues resolved and documented). **Owner-gated**: engine wrappers + probes are written and the bake-off script is ready (`worker-agent/scripts/bakeoff.py`), but real runs need the owner to install the CUDA 12.8 engines venv (one PowerShell script) — same class as the task-11/18 gates. Record benchmarks + the Wan-vs-LTX verdict (judgment gate #3) here.
- [x] Security: worker token can only lease/complete jobs (`test_worker_token_grants_no_user_surface`; constant-time compare; endpoints disabled outright when `WORKER_TOKEN` unset); user media wiped from the PC post-upload, success or failure (`worker-agent/tests/test_agent.py::test_happy_path…` and `…engine_crash…` both assert the task dir is empty after).

## Completion notes

**This task was found skipped**: PROGRESS.md jumped from task-20 to task-21 (the sessions that built those two shared "everything short of live infra" and 20a fell through the gap). Built in full on 2026-07-10; everything below is tested against fakes/the real protocol; only the real-GPU runs stay owner-gated.

- **Architecture — two queues, not one**: `gpu_tasks` (new migration 004) is deliberately separate from `jobs`. A jobs row is a user-visible pipeline; a gpu_tasks row is one GPU sub-step handed to the PC while that pipeline `await`s it (`gpu_router.submit_task` → `wait_for_task`). No fairness pass on gpu_tasks (plain FIFO): user fairness already happened when the parent job was claimed.
- **The waiter runs the expiry sweep too** (`wait_for_task`'s loop, not just the poll endpoint): when the agent dies, nobody polls — without this, a pipeline would hang for its full timeout instead of failing over within ~3 missed heartbeats. This is the linchpin of "worker loss is a normal event".
- **Agent-reported failure ≠ lease expiry**: an engine crash reported via `/api/worker/fail` fails the task permanently (near-certainly deterministic for that input — retry would burn GPU minutes before the same fallback); a *silent* disappearance requeues up to `worker_task_max_attempts` (a slept PC deserves one more try). Instant reclaim ("Pause now") deliberately reports nothing — the expiry path owns re-routing, so nobody's video is lost (tested both sides).
- **Task spec correction**: the task file said Mode B "assembly already accepts per-scene clips" — it didn't (task-09's `SceneClip` was image-only). Added `video_path` to `SceneClip` + a `_footage_filter` branch (cover-fit + fps pin + `tpad=stop_mode=clone:stop=-1` + exact `trim`, keeping the xfade offset math identical to Ken Burns) and a new `footage` pipeline stage between images and subtitles. Found in the process: `tpad` has no `whole_dur` option (that's `apad`'s) — caught by a real ffmpeg run, hence hold-then-trim. Also learned/confirmed: the Ken Burns branch massively overproduces frames (zoompan emits d frames per looped input frame) and production duration correctness comes from the audio map + `-shortest` — the new mixed-scene integration test mirrors that exactly.
- **Honest degradation end-to-end**: footage requested while worker offline → 400 with a human hint at the API; worker lost mid-render → completed clips keep motion, remaining scenes get Ken Burns, and `jobs.engine_notes` records "N/M scenes generated" (tested); stale clips are invalidated on image swap/re-source and cleared on a later photo-level render, so motion from an old image can never resurface.
- **Mode A HD default**: `hd_requested` became `Optional[bool]` (None = server decides at render time: HD iff the worker advertises sadtalker). The chooser gained tier 1 (`HomeWorkerTalkingHeadEngine`) via a backwards-compatible keyword arg — all pre-existing chooser tests pass unchanged. There is still no user-facing HD toggle (deliberate, documented in the generate page).
- **Signed URLs**: full-entropy `secrets.token_urlsafe(32)` (NOT `new_id()`'s UUIDv7, whose leading bits are a timestamp), single-use, TTL'd, 404-identical for unknown/expired/reused. Upload filenames are sanitized to basename (traversal test included).
- **worker-agent/**: standalone package (own tiny venv: requests + optional pystray) with injectable GPU probe/clock/HTTP — 23 pure-logic tests run without a GPU and in CI (new `worker-agent` job in ci.yml). Engines venv is separate (torch cu128 for Blackwell/sm_120 — R12). `scene_gen` supports both Wan 2.2 TI2V-5B and LTX-Video behind one config key; **judgment gate #3 is open** — `scripts/bakeoff.py` reuses the production engine class itself so the owner judges exactly what production runs. Deviation from the task's Files list: `setup_worker.ps1` lives at `worker-agent/scripts/` (not a repo-root `scripts/`, which doesn't exist) to keep the agent self-contained.
- **Owner-gated remainder**: real engine installs + benchmarks on the 5070 Ti, the bake-off verdict, and live end-to-end (phone → HD avatar via the real PC) which also needs task-20's deployed VM. `WORKER_TOKEN` added to `.env.example`, `deploy/setup_vm.sh`'s template, and RUNBOOK §3b.
- Suite state: 441 backend tests + 23 agent tests passing; frontend tsc/eslint/build clean (generate page gained the Photo-vs-Generated-footage picker, gated on live `worker_capabilities` so it's never a dead checkbox).
