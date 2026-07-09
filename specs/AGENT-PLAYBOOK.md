# Agent Playbook — How to Execute This Plan

You are the executing agent for AI Video Maker. You were not part of the planning conversations; **everything you need is written down.** This file tells you how to work. Follow it exactly — the plan's quality comes from its discipline.

## What you are building (30-second version)

A website for 1–2 known users, ₹0 forever: user types a topic → Gemini writes a scene-segmented script in Hindi or English → user refines it (accept / scrap / AI-improve a selection / manual edit) → the video renders **narrated in the user's own enrolled voice**, either as a talking AI avatar built from their selfie (Mode A) or as a visual video with photo or AI-generated footage per scene (Mode B) → they watch and download it. Backend on a free Oracle VM; heavy GPU work on the owner's RTX 5070 Ti via a pull-worker; assembly is always FFmpeg composing AI-made ingredients.

## Session-start ritual (every session, no exceptions)

1. Read `specs/README.md` (product summary + agent rules).
2. Read `specs/04-tasks/PROGRESS.md` (create it if missing — format below). Identify the current task: the first task whose deps are all `done` and whose status isn't `done`.
3. Read that ONE task file. Do not read other task files.
4. Read the `01-requirements/` and `03-design/` files that task links to. Read `02-research/` files only if the task touches that component.
5. Only then write code.

## The task loop

For the current task:

1. **Plan briefly** — map the task's file list to concrete edits; note the tests you'll write.
2. **Implement** — small commits, one concern each. Match existing code style.
3. **Test** — write the tests the task lists; run the whole suite, not just new tests.
4. **Verify acceptance** — walk the task's Acceptance checkboxes literally. Run the Demo section yourself where possible. Unchecked box = task not done.
5. **Record** — update `PROGRESS.md`; if you deviated from the spec, write what and why in the task file under a `## Completion notes` heading.
6. **Stop or continue** — one task per session is the default. If context is still fresh and the user says continue, loop.

### PROGRESS.md format

```
# Progress
| Task | Status | Date | Notes |
|------|--------|------|-------|
| 01 | done | 2026-07-10 | — |
| 02 | in-progress | 2026-07-11 | validation retry loop pending |
```

## Decision rules (memorize these)

- **The specs are law.** If code and spec disagree, the spec wins. If you believe the spec is wrong, STOP and ask the owner — never silently "improve" a locked decision.
- **Never add a paid dependency.** No trials, no card-required tiers, no "cheap" APIs. Substitutions go through the fallback column in `01-requirements/07-free-stack-lock.md` and the risk file — nowhere else.
- **Small ambiguities: decide and document.** If the spec doesn't cover a detail (a variable name, a minor UX wording), pick the obvious option and note it in Completion notes. Don't stall on trivia.
- **Big ambiguities: ask.** Anything touching money, scope, a locked decision, data deletion, or external services → ask the owner first.
- **Open decisions table** (`01-requirements/09-open-decisions.md`): use the listed default; when a task demo confirms/overturns one, move it into the proper requirement file and delete the row.

## The three judgment gates (do NOT decide these alone)

These are subjective quality calls that require the owner's eyes/ears. Prepare the artifacts, present them, record the owner's verdict in the task file:

1. **Task-11**: LongCat-Video Avatar 1.5 vs SadTalker — realism per GPU-second, and whether quantized LongCat fits 16 GB.
2. **Task-18**: OpenVoice Hindi tone-conversion ear test (5 scripts: converted vs base vs VoxCPM).
3. **Task-20a**: Wan 2.2 5B vs LTX-Video for generated footage — quality-per-minute on the 5070 Ti.

## Hard invariants (violating any of these is a broken build)

- Hindi in Devanagari, never romanized; script `text` goes verbatim to TTS (no digits/emoji/markdown).
- Language chosen once, flows everywhere; nothing translates.
- Nothing renders before the user's explicit Accept; improve-selection touches ONLY the selected span (byte-identical elsewhere).
- Every render defaults to the user's enrolled voice; stock voice only with a visible notice. Subtitle timings come from TTS word boundaries (or forced alignment for generative voices) — never ASR of unknown text.
- One audio clock: scene durations, image switches, crossfades, and subtitle cues all derive from TTS timings.
- Every external call goes through its engine interface (`ScriptLLM`, `TTSEngine`, `TalkingHeadEngine`, `ImageStyler`, `StockImages`) with retry/backoff and honest quota errors. No raw API calls in pipelines.
- All user-owned rows carry `user_id`; deletion removes rows + media files. Likeness artifacts (selfie/portrait/voice) require logged consent + working delete.
- The owner's GPU always yields to the owner (auto-yield, instant reclaim, schedule).
- Quota/GPU failures degrade honestly in UI copy — never silent, never a stack trace to the user.

## Environment traps (learned the hard way, don't relearn)

- Dev = Windows 11; prod = **aarch64 Linux** (Oracle ARM). Use `pathlib` everywhere; verify every wheel has an aarch64 build; CI must include an ARM runner from task-01.
- Owner's GPU is **Blackwell (sm_120)**: worker engines need PyTorch CUDA 12.8+ builds; SadTalker/Wav2Lip pin ancient deps — expect dependency surgery, document working pins.
- Devanagari: use codepoint offsets (not UTF-16) for selection APIs; test conjunct-heavy strings; subtitle rendering needs libass+HarfBuzz and the bundled Noto fonts via `fontsdir`.
- PowerShell 5.1 quirks on the dev machine: no `&&` chaining; UTF-8 needs explicit `-Encoding utf8`.
- Free-tier 429s are normal weather: every client maps them to "resets midnight PT"-style messages. Never auto-retry in a loop that burns quota.
- edge-tts is unofficial: wrap failures cleanly; the Supertonic fallback path is specced in `02-research/07`.

## Quality bar (from `01-requirements/08-scope.md`)

Unit tests per pipeline stage; an e2e smoke per mode; typed clients for all external calls; no TODOs in shipped code (deviations go to Completion notes / risk file); every endpoint auth-guarded past task-14.

## When something breaks that the spec didn't predict

1. Reproduce it minimally. 2. Check `06-risks-and-future/01-risks.md` — most failures are pre-planned there with a fallback. 3. If the fallback applies, implement it and note it. 4. If genuinely novel: fix forward if it's local; ask the owner if it changes architecture, cost, or scope.

Build order, dependencies, and per-task detail: `specs/04-tasks/INDEX.md`. Start there.
