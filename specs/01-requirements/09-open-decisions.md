# Open Decisions

Everything that had a working default has been confirmed by what actually shipped (tasks 01-19) and promoted into the relevant locked requirement files:

| # | Question | Resolution | Where it's now locked |
|---|----------|-----------|------------------------|
| 1 | Avatar backdrop | Portrait's own generated background (confirmed) | [`04-mode-a-avatar.md`](./04-mode-a-avatar.md) |
| 2 | 3-second animated Mode A preview? | No (confirmed) | [`04-mode-a-avatar.md`](./04-mode-a-avatar.md) |
| 3 | Default subtitle style | Phrase-at-a-time; karaoke ships as a toggle (confirmed) | [`05-mode-b-image-video.md`](./05-mode-b-image-video.md) |
| 4 | GPU slot pricing | Superseded — no per-user slot count; GPU-minutes spent per video, ZeroGPU is worker-offline overflow only | [`10-hosting-accounts-quotas.md`](./10-hosting-accounts-quotas.md) |
| 5 | Mode A script length cap | 2 minutes, enforced in UI + API (confirmed) | [`04-mode-a-avatar.md`](./04-mode-a-avatar.md) |
| 7 | Visible watermark on output? | Off; metadata tag only (`comment=AI-generated`) (confirmed) | `04-tasks/task-19-moderation-consent.md` |
| 8 | Pexels/Pixabay attribution | Metadata + `credits.txt` in the download bundle (confirmed) | [`05-mode-b-image-video.md`](./05-mode-b-image-video.md) |
| 9 | Selfie/voice retention | Keep with a working delete button, stated in the privacy page | `frontend/app/privacy/page.tsx` (task-21) |
| 11 | Per-user daily credit numbers | Superseded — per-user credits dropped entirely; global provider caps instead (~700 LLM calls, ~200 images/day site-wide) | [`10-hosting-accounts-quotas.md`](./10-hosting-accounts-quotas.md) |
| 12 | Magic-link vs password auth | Password (argon2) + JWT cookies — no email dependency needed since the owner creates both accounts directly | [`10-hosting-accounts-quotas.md`](./10-hosting-accounts-quotas.md) |
| 13 | Rendered-video retention | Auto-prune MP4s after 14 days (confirmed) | `deploy/retention_cron.sh` (task-20) |

## Still genuinely open — needs the owner, not a default

| # | Question | Why it can't be resolved autonomously |
|---|----------|-----------------------------------------|
| 10 | Product name | "AI Video Maker" is a working placeholder. A real public name (and matching domain/subdomain choice for task-20's deployment) is a branding decision, not an engineering one. |

## Resolution protocol

When #10 is decided, move it into the appropriate locked requirement file and delete its row above — this file should then be empty except for this protocol note.
