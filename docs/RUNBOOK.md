# Runbook — Provisioning, Keys, Disaster Recovery

This is the operational companion to `specs/04-tasks/task-20-deployment.md`. It assumes
you (the owner) are doing this by hand once — none of it can be automated further without
your actual account credentials.

## 1. Prerequisites (one-time, needs your accounts)

| What | Where | Notes |
|---|---|---|
| GitHub repo | github.com | `git remote add origin <url> && git push -u origin main` from this checkout. Needed for CI (`.github/workflows/ci.yml`) and for the VM to `git clone`/`git pull`. |
| Oracle Cloud account | cloud.oracle.com | Always Free tier. Region choice matters — ARM capacity is sometimes "out of stock"; try a few regions if the first is unavailable. |
| Vercel account | vercel.com | Hobby (free) plan. Import the `frontend/` directory as the project root. |
| A domain or free subdomain | e.g. DuckDNS, or a domain you already own | Points at the Oracle VM's public IP for the backend; Vercel gives the frontend its own subdomain automatically. |
| Cloudflare account + R2 bucket | dash.cloudflare.com | Free 10GB tier, for off-VM backups. |
| UptimeRobot account | uptimerobot.com | Free tier — pings `/api/meta/health` every 5 minutes, guards against Oracle's idle-VM reclaim and tells you if the box goes down. |
| Free API keys | Gemini, Pexels, Pixabay | See `.env.example` / `README.md`. |

## 2. Provisioning the VM

1. Create the Oracle Always Free ARM instance (Ubuntu 24.04 aarch64, the smallest always-free shape).
2. Either:
   - Paste `deploy/cloud-init.yml` (with the real repo URL filled in) into Oracle's "cloud-init script" field at creation time, **or**
   - SSH in after creation and run `deploy/setup_vm.sh` manually (see that script's own header comment for both paths).
3. The first run of `setup_vm.sh` will stop and ask you to fill in `/opt/aivideomaker/deploy/.env` with real values (API keys, `JWT_SECRET`, `FRONTEND_ORIGIN`). Generate a JWT secret with:
   ```
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```
4. Re-run `sudo bash /opt/aivideomaker/deploy/setup_vm.sh` — this time it installs the systemd units, starts `aivideomaker-api`, and configures Caddy.
5. Point your domain/subdomain's DNS `A` record at the VM's public IP. Caddy requests its own Let's Encrypt certificate automatically on first request to that domain — no manual cert steps.
6. Create your (and the second user's, if any) account:
   ```
   cd /opt/aivideomaker/backend && .venv/bin/python scripts/create_user.py you@example.com --admin
   ```

## 3. Deploying the frontend

1. In Vercel, import the repo, set the project root to `frontend/`.
2. Set the environment variable `NEXT_PUBLIC_API_URL` to `https://<your-backend-domain>`.
3. Set `FRONTEND_ORIGIN` in the VM's `deploy/.env` to the Vercel deployment's own URL (CORS — `app/main.py` reads this at startup).
4. Deploy. Vercel redeploys automatically on every push to `main` once connected.

## 4. Backups (Cloudflare R2)

1. Create an R2 bucket (e.g. `aivideomaker-backups`) and an API token scoped to it.
2. On the VM: `rclone config` → new remote named `r2` → provider `Cloudflare` → paste the R2 credentials.
3. `deploy/backup.sh` (already installed as a nightly systemd timer by `setup_vm.sh`) uploads a gzipped SQLite snapshot to `r2:aivideomaker-backups/db/` every night at 03:00 UTC, and keeps 7 days locally as a fast fallback.
4. Verify it's actually working after the first night: `rclone ls r2:aivideomaker-backups/db/`.

## 5. Keep-alive

Add the VM's public health endpoint (`https://<domain>/api/meta/health`) to UptimeRobot on a 5-minute free-tier interval. This does double duty: it's your uptime alert, and the regular traffic itself counts as VM activity for Oracle's idle-reclaim heuristic.

## 6. Disaster recovery

### "Oracle reclaimed my VM" / VM lost entirely

1. Create a fresh Always Free ARM instance (same steps as §2).
2. Run `deploy/setup_vm.sh` against it — it clones the repo, installs everything, and fetches model weights fresh.
3. Restore the database:
   ```
   rclone copy r2:aivideomaker-backups/db/<latest>.db.gz /tmp/
   gunzip /tmp/<latest>.db.gz
   sudo systemctl stop aivideomaker-api
   sudo cp /tmp/<latest>.db /opt/aivideomaker/data/app.db
   sudo chown aivideomaker:aivideomaker /opt/aivideomaker/data/app.db
   sudo systemctl start aivideomaker-api
   ```
4. **Note**: rendered MP4s and selfie/portrait/voice-sample files themselves are NOT part of the SQLite backup — only the database rows (which reference their paths) are. If the VM's disk is gone, those media files are gone too; users can re-render videos for free (script/project rows survive), but will need to re-upload selfies/re-enroll voices. This is the accepted tradeoff for staying on free-tier backup storage (10GB R2 free tier wouldn't fit a media library anyway) — call this out to your users if it ever happens.
5. Point DNS at the new VM's IP (may take a few minutes to propagate).
6. Update Vercel's `NEXT_PUBLIC_API_URL` if the domain changed.

### Restore drill (do this once, before relying on it)

Repeat the disaster-recovery steps above against a *second*, throwaway Always Free instance while the real one is still running, to confirm the whole path actually works end to end before you need it for real. Record how long it took here once done — this satisfies task-20's own "Restore drill: rebuild VM from scratch + backup within the documented time" test.

## 7. Admin dashboard walkthrough

There's no separate admin UI page — the "admin dashboard" is the existing API surface, checked via `curl` or a browser:

- `GET /api/admin/usage` (requires an admin account, cookie auth) — today's `gemini_text`/`genai_image`/`zerogpu_seconds` counters against their daily caps.
- `GET /api/meta/health` — ffmpeg presence, DB migration state, which provider keys are configured.
- `GET /api/meta/tier` — current GPU tier (worker/zerogpu/cpu) shown honestly in the frontend's own tier badge.
- `journalctl -u aivideomaker-api -f` — live application logs (structured, since uvicorn/FastAPI logs to stdout which systemd captures via journald).

## 8. Zero-paid-services audit (task-20's own acceptance check)

Everything in this stack is free-tier: Oracle Always Free, Vercel Hobby, Hugging Face Spaces (ZeroGPU) free quota, Cloudflare R2 free tier, UptimeRobot free tier, Let's Encrypt (via Caddy), and the owner's own electricity for the GPU worker (task-20a). No credit card is charged anywhere in this design — Oracle's Always Free tier does require a card on file for identity verification at signup, but the resources this project actually provisions stay within the always-free allocation.
