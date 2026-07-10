# Home GPU Worker (Owner's RTX 5070 Ti)

The owner's PC (RTX 5070 Ti **Laptop** GPU — **12 GB VRAM**, confirmed by a real `nvidia-smi` read at task-20a setup on 2026-07-10; planning docs earlier assumed the 16 GB desktop card) runs a **worker agent** that turns it into the site's primary GPU whenever it's online. No port forwarding, no public exposure: the agent makes **outbound HTTPS long-poll requests** to the VM and pulls jobs.

## Protocol

```
agent → VM: POST /api/worker/poll   {token, capabilities[], vram_free}
VM → agent: job lease {job_id, stage, input_urls} | none (long-poll)
agent → VM: POST /api/worker/heartbeat {job_id, progress}   (every 10 s)
agent → VM: POST /api/worker/complete {job_id} + result upload (multipart)
```

- Auth: a single pre-shared worker token in the agent's config (owner-only infrastructure; not a user surface).
- **Lease + heartbeat**: a job missing 3 heartbeats returns to the queue and re-routes (PC put to sleep mid-render is a normal event, not an error). Partial results discarded; stage restarted.
- Inputs (portrait, WAV, embeddings) downloaded from signed one-time URLs; outputs uploaded back; nothing else on the VM is reachable with the worker token.

## Capabilities (engine plugins on the agent)

| Plugin | Model | VRAM | Role |
|--------|-------|------|------|
| `sadtalker` | SadTalker | ~4 GB | HD avatar — **default engine while worker online** |
| `voxcpm` | VoxCPM | ~8 GB | HD voice cloning/design; **the Hindi cloning fallback (R11) at real capacity** |
| `musetalk` | MuseTalk | ~6 GB | Lip-enhance pass |
| `scene_gen` | **Wan 2.2 TI2V-5B or LTX-Video** (diffusers, no ComfyUI; task-20a picks by quality-per-minute on the 5070 Ti) | ~10–14 GB (needs CPU offload on the real 12 GB card) | **Generated-footage Mode B**: image→~5 s clip per scene — the "proper AI video" engine. Also serves single-scene re-renders |

Agent probes GPU + models at startup and advertises only what loads; the VM routes accordingly.

## Three-tier GPU routing (replaces the flat ZeroGPU budget)

```
GPU job → worker online? → home worker (plentiful)
        → else ZeroGPU minutes remaining? → ZeroGPU Space (rationed)
        → else CPU fallback (Wav2Lip / OpenVoice standard) with honest notice
```

- **With 1–2 users there is no slot rationing on the worker**: while online, HD avatars and generated footage are simply available, FIFO-queued; only the ZeroGPU overflow tier stays minute-budgeted. The UI reflects tier state live ("Generated footage available" / "Photo mode only — PC offline").
- Mode A defaults: worker online → **SadTalker HD by default**; offline → Wav2Lip default, HD as rationed option.
- Queue estimates account for tier (5070 Ti renders a 60 s SadTalker video in low minutes).

## Windows/Blackwell notes (task-20a)

- Blackwell (sm_120) requires **recent PyTorch (CUDA 12.8+ builds)**; SadTalker/Wav2Lip are 2023-era research code and may need dependency pins/patches — budgeted in the task, verified before launch (risk R12).
- Agent = a small Python service (`worker-agent/`) with a tray icon (pause/resume), auto-start optional, bandwidth-capped uploads.

## The owner's GPU comes first (locked)

The owner uses this GPU for their own work; the agent must never get in the way:

1. **Auto-yield**: before leasing a job, the agent checks GPU utilization and free VRAM — if another process (game, training run, editing app) is using the card beyond thresholds (config: >20% util or <10 GB free), it doesn't pick up work. Checked between jobs, so the owner's work is never contended mid-session.
2. **Instant reclaim**: tray "Pause now" aborts the current job immediately — the job re-queues to ZeroGPU/CPU tiers via the normal lease-expiry path; nobody's video is lost, it just re-routes.
3. **Work-hours schedule**: config for active windows (e.g. "only 22:00–08:00" or "always except 18:00–23:00"). Outside the window the agent idles at zero GPU cost.
4. **Site never depends on it**: with the agent paused/yielding, everything still works — scripts, editing, Photo-mode videos, Wav2Lip avatars, ZeroGPU minutes. Only the premium tiers (generated footage, HD avatars) wait or degrade, with the tier badge telling users honestly.

## Security & privacy

User media transits to the owner's PC for processing — disclosed in the privacy page (task-21); files deleted from the PC after upload; the agent keeps no library.
