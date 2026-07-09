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

- [ ] Worker online/offline transitions are seamless — no stuck jobs, no user-visible errors, UI state truthful.
- [ ] All four engines run on the 5070 Ti with recorded benchmarks (Blackwell/PyTorch issues resolved and documented).
- [ ] Security: worker token can only lease/complete jobs; user media wiped from the PC post-upload.
