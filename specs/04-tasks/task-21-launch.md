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

- [ ] A stranger on a phone goes from the public URL to a downloaded Hindi video in under 10 minutes, spending nothing, and the owner's dashboards show every quota behaving.
