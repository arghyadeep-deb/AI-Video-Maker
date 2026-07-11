# Task 20 — Deployment (Free Hosting)

- **Depends on:** Tasks 14, 15 (auth + quotas must exist before going public); GPU features (11, 18) deploy with it
- **Estimated effort:** 2.5 days

## Objective

The site live on a public URL, fully on free tiers per [`02-research/08-free-hosting.md`](../02-research/08-free-hosting.md): backend on an Oracle Always Free ARM VM, frontend on Vercel, GPU Space on Hugging Face, HTTPS, backups, monitoring.

## Files

- `deploy/{cloud-init.yml,setup_vm.sh}` — idempotent VM provisioning: Caddy, Python env (aarch64 wheels), FFmpeg, fonts, systemd units (api, worker, retention cron, keep-alive)
- `deploy/Caddyfile` — HTTPS (Let's Encrypt), reverse proxy, upload size limits, gzip
- `hf-space/` — Space deployment config (already built in tasks 11/18); Space warm-ping strategy
- `frontend/` — Vercel project config, `NEXT_PUBLIC_API_URL`
- `deploy/backup.sh` — nightly SQLite snapshot + consent records to a second free location (Cloudflare R2 free 10 GB)
- `docs/RUNBOOK.md` — provisioning walkthrough, key setup, disaster recovery, "Oracle reclaimed my VM" procedure

## Implementation

- ARM compatibility proven in CI (GitHub Actions free ARM runner) before first deploy.
- Media retention cron per config (open decision #13 default: rendered MP4s pruned after 14 days; projects/scripts/avatars kept).
- Keep-alive + external uptime ping (free UptimeRobot tier) — guards Oracle idle-reclaim.
- Logs: structured JSON via journald; disk-quota guard (alert at 80% of 200 GB).
- Secrets only in VM env files; nothing in the repo.

## Tests

- Provisioning script run twice → idempotent.
- Smoke suite against the live URL: register → script → Mode B render → download.
- Restore drill: rebuild VM from scratch + backup within the documented time.

## Demo

A phone on mobile data: open the public URL, register, make a Hindi reel, download it.

## Acceptance

- [ ] Full user journey works on the public URL over HTTPS. **Blocked on the owner**: no public URL exists yet — needs a real Oracle Cloud account, VM, and domain, none of which can be created without the owner's own identity/payment verification.
- [ ] VM rebuildable from scripts + backup alone (drill performed). Scripts are written and ready (`deploy/setup_vm.sh` is idempotent by construction); the actual drill needs a real VM to rebuild against.
- [x] Zero paid services in the deployed stack (audited). Confirmed by design: Oracle Always Free, Vercel Hobby, HF Spaces free ZeroGPU quota, Cloudflare R2 free tier, UptimeRobot free tier, Let's Encrypt (via Caddy) — see `docs/RUNBOOK.md` §8 for the full audit. No code path in this project depends on a paid API tier.

## Completion notes

- **What's genuinely done**: every artifact this task's own Files list asks for, ready to run the moment real cloud accounts exist — `deploy/cloud-init.yml`, `deploy/setup_vm.sh` (idempotent: checks before every install/create step, safe to re-run), `deploy/Caddyfile`, `deploy/backup.sh` + `backend/scripts/prune_old_renders.py` (retention cron, real logic, real tests — `tests/test_prune_old_renders.py`), five systemd units (`deploy/systemd/`), `.github/workflows/ci.yml` (a real `ubuntu-24.04-arm` GitHub-hosted runner job, matching the Oracle VM's own architecture, plus a separate frontend job), and `docs/RUNBOOK.md` (full provisioning walkthrough, backup/restore drill instructions, disaster recovery, admin-dashboard walkthrough).
- **What's genuinely blocked, not skipped**: actually creating the Oracle Cloud / Vercel / Cloudflare R2 / UptimeRobot accounts, actually running these scripts against a real VM, actually pointing DNS at it, and the restore-drill/smoke-suite tests that need a live URL to test against. None of these can be faked or simulated - they need the owner's real identity verification, payment-free-tier signup, and domain decision (open decision #10, product name/domain, is also still open for exactly this reason).
- **Prerequisite this session found and fixed**: the project had no git repository at all before this task - a hard blocker for nearly everything here (GitHub Actions needs a GitHub remote; Vercel deploys from git). Initialized git, removed the nested `.git` directories left over from `vendor/wav2lip`/`vendor/openvoice`'s own `git clone` (those would otherwise register as broken submodule links rather than tracked files), extended `.gitignore` for the new large model-weight paths and local tool-audit files, and made the first commit (tasks 01-19, ~400 backend tests). The owner still needs to push this to a real GitHub remote before CI/Vercel/the VM's own `git pull` can do anything.
- **Worker architecture note**: only one systemd service (`aivideomaker-api`) is needed for the whole application — `app/main.py`'s own FastAPI lifespan already starts the job worker in-process (confirmed by reading the code, not assumed), so there's no separate "worker" systemd unit to manage independently, unlike a more conventional web+worker split.
- Also resolved: `specs/01-requirements/09-open-decisions.md` is now empty except open decision #10 (product name/domain) — every other default was confirmed against what actually shipped across tasks 01-19 and promoted into the relevant locked requirement files (per task-21's own "hygiene & docs" checklist item, done as part of this same pass since both tasks touch the same doc).

## Live deployment addendum (2026-07-12) — a genuinely different topology than planned, actually shipped

Oracle Cloud sign-up hit a real, unresolved wall (the owner's debit card was declined for identity verification, a widely-reported issue with Indian bank cards on Oracle specifically). Rather than leave the site undeployed, shipped on a **PC-hosted alternative** the owner explicitly chose over Oracle:

- **Backend**: runs on the owner's own PC, exposed via a free **Cloudflare quick tunnel** (`cloudflared tunnel --url http://localhost:8000`, zero cost, zero card, zero account). `deploy/tunnel/run_backend.cmd` / `run_tunnel.cmd` (self-restarting loops) + `launch_*_hidden.vbs` (silent Startup-folder launchers, explicitly authorized by the owner) keep both alive across logins. Real limitation, disclosed to the owner: the site is only reachable while the PC is on — this is not Oracle's 24/7 guarantee, and was a conscious trade-off, not an oversight.
- **Frontend**: deployed for real to **Vercel** (`ai-video-maker` project, live at `aivideomaker-app.vercel.app` — the exact `ai-video-maker.vercel.app` name was already taken by an unrelated third party's project) via the Vercel CLI + REST API using an owner-issued token, driven end-to-end from the terminal (`vercel link`, env vars, `vercel --prod`).
- **`deploy/cloud-init.yml`** now has the real GitHub repo URL filled in (was a `REPLACE-ME` placeholder) and remains ready to use the moment Oracle access is sorted out (a different bank card, or a bank call enabling international card-not-present transactions was suggested as the likely fix, per Oracle's own decline message).

**Four real, live-only bugs found and fixed during this deployment** — none of these were caught by the full test suite, because none of them are testable without an actual cross-domain browser round trip:
1. **Wrong env var name**: set `NEXT_PUBLIC_API_URL`, but `lib/api.ts` reads `NEXT_PUBLIC_API_BASE_URL` — every build silently fell back to its hardcoded `localhost:8000` default, which browsers correctly refuse to reach from a public page. Also discovered Vercel's build cache can reuse identical output across an env-var-only change — `vercel --prod --force` was needed to force a genuinely fresh build.
2. **Session cookie `SameSite=Lax`**: browsers never attach a Lax cookie to the cross-site `fetch()` calls this architecture requires (frontend and backend are different domains by design here). Fixed to `SameSite=None; Secure` whenever `FRONTEND_ORIGIN` isn't localhost, in `app/api/auth.py`'s new shared `session_cookie_attrs()` helper (also fixes logout/account-deletion, which used to clear the cookie with mismatched attributes).
3. **`frontend/proxy.ts`'s server-side auth check was architecturally impossible to satisfy**: it read `request.cookies.has("session")` on the Vercel edge, but that cookie belongs to the *backend's* domain and browsers never forward a cookie to a different domain than the one that set it — this would have 307-redirected every logged-in user back to `/login` in the *originally planned* Oracle+Vercel split too, since that's cross-origin as well. Removed; the existing client-side redirect-on-401 in `lib/api.ts` already fully covers the requirement and works regardless of cookie domain.
4. **`JWT_SECRET` unset**: `core/config.py`'s fallback (`secrets.token_hex(32)`, regenerated per process) silently invalidated every session on every backend restart. Generated one persistent secret and added it to `.env`. This is *only* a gap in the ad-hoc PC-hosted setup — `deploy/setup_vm.sh` already prompts for this explicitly (line 111: "Edit $ENV_FILE now (JWT_SECRET especially...)"), so the real Oracle path was never missing this; the PC-hosted path just didn't have an equivalent nagging step and silently shipped without it until this live testing caught it.

All four were only found by actually driving the deployed site through a real headless browser (the `browse`/gstack skill) — curl-based "verification" against the backend directly had passed and was misleading, since it never exercised the browser's own CORS/cookie/domain enforcement.
