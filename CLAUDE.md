# AI Video Maker

A zero-cost, invite-only (1–2 users) website: topic → AI script (Hindi/English) → user review loop → video narrated in the user's own voice, as a personal AI avatar (Mode A) or a visual video with photo or AI-generated footage (Mode B).

## The plan is law

The complete build plan lives in [`specs/`](./specs/README.md).

**MANDATORY FIRST READ, every session: [`specs/AGENT-PLAYBOOK.md`](./specs/AGENT-PLAYBOOK.md).** It is the complete operating manual — session-start ritual, task loop, decision rules, judgment gates, hard invariants, environment traps. Follow it exactly; do not improvise around it.

Quick orientation: tasks execute in dependency order from [`specs/04-tasks/INDEX.md`](./specs/04-tasks/INDEX.md), **one task at a time** (01 → 21, incl. 20a); progress is tracked in `specs/04-tasks/PROGRESS.md`; a task is done only when its acceptance checkboxes pass.

## Hard rules (never violate)

- **₹0 forever**: never introduce a paid dependency, trial, or card-requiring service. If a free tier breaks, consult `specs/06-risks-and-future/01-risks.md` for the wired fallback — do not substitute on your own.
- **Language**: Hindi + English only. Hindi in Devanagari, never romanized.
- **The script is the only editable artifact**; nothing renders before explicit user Accept.
- **Every render defaults to the user's enrolled voice** (edge-tts base → OpenVoice conversion); stock voice only with an explicit notice.
- Subtitle timing comes from TTS word boundaries — never ASR.
- Likeness artifacts (selfie, portrait, voice sample) require logged consent records and working deletion.
- Owner's GPU (RTX 5070 Ti worker) yields to the owner's own work — auto-yield, instant reclaim, schedule (see `specs/03-design/11-gpu-worker.md`).

## Progress tracking

Maintain `specs/04-tasks/PROGRESS.md`: one line per task — status (todo/in-progress/done), date, and any deviation from spec (with why). Create it at task-01.

## Environment notes

- Dev machine: Windows 11 (this repo); production: Oracle Always Free ARM VM (aarch64 Linux) — keep everything pathlib/ARM-compatible, CI on an ARM runner from task-01.
- Owner's GPU is Blackwell (sm_120): PyTorch CUDA 12.8+ builds required for worker engines.
- Free API keys used: `GEMINI_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY` (see `.env.example` from task-01).
