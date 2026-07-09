# Scope — One Complete Build

**Question.** What ships? What is staged for later?

**Decision.** **Nothing is staged.** This is a single complete build of a publicly hosted, multi-user, zero-cost product. The task order in [`04-tasks/INDEX.md`](../04-tasks/INDEX.md) is a dependency sequence, not a release plan — the product launches once, whole.

## The complete feature set

### Core pipeline
1. Invite-only login (1–2 known users); each user's projects, avatars, and videos are private to them.
2. Create page: description + language (hi/en) + duration + format (9:16 / 16:9).
3. Script generation (structured, scene-segmented, native-language).
4. Full review loop: accept / scrap / improve-selection with diff / manual edit, with version history.
5. Mode B end-to-end with **two visual levels**: Photo (stock images + Ken Burns, CPU-fast) and **Generated footage — a real AI-generated clip per scene on the owner's GPU** ("proper AI video"); both with music (auto-ducked) + word-timed subtitles (phrase or karaoke).
6. Mode A end-to-end: selfie upload + persona styling + approval gate + talking head + optional subtitles.
7. **Personal voice as the default**: onboarding records the user's voice once (~30–45 s guided reading); **every render in both modes is narrated in the user's own voice** (edge-tts base → OpenVoice CPU conversion). VoxCPM "HD voice" (GPU slot) and designed persona voices ("elderly wise astrologer") as deliberate alternatives; stock voices only as an explicit fallback. See [`11-personal-voice.md`](./11-personal-voice.md).
8. Background job pipeline with live stage progress, **fair multi-user queueing**.

### Post-generation control
9. Result page: in-browser playback + MP4 download (+ SRT/credits bundle).
10. **Swap-image picker**: per-scene image candidates, replace before or after render.
11. **Single-scene re-render**: fix one scene's audio/image without rebuilding the whole video.
12. **One-click re-render in the other mode** from the same accepted script.
13. Project library per user; reusable approved avatars; deletion (projects, avatars, account).

### Platform
14. **Hosting on free infrastructure** with the owner's API keys serving all users ([`10-hosting-accounts-quotas.md`](./10-hosting-accounts-quotas.md)).
15. **Owner's RTX 5070 Ti as the site's GPU worker** (when online) with three-tier routing: home GPU → ZeroGPU → CPU ([`03-design/11-gpu-worker.md`](../03-design/11-gpu-worker.md)); HD avatars, HD voices, and generated footage are simply available while the worker is up (no rationing needed for 2 users).
16. **Global quota guards only** (no per-user credits — unnecessary at this scale); honest degradation near provider caps.
17. Consent basics for selfie/voice (private site — no public moderation apparatus; risk R4 downgraded).
18. **MuseTalk quality pass** on avatar videos — worker-online feature.

## Quality bar

- Every pipeline stage has unit tests; each mode has an end-to-end smoke test.
- All external calls wrapped in typed clients with retry/backoff and honest quota errors.
- Every endpoint auth-guarded and quota-checked; all user data scoped by user id.
- No TODOs in shipped code; exclusions live in [`02-explicitly-out.md`](../06-risks-and-future/02-explicitly-out.md), not in comments.
