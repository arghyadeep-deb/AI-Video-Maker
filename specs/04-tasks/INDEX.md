# Tasks Index

One complete build — the order below is a dependency sequence, not a release plan. The site goes public at task-20 and launches at task-21 with everything included.

| Task | Demo |
|------|------|
| [01](./task-01-foundation.md) | FastAPI + Next.js + SQLite scaffold; env doctor |
| [02](./task-02-script-generation.md) | Description → validated native-language script |
| [03](./task-03-script-editor.md) | Scene-card editor; manual edit; versions; accept/scrap |
| [04](./task-04-improve-selection.md) | Select text → AI improve → keep/revert diff |
| [05](./task-05-tts.md) | edge-tts engine: 4 voices (hi/en), audio + word timings |
| [06](./task-06-subtitles.md) | Word timings → phrase-grouped ASS/SRT, Devanagari + Latin |
| [07](./task-07-job-worker.md) | SQLite job queue + progress polling UI |
| [08](./task-08-image-sourcing.md) | Scene hints → Pexels/Pixabay/nano-banana images |
| [09](./task-09-mode-b-assembly.md) | Full Mode B render: Ken Burns + subs + audio |
| [10](./task-10-avatar-styling.md) | Selfie + persona → portrait + approval gate |
| [11](./task-11-talking-head.md) | Portrait + audio → talking head (Wav2Lip CPU + SadTalker ZeroGPU) |
| [12](./task-12-mode-a-assembly.md) | Full Mode A render end-to-end |
| [13](./task-13-library-delivery.md) | Library, player, download, avatar reuse, delete |
| [14](./task-14-auth-accounts.md) | Invite-only login (1–2 users); everything user-scoped |
| [15](./task-15-quotas-fairness.md) | Global provider guards, tier badge, queue visibility |
| [16](./task-16-music-subtitle-styles.md) | Background music (ducked) + karaoke subtitles |
| [17](./task-17-post-render-tools.md) | Swap image, scene re-render, other-mode re-render |
| [18](./task-18-voice-cloning-voxcpm.md) | Personal voice: enroll once → **all videos in the user's own voice** (+HD/persona, MuseTalk) |
| [19](./task-19-moderation-consent.md) | Consent records + provenance (private-site scope) |
| [20](./task-20-deployment.md) | Live on Oracle VM + Vercel + ZeroGPU Space |
| [20a](./task-20a-gpu-worker.md) | RTX 5070 Ti worker: HD avatars + **generated-footage Mode B** (Wan/LTX per-scene clips) |
| [21](./task-21-launch.md) | Polish, live matrix, ToS/licenses, launch |
| [22](./task-22-local-hd-engines.md) | Local HD engines: SadTalker HD install + local portrait styler (R2 fallback) + Wan/LTX bake-off — all local, deploy last |

## Dependency chain

```
01 → 02 → 03 → 04
01 → 05 → 06
01 → 07
02 → 08
05,06,07,08 → 09
01,07 → 10
05,07,10 → 11
06,11 → 12
09,12 → 13
13 → 14 → 15
09 → 16
12,15 → 17
05,14,15 → 18 (MuseTalk extra also needs 11)
14,15 → 19
14,15 → 20 (GPU features 11,18 deploy with it)
11,15,18,20 → 20a
all-prior → 21
20a,21 → 22 (post-launch: finish the deferred GPU engines locally, deploy last)
```

## Suggested build order (one track)

`01 … 13` (the full single-user pipeline, both modes) `→ 14 → 15` (multi-user + shared-budget machinery) `→ 16 → 17 → 18 → 19` (feature completion + safety) `→ 20 → 21` (go live, launch).

Mode B still lands before Mode A within the pipeline phase: it exercises the whole architecture with the least model risk, so avatar-specific problems never block having a working product to deploy.
