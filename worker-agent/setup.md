# Home GPU Worker — Setup (Windows, RTX 5070 Ti)

Turns this PC into the site's primary GPU whenever it's online. Outbound
HTTPS only — no port forwarding, nothing exposed. Design:
`specs/03-design/11-gpu-worker.md`; task: `specs/04-tasks/task-20a-gpu-worker.md`.

## Quick install

```powershell
cd worker-agent
powershell -ExecutionPolicy Bypass -File scripts\setup_worker.ps1
```

The script creates one venv (`.venv`) holding the agent **and** its
in-process engines (scene_gen/voxcpm import torch/diffusers inside the
agent's own process, so they must share it), installs Blackwell-correct
PyTorch (CUDA 12.8 builds — sm_120 needs them, risk R12), copies
`config.example.toml` → `config.toml`, and prints what to fill in.
Only SadTalker/MuseTalk (2023-era pins that clash with modern diffusers)
go in a separate venv you point `engines_python` at.

## Manual steps the script can't do

1. **Token**: on the VM, set `WORKER_TOKEN=<long random string>` in the env
   file (see `docs/RUNBOOK.md`), restart the API, and paste the same string
   into `config.toml`'s `token`.
2. **vm_url**: the site's public URL.
3. **Engines** (each optional — the agent only advertises what loads):
   - **scene_gen** (generated footage): nothing to clone; weights download
     from Hugging Face on first task (~10-20 GB, one time). Works out of
     the box once the engines venv exists.
   - **sadtalker** (HD avatars): clone https://github.com/OpenTalker/SadTalker
     to e.g. `C:\tools\SadTalker`, run its `scripts\download_models.sh`
     equivalents (checkpoints into `SadTalker\checkpoints`), create a
     SEPARATE venv for its 2023-era `requirements.txt` (they clash with
     modern diffusers), set `sadtalker_dir` + `engines_python` (that
     venv's python.exe) in config.toml. Expect dependency surgery
     (2023-era pins) — record working pin versions here when found:
     - *(pins discovered during install go here)*
   - **musetalk** (lip enhance): same pattern, https://github.com/TMElyralab/MuseTalk,
     set `musetalk_dir`.
   - **voxcpm** (HD voice): needs Visual Studio Build Tools (C++ workload)
     first — its `editdistance` dep has no Python-3.13 Windows wheel and
     compiles from source (found live, 2026-07-10). Then
     `.venv\Scripts\pip install voxcpm` and add `"voxcpm"` to `engines`
     in config.toml.
4. **Bake-off (judgment gate #3, before launch)**: run
   `scripts/bakeoff.py` with 2-3 real scene images + prompts, watch the
   side-by-side results, record the verdict + timings in
   `specs/04-tasks/task-20a-gpu-worker.md`, set `scene_gen_backend`.

## Run

```powershell
# tray icon (green = active, amber = paused):
.venv\Scripts\python.exe -m worker_agent
# headless:
.venv\Scripts\python.exe -m worker_agent --no-tray
```

Auto-start (optional): Task Scheduler → run
`worker-agent\.venv\Scripts\pythonw.exe -m worker_agent` at logon.

## The owner's GPU comes first (how to reclaim it)

- **Do nothing**: the agent checks the card between jobs — if your game or
  training run has it (>20% util or <10 GB free), it simply doesn't lease.
- **Instant reclaim**: tray → "Pause now". The in-flight job aborts within
  ~1 s and re-routes on the VM (nobody's video is lost).
- **Schedule**: `active_hours = ["22:00-08:00"]` in config.toml.
- The site keeps working when this PC is off — Photo mode, Wav2Lip,
  ZeroGPU minutes. Only the premium tiers wait, with an honest badge.

## Privacy

User media (portraits, voice WAVs, scene images) transits this PC for
processing only. Task files live in `%USERPROFILE%\.aivideomaker-worker`
during a job and are deleted after upload — success or failure. The agent
keeps no library. This is disclosed on the site's privacy page.
