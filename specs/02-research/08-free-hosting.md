# Research — Free Hosting for a Public Video-Rendering Site

Verified July 2026. This is the hardest free-tier problem in the product: video rendering needs a real, always-on machine — most "free hosting" (serverless, sleep-after-idle dynos) cannot do it.

## Oracle Cloud Always Free — the backend home

- **As of June 2026 the Ampere ARM allocation was cut in half: 2 OCPU / 12 GB RAM total** (was 4/24), plus the AMD micro instances and **200 GB block storage**, ~10 TB egress/month. Still by far the most capable always-free VM anywhere.
- Enforcement of the cut is rolling out inconsistently; **plan for 2/12, treat anything more as a bonus.**
- 2 ARM cores handle: FastAPI, SQLite, edge-tts calls, FFmpeg (a 60 s 1080p Mode B render in low single-digit minutes — slower than a laptop, fine for a queue), and Wav2Lip CPU inference (slow; queue-visible).
- ARM caveat: all Python wheels must have aarch64 builds (FFmpeg, onnxruntime, torch CPU do); test in CI with an ARM runner.
- Known friction: free-tier capacity in popular regions is often "out of stock" at signup — pick region carefully; VMs can be reclaimed if idle (ours won't be, and a keep-alive cron guards it).

## The owner's PC — the real GPU (RTX 5070 Ti, 16 GB)

The strongest free compute in the whole stack is the owner's own gaming PC, attached as a **pull-based worker** ([`03-design/11-gpu-worker.md`](../03-design/11-gpu-worker.md)): outbound HTTPS polling (works behind home NAT, nothing exposed), lease/heartbeat so a sleeping PC just re-queues jobs. 16 GB VRAM runs every model in the plan — SadTalker (~4 GB), VoxCPM (~8 GB), MuseTalk, and LTX-Video for animated scenes. Caveats: availability is intermittent by design (hence the three-tier routing), residential upload speed bounds result transfer (tens of MB per video — fine), and **Blackwell (sm_120) needs PyTorch built for CUDA 12.8+** — 2023-era research repos may need dependency surgery (risk R12).

## Hugging Face ZeroGPU — the overflow budget

- Free Spaces can use **ZeroGPU** (H200 slices), **Gradio SDK only**.
- Quota is per *requesting* account: free accounts ≈ **a few minutes of GPU per day** (~300 s programmatic; resets 24 h after first use). This is a **tight daily budget, not a rendering farm**.
- Design consequence: GPU features (SadTalker, VoxCPM cloning, MuseTalk pass) are metered as "GPU slots/day" product-wide; the UI shows remaining slots. Default avatar path stays Wav2Lip-on-CPU.
- The backend calls the Space via `gradio_client`; the Space holds the models and exposes `render(portrait, wav)`.

## Vercel free (Hobby) — the frontend

Next.js deploys free with SSL and CDN; API calls go to the VM over HTTPS (Caddy + a free subdomain — DuckDNS or a cheap-to-free domain the owner already has). Vercel Hobby forbids commercial use — fine for a free product; noted in licenses review.

## Rejected options

| Option | Why not |
|--------|---------|
| Render/Railway/Fly free tiers | Sleep-on-idle, tiny CPU/RAM, hour caps — can't render video reliably |
| Google Colab as the backend | Session-based, not a server; stays as the manual GPU escape hatch |
| Cloudflare Workers/Pages functions | No FFmpeg/long jobs on free CPU limits |
| Supabase (auth/DB) | Fine service, but the VM already runs SQLite + fastapi-users — fewer moving parts, zero external dependency |

## Storage math

200 GB disk ÷ ~40 MB per 60 s 1080p video ≈ ~5,000 videos. Retention policy (open decision #13): auto-delete rendered videos after N days (user re-renders from the kept script/project if needed); selfies/portraits are tiny.
