# Task 21 — Polish & Launch

- **Depends on:** all prior tasks
- **Estimated effort:** 2 days

## Checklist

### Live verification
- [ ] E2E smoke (Playwright) against staging: register → **enroll voice** → describe → script → edit → improve → accept → Mode B (music + karaoke) → download; Mode A with reused avatar.
- [ ] Language×mode matrix on the live site: hi/en × A/B = 4 videos, **all narrated in the enrolled voice**, reviewed by a human (voice likeness included).
- [ ] Post-render tools exercised live (swap, scene re-render, mode re-render).
- [ ] Load sanity: 5 concurrent users queueing renders — fairness and VM stability hold.

### UX honesty pass
- [ ] Every failure mode has a human message + recovery: daily credit spent, global quota degradation, GPU slots exhausted, queue long, edge-tts down, no face in selfie, moderation decline.
- [ ] Credits, queue position, and GPU slots visible where relevant; generation pages survive refresh.
- [ ] Sample gallery (one video per language per mode) on the logged-out landing page — the pitch is the output.

### Design polish
- [ ] Consult frontend-design guidance; dark editorial theme consistent; real empty states; full mobile pass (most users will be on phones).

### Hygiene & docs
- [ ] `09-open-decisions.md` emptied — every default confirmed or overturned and promoted into requirement files.
- [ ] Licenses page: OFL fonts, model licenses (SadTalker/Wav2Lip research — **flagged**: this product is free, but re-audit before any monetization; VoxCPM Apache-2.0; MuseTalk), music track licenses, Pexels/Pixabay terms, edge-tts unofficial-status note, Vercel Hobby non-commercial note.
- [ ] ToS + privacy page: what's stored (selfies, voice samples, consent records), retention windows, deletion rights.
- [ ] RUNBOOK current; admin dashboard (usage, reports, jobs) walkthrough documented.
- [ ] No TODOs in code.

### Launch
- [ ] Announce link; watch admin usage dashboard through first real traffic; retention cron and backups observed working over 48 h.

## Acceptance

- [ ] A stranger on a phone goes from the public URL to a downloaded Hindi video in under 10 minutes, spending nothing, and the owner's dashboards show every quota behaving. **Blocked on task-20**: no public URL exists yet.

## Completion notes

Everything in this checklist that needs a *live* site (E2E smoke against staging, the language×mode matrix reviewed by a human ear, 5-concurrent-user load sanity, the actual "announce link" launch step) is genuinely blocked on task-20's deployment, which is itself blocked on the owner creating real cloud accounts. What follows is everything from this checklist that does NOT need live infrastructure, done now:

- **Hygiene & docs**:
  - `specs/01-requirements/09-open-decisions.md` emptied except open decision #10 (product name/domain — a branding call, not an engineering one, and it also determines what DNS record task-20 needs, so it's correctly deferred to the same moment). Every other decision confirmed against what actually shipped in tasks 01-19 and promoted into the relevant locked requirement files (`04-mode-a-avatar.md`, `05-mode-b-image-video.md`, `10-hosting-accounts-quotas.md`).
  - Licenses page (`frontend/app/licenses/page.tsx`): audited every model/dependency this project actually vendors or calls — Wav2Lip/SadTalker (research/non-commercial, flagged for re-audit before any monetization), OpenVoice V2 (MIT, verified from the real vendored `LICENSE` file), VoxCPM (Apache 2.0), MuseTalk (MIT, checked live via web search since training data can go stale on license terms - its own upstream deps like Whisper/DWPose carry separate licenses), Noto fonts (OFL), music tracks (CC BY 3.0, already documented in task-16), Pexels/Pixabay terms, edge-tts's unofficial status, Vercel Hobby's non-commercial clause.
  - Privacy & ToS page (`frontend/app/privacy/page.tsx`): what's stored, the real retention windows (14-day MP4 pruning, indefinite selfie/voice-sample retention until deleted), and deletion rights — cross-linked from `/responsible-use` (task-19) and the account menu.
  - `grep`'d the entire backend and frontend for `TODO`/`FIXME`/`XXX` — none found. Nothing to clean up here.
- **UX honesty pass**: audited (not newly built - this was mostly already true from earlier tasks, just verified here) that every listed failure mode has a real, human message: global quota exhaustion (task-15's `QuotaExhaustedError` → 429 with a "resets midnight PT" hint), GPU slots (`SadTalkerZeroGPUEngine`'s own budget check + honest tier badge), queue position (task-15's `QueuePosition` component), edge-tts down (`app/engines/tts/edge.py`'s own "unofficial API, could be down" message), no face in selfie (task-10), moderation/impersonation decline (task-19, just built).
- **Design polish / mobile pass / sample gallery / live verification / load sanity**: not attempted. These either need a live URL, real users, or (sample gallery) real rendered videos this dev environment has no API keys to produce - faking any of these would misrepresent what's actually been verified.

See `specs/04-tasks/task-20-deployment.md`'s own Completion notes for the deployment-artifact side of this same "everything short of live infra" pass (git init, deploy scripts, CI, RUNBOOK) — the two tasks were finished together since they share the same blocker.
