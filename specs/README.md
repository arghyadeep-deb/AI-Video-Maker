# AI Video Maker — Build Plan

A **zero-cost, publicly hosted** website: visitors **register**, describe the video they want, AI writes a script in their chosen language (**Hindi / English**), they refine it in a review loop (accept / scrap / AI-improve a selected part / edit manually), record their voice once so that **every video is narrated in their own voice**, then pick a generation mode: **Mode A** — a talking AI avatar built from their selfie and styled per a persona description (astrologer, businessman, …), or **Mode B** — an image-based video with narration, background music, and word-timed subtitles. They watch the result on the site and download it.

The **site owner provides all API keys**; users just sign up and use it. Every component runs on free tiers or open-source software: Gemini Flash (script + avatar styling), edge-tts + OpenVoice (narration in the user's voice + subtitle timing), SadTalker/Wav2Lip (talking head), VoxCPM (HD voice cloning), Pexels/Pixabay (images), FFmpeg (assembly), hosted on an Oracle Always Free VM + Vercel + a ZeroGPU Space — with the **owner's RTX 5070 Ti PC attached as a pull-based GPU worker** that makes HD avatars, HD voices, and animated scenes the default whenever it's online. Because the free quotas are shared by all users, **per-user daily credits and fair queueing are core features, not afterthoughts**. This is one complete build — there is no v1/v2 split; everything in scope ships together.

## Mandatory reading order

1. [`00-context/`](./00-context/) — what we are building and the zero-cost constraint
2. [`01-requirements/`](./01-requirements/) — locked-in product decisions (incl. hosting, accounts, quotas)
3. [`02-research/`](./02-research/) — verified free-tier facts (LLM, TTS, talking heads, images, hosting)
4. [`03-design/`](./03-design/) — architecture, pipelines, data model, API, frontend
5. [`04-tasks/`](./04-tasks/) — see [`04-tasks/INDEX.md`](./04-tasks/INDEX.md); execute in dependency order task-01 → task-21
6. [`06-risks-and-future/`](./06-risks-and-future/) — known risks and explicit exclusions

Flowchart sources live in [`05-flowcharts/`](./05-flowcharts/) as `.mmd` (Mermaid) files; design docs embed them.

## Rules for the executing agent

**Full operating manual: [`AGENT-PLAYBOOK.md`](./AGENT-PLAYBOOK.md) — read it first, every session.** Summary:

- Load only ONE task file at a time. Do not preload all tasks.
- Re-read [`01-requirements/`](./01-requirements/) and the relevant [`03-design/`](./03-design/) file before starting a task.
- Each task file has `Depends on:` at the top — do not start a task until its deps are green.
- After each task: run its acceptance-criteria checks; only then proceed.
- **Never introduce a paid dependency.** If a free tier disappears, stop and consult [`06-risks-and-future/01-risks.md`](./06-risks-and-future/01-risks.md) for the fallback before substituting anything.
- This is a public multi-user product: every endpoint added after task-14 must be auth-guarded and quota-checked by default.
