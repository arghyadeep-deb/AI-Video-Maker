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

- [ ] Full user journey works on the public URL over HTTPS.
- [ ] VM rebuildable from scripts + backup alone (drill performed).
- [ ] Zero paid services in the deployed stack (audited).
