# Task 22 — Local HD Engines: SadTalker HD, Local Portrait Styler, scene_gen Bake-off

- **Depends on:** Task 20a (worker protocol + agent, live and proven), Task 20 (live PC-hosted deploy)
- **Estimated effort:** 2–3 days (dependency surgery dominates; GPU-time waits are elastic)
- **Planned by:** Fable session 2026-07-12, at the owner's explicit direction. **Owner authorization for all model-weight downloads in this task was granted 2026-07-12** ("do this part locally and run all of them locally") — do not re-ask per download; do record every artifact fetched (URL + size + hash where published).

## Objective

Finish the three deliberately-deferred GPU capabilities, **entirely locally**, and only deploy when all three are verified:

1. **SadTalker HD avatars** on the 5070 Ti — the home-worker `sadtalker` capability that task-20a's chooser and HD-by-default routing already expect but no engine install ever backed.
2. **Local portrait styler** — risk R2's wired fallback ("local SD+InstantID for GPU owners"), replacing the raw-selfie degrade with real persona styling now that Gemini's image API free tier is gone (`limit: 0`, verified live 2026-07-11).
3. **Wan vs LTX bake-off** — judgment gate #3, interrupted mid-run on 2026-07-11 and never finished; `scene_gen_backend` sits on an unverified-against-alternative "wan" default.

## The iron rule of this task (owner's words)

> "run all of them locally, after all of them are done then only deploy it"

Concretely: **the live services (backend :8000, cloudflared tunnel, worker agent, Vercel frontend) must not be restarted or redeployed with any of this task's changes until Phase 5.** Commit locally as often as you like, but **do not `git push` before Phase 5** — the Vercel project is git-linked to this GitHub repo, so a push can trigger an automatic frontend deploy on its own. The live site keeps working exactly as it does today throughout Phases 0–4. All new backend code must be verified against a **second dev instance** (uvicorn on **port 8001**, same `.env`, same DB is fine — the job worker inside it is idle unless you enqueue through it) and via the test suites. The worker *agent* process may be restarted freely (users only lose the "Generated footage available" badge for seconds), but its `config.toml` `engines` list must not advertise a new capability until that engine has passed its local verification.

## Environment facts (verified live, don't rediscover)

- GPU: RTX 5070 Ti **Laptop**, **12 GB** VRAM (12227 MiB), driver 592.01, Blackwell **sm_120** → only CUDA 12.8+ torch builds run (R12).
- **The GPU is genuinely contended**: the owner's separate V.E.C.T.O.R. project (ComfyUI-class, port 8188) periodically holds ~11.5 GB. The agent's auto-yield handles this at lease time; for *installs and bake-off runs*, check `nvidia-smi` first and wait for a ≥10 GB-free window — never kill the other project's processes. On this shared machine, kill only by exact PID after inspecting `Get-CimInstance Win32_Process` command lines (lesson recorded in task-20a notes).
- Agent venv (`worker-agent/.venv`): Python 3.13, torch 2.11.0+cu128 (CUDA verified), diffusers 0.39, transformers 5.13, accelerate 1.14. `config.toml`: `engines = ["scene_gen"]`, `scene_gen_backend = "wan"`. Wan 2.2 TI2V-5B already in the HF cache (~20 GB total cache); LTX-Video **not yet downloaded** (~10 GB).
- Global Python is 3.13 — 2023-era research pins (SadTalker) will not build against it; plan for a Python 3.10/3.11 pins venv (below).
- Backend restarts no longer log users out (`JWT_SECRET` persisted 2026-07-12) — but the iron rule above still applies: no unverified code on :8000.
- Disk: ~350 GB free as of 2026-07-11; this task adds roughly 25–35 GB (SadTalker ckpts ~4 GB, SDXL+InstantID ~12 GB, LTX ~10 GB, pins venv ~5 GB). Re-check before starting.

## Phase 0 — Preconditions (½ h)

- `git status` clean; note starting commit. `nvidia-smi` + `df` snapshot into the eventual Completion notes.
- Start the dev backend: `backend/.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001` (detached, logged). Verify `GET :8001/api/meta/health` = 200. All Phase 1–4 end-to-end checks go through :8001 (curl with a real login cookie is fine; the gstack `browse` skill against `localhost:3000` dev frontend pointed at :8001 is better where UI behavior matters).

## Phase 1 — SadTalker HD (~1 day, timeboxed)

**Install (the R12 surgery):**
- Create the separately-pinned venv the architecture already expects (`config.toml`'s `engines_python`): install Python 3.11 if absent (`winget install Python.Python.3.11`), then `python3.11 -m venv C:\tools\sadtalker-venv`.
- Clone `OpenTalker/SadTalker` to `C:\tools\SadTalker`; download its checkpoint set into `SadTalker\checkpoints` (+ gfpgan weights). Record URLs/sizes/hashes.
- **Do NOT install its pinned `torch==1.12.1`** — no sm_120 build exists. Install torch/torchvision **cu128** into the pins venv first, then SadTalker's remaining requirements, then patch forward-compat breaks as they surface. Expected surgery (budget for it, document every working pin in `worker-agent/setup.md`'s reserved "pins discovered" list): `basicsr`'s `torchvision.transforms.functional_tensor` import (patch to `functional`), NumPy 2.x `np.float`/`np.int` removals in old deps (pin `numpy<2` inside this venv if simpler), `librosa`/`numba` version pairing.
- **Timebox: 4 hours of surgery.** If it genuinely won't run on sm_120 after that, STOP — record the exact failure in Completion notes, leave `sadtalker` out of `engines`, and move to Phase 2. Wav2Lip remains the honest avatar floor; the site loses nothing it has today. Do not burn the whole task on this phase.

**Verify (agent-level first, then dev-instance E2E):**
- Direct engine run: `SadTalkerEngine(config).run(...)` with a fixture portrait + a real edge-tts WAV → playable MP4. Record minutes-per-job on this card (task-20a's benchmark line wants it).
- Add `"sadtalker"` to `config.toml` `engines`, restart the agent, confirm `/api/meta/tier` (on :8000 — read-only, allowed) now lists both capabilities.
- E2E through **:8001**: enqueue a Mode A render (task-12's flow) with `hd_requested` unset → job's `engine_notes` must read `sadtalker-home`; kill the agent mid-render once → job must complete via Wav2Lip fallback (chooser tier-fall proven live, not just in tests).
- **Owner gate (eyes)**: present the same script rendered by Wav2Lip vs SadTalker side by side; record the verdict in task-11's judgment-gate line and here. (Gate #1's LongCat half is already answered — 13.6B doesn't fit 12 GB.)

## Phase 2 — Local portrait styler (~1 day)

**Engine (in the agent's existing modern venv — no new venv):**
- New `worker-agent/worker_agent/engines/styler.py`, capability name **`styler`**, `vram_required_mb = 10 * 1024`, same abort/progress contract as `scene_gen`.
- **Model decision (decided here, don't re-research):** InstantID + SDXL-base-1.0 via diffusers — proven identity-preserving persona styling that fits 12 GB with `enable_model_cpu_offload()`. If InstantID's dependency set fights diffusers 0.39/transformers 5.13, the sanctioned fallback is **IP-Adapter FaceID (SDXL)** — same identity-from-one-photo family, lighter integration. Both depend on InsightFace face models, which are **research/non-commercial** — acceptable for this free product but MUST join the licenses page next to SadTalker/Wav2Lip's existing "re-audit before any monetization" flag.
- Contract: input file `selfie.jpg`; payload `{prompt, width: 1024, height: 1024}` where the backend sends `persona_description` + the identity-pinning suffix semantics from `app/engines/image_styler.py::IDENTITY_SUFFIX`; output `portrait.png`.

**Backend routing (mirror the home-worker talking-head pattern exactly):**
- `app/engines/home_worker_styler.py`: `HomeWorkerImageStyler` — checks `styler` in `gpu_router.worker_capabilities`, `submit_task(kind="styler", ...)`, `await wait_for_task(...)`, returns portrait bytes; raises `HomeWorkerUnavailable`/`GpuTaskFailed` for the caller to catch.
- `avatar_styling.stage_style` order becomes: Gemini styler → on `ImageStylerUnavailableError`, home-worker styler if advertised → on its failure/absence, existing raw-selfie fallback. `engine_notes` records which path produced the portrait (`gemini` / `styler-home` / `styling unavailable - raw selfie...`). The approval gate and every UI stay untouched — restyle simply starts producing real portraits when the worker is online.
- Tests: fake-agent pattern from `tests/test_mode_b_footage.py` (thread speaking `gpu_router`'s own lease protocol) — happy path, worker-lost-mid-style → raw-selfie fallback, offline → unchanged current behavior. Frontend `/licenses` row for InstantID/SDXL/InsightFace.
- **Owner gate (eyes)**: 2–3 personas styled from a real selfie of the owner — does it still look like *them*? Verdict here + update `specs/06-risks-and-future/01-risks.md` R2 (its "queued as follow-up" line becomes "implemented"; note the actual model used).

## Phase 3 — Wan vs LTX bake-off (~½ day, mostly unattended GPU time)

- Wait for a ≥10 GB-free VRAM window. Run `worker-agent/scripts/bakeoff.py` **detached with file logging** (reuse the quoted-`Start-Process`-`cmd` pattern from `deploy/tunnel/` — remember `Start-Process` silently mangles unquoted space-laden paths, found live) over 2 real scene images × both backends, `--duration 3.0`. LTX (~10 GB) downloads on first use.
- Deliverables: `bakeoff-results/{wan,ltx}-scene-*.mp4`, `timings.json`, minutes-per-clip for both on this card.
- **Owner gate (eyes)**: side-by-side viewing; verdict = quality-per-minute. Set `scene_gen_backend` accordingly (staying on "wan" is a valid verdict), record verdict + benchmarks in task-20a's gate line.

## Phase 4 — Full local verification (no deploy yet)

- Suites: backend (`455+` must stay green — new styler tests add to it), worker-agent pytest, frontend `tsc`/`eslint`/`next build`.
- Through **:8001** + dev frontend, one continuous pass: script → accept → Mode A HD (SadTalker path if Phase 1 landed) → avatar restyle producing a *styled* portrait (Phase 2) → Mode B generated footage on the bake-off-chosen backend (Phase 3). Screenshot evidence per the live-verification convention.
- If any phase was honestly abandoned at its timebox, verify its *fallback* path end-to-end instead, and say so plainly in Completion notes — an honest partial with working fallbacks is an acceptable outcome of this task; a silently broken capability is not.

## Phase 5 — Deploy (only now)

1. Commit(s) + push to GitHub.
2. Restart backend :8000 (kill by exact PID) → health 200 → confirm tunnel URL unchanged (if cloudflared restarted and the URL rotated: update `NEXT_PUBLIC_API_BASE_URL` on Vercel — **the correctly-named var, not `NEXT_PUBLIC_API_URL`** — and `FRONTEND_ORIGIN` in `.env`, then `vercel --prod --force`).
3. Restart the worker agent with the final `engines` list; `/api/meta/tier` shows the new capabilities.
4. Frontend redeploy only if frontend files changed (licenses page did → yes): `vercel --prod`.
5. Live browser smoke (gstack `browse`) on `https://aivideomaker-app.vercel.app`: login → tier badge → one HD avatar render → one styled restyle → generated-footage option clickable. **Live-only classes of bug (CORS, cookies, env-var bake-in) are exactly what curl misses — use the real browser.**
6. Update PROGRESS.md (this task's row), this file's Completion notes, `docs/USER-GUIDE.md`'s "honest note" about unstyled portraits (delete or soften it if Phase 2 shipped), R2/R12 risk statuses.

## Rollback

Every capability is config-gated at the agent (`engines` list) and tier-gated at the backend (chooser/styler fall through automatically when a capability isn't advertised). Rollback for any misbehaving engine = remove it from `config.toml`, restart the agent — no code revert, no redeploy. That property is why the iron rule is satisfiable at all; don't break it (no backend code path may *require* a new capability).

## Acceptance

- [ ] SadTalker renders a Mode A video via the home worker on :8001, with lease-loss falling back to Wav2Lip — or the sm_120 failure is documented at the 4-hour timebox and the capability honestly absent. Benchmark recorded either way.
- [ ] Avatar styling produces a genuinely styled, identity-preserving portrait via the local styler when the worker is online, raw-selfie fallback intact when offline; owner's identity verdict recorded; licenses page updated.
- [ ] Bake-off verdict recorded by the owner's eyes with timings for both backends; `scene_gen_backend` set deliberately.
- [ ] All three suites green; the single continuous :8001 E2E pass done with evidence.
- [ ] Deploy happened **after** all of the above, and the live smoke passed on the public URL.
- [ ] The live site was never running unverified code at any point before Phase 5.

## Owner gates in this task (schedule his eyes, don't decide alone)

1. Wav2Lip vs SadTalker realism (closes gate #1's remaining half).
2. Styled-portrait identity preservation (R2 fallback quality).
3. Wan vs LTX quality-per-minute (gate #3).

## Completion notes

*(execution session fills this in)*
