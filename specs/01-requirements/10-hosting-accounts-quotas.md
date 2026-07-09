# Hosting, Accounts, Quotas

**Question.** How does a zero-cost product serve the public with the owner's API keys?

**Decision.** One free VM runs everything; the owner's keys are a shared pool guarded by per-user daily credits, a global kill-switch per provider, and fair queueing. Users register with email + password and only ever see: describe → script → video → download.

## Hosting topology (locked; facts in [`02-research/08-free-hosting.md`](../02-research/08-free-hosting.md))

| Piece | Where | Free basis |
|-------|-------|-----------|
| Backend (FastAPI + worker + FFmpeg + SQLite + media) | **Oracle Cloud Always Free ARM VM** (2 OCPU / 12 GB / 200 GB as of June 2026) | Always Free |
| Frontend (Next.js) | **Vercel** free tier | Hobby plan |
| HTTPS + reverse proxy | Caddy on the VM | OSS |
| **Primary GPU: owner's home PC** (RTX 5070 Ti, 16 GB) | Worker agent, outbound-only connection to the VM ([`03-design/11-gpu-worker.md`](../03-design/11-gpu-worker.md)) | Owner's electricity — ₹0 cash |
| Overflow GPU (worker offline) | **Hugging Face ZeroGPU Space** (Gradio) | ~minutes of H200 per day |
| Last-resort animator/voice | Wav2Lip + OpenVoice on the VM's CPU | OSS |

**Three-tier GPU consequence:** while the owner's PC is online, HD avatars (SadTalker), HD voices (VoxCPM), MuseTalk, and animated hero scenes are plentiful and HD becomes the *default*; when it's offline, the site degrades honestly to ZeroGPU rationing, then to CPU engines. The UI always tells the truth about which tier is live ("HD available" / "HD limited today").

## Accounts (locked — private site, 1–2 users)

- **Invite-only**: no open registration. Accounts are created by the owner (`backend/scripts/create_user.py`, CLI-only — no public register endpoint); email + password (argon2-cffi) + JWT cookies, hand-rolled rather than via `fastapi-users` (task-14: that library's storage layer needs an async ORM adapter this raw-sqlite3 codebase doesn't have — see task-14-auth-accounts.md's own Completion notes). No email verification needed — the owner knows both users, so magic-link auth (open decision #12) was dropped in favor of plain password login.
- All data rows still carry `user_id` and queries are user-scoped (cheap discipline, keeps deletion clean), but there is no anonymous-public attack surface: no signup throttles, no disposable-email filters, no report/takedown queue.

## Quotas (simplified — the budget is generous for two people)

Per-user credits are **dropped**. With 1–2 users, daily free quotas are effectively personal: ~750 LLM calls and ~250 images *each*. What remains:

1. **Global guards only**: counters per provider with honest degradation near caps (image gen → stock-only; a friendly "free tier resets midnight PT" if something is exhausted). These exist as safety rails, not rationing.
2. **GPU budgeting inverts**: instead of scarce "slots," each video may spend **tens of GPU-minutes on the owner's 5070 Ti** — enough for fully generated footage and frontier avatars. ZeroGPU minutes remain the worker-offline overflow.

**Key pool**: config accepts a list of keys per provider and rotates on 429 — resilience only (ToS ties quota to the developer, not the key).

## Queueing (simplified)

Plain FIFO, one media job at a time on each compute tier (VM CPU and GPU worker run in parallel). Queue position shown; with two users, contention is rare by nature.
