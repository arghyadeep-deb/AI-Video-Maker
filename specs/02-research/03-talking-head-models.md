# Research — Open-Source Talking-Head Models

**Sources:** SadTalker (CVPR 2023, OpenTalker/SadTalker), Wav2Lip, MuseTalk (TMElyralab), LivePortrait — surveyed July 2026.

## The problem

Mode A needs: single still portrait + audio → video of the portrait speaking, with lip-sync and natural head motion. Must run on free compute.

## Candidates

| Model | Input | Strength | Weakness | CPU-viable? |
|-------|-------|----------|----------|-------------|
| **SadTalker** | 1 image + audio | Full head motion + blinks + expression from a single image — exactly our shape | ~GPU-hungry; slow (roughly real-time× several on a mid GPU, far worse on CPU); **research license (R5)** | Barely |
| **LongCat-Video Avatar 1.5** (Meituan, May 2026) | image/ref + audio | 2026-gen quality, Whisper-based lip-sync, **MIT license** (fixes R5 if adopted) | 13.6 B dense — exceeds the 5070 Ti's 16 GB without quantization; runs on ZeroGPU H200 but burns several GPU-minutes per video | No |
| **Wav2Lip** | video *or* image + audio | Battle-tested, light, runs on CPU acceptably | Lips only — head stays rigid; lower realism on a still image | Yes |
| MuseTalk | video + audio | Near-photorealistic, real-time on GPU | Designed to re-dub an existing *video*, not animate a still; needs a driving video | GPU only |
| LivePortrait | image + driving video | Premium quality motion transfer | Needs a driving performance video, not audio-driven | GPU only |

## Decision (hosted reality)

- **Default: Wav2Lip on the server CPU** — always available on the free VM, no GPU needed; honest quality note in UI ("lips animated, head still").
- **"HD avatar" option: SadTalker on the ZeroGPU Space** — full head motion, spends one of the site's daily GPU slots; the only audio-driven single-image model with full head motion, so it's the quality ceiling.
- **MuseTalk ships as the optional "enhance lips" pass (task-18)** — re-drives a rendered avatar video for sharper lips, same GPU-slot budget.
- **LongCat-Video Avatar 1.5: mandatory evaluation in task-11** — test on the ZeroGPU Space vs SadTalker (quality per GPU-second, quantized fit on the 5070 Ti). If it wins, it becomes the HD engine *and* retires the R5 license risk (MIT). Adopt-if-better, not assumed.
- LivePortrait rejected: needs a driving performance video, not audio. Higgsfield CLI rejected: MIT wrapper around a **paid** cloud (credit-billed Kling/Veo) — violates zero-cost.
- **Pixelle-Video** (Apache-2.0) noted as a *reference implementation* of the Mode B idea (topic → LLM → edge-tts → images → FFmpeg): validates our architecture; study its templates/segmentation, don't integrate (single-user tool; our review loop, personal voice, word-timed subtitles, and multi-user quota layer are the product).

## Free compute reality

- The VM has no GPU; all GPU inference happens on the HF ZeroGPU Space under a few-minutes-per-day budget ([`08-free-hosting.md`](./08-free-hosting.md)). Wav2Lip CPU timing on the 2-core ARM VM must be benchmarked in task-11 and reflected in queue estimates.
- An owner-side Colab notebook remains as an admin escape hatch for stuck jobs.
- SadTalker/Wav2Lip are research-licensed for non-commercial use — fine for a free product; **re-check licenses if this ever monetizes** (risk file). VoxCPM (Apache-2.0) and MuseTalk licenses noted in the launch licenses page (task-21).

## Integration notes

- Wrap as `TalkingHeadEngine` interface: `render(portrait, wav) → mp4`. Backends: `sadtalker-local`, `wav2lip-local`, `colab-manual`.
- SadTalker wants: front-facing portrait, WAV 16 kHz audio, `--still` flag for less head wobble at higher stability.
- Pin exact commits of both repos; they are research code and move without semver.

## Addendum (2026-07-18) — avatar modernization candidates (task-23 quality initiative)

The shipped engines (Wav2Lip CPU default, SadTalker HD) are 2023-generation and are now the biggest remaining "AI tell" in Mode A: blurry mouth region, stiff/uncanny head motion. Owner has prioritized closing this gap. Refreshed July-2026 landscape:

- **MuseTalk — promoted from "enhance lips pass" to primary upgrade candidate.** Already in this project's plan (license audited at task-21; task-22 notes it needs its own pinned venv, never installed). 2026 comparisons rank it among the highest-quality open lip-sync models, near-photorealistic, and it is efficient enough for the home worker. Cheapest path: it upgrades the *existing* Wav2Lip output style directly (same single-portrait input) without new architecture.
- **LatentSync (ByteDance, open)** — latent-space lip-sync, sharper than pixel-space Wav2Lip-era models; second candidate, needs license + VRAM check on the 12GB laptop 5070 Ti.
- **Hallo3** — best-in-class temporal consistency for long clips (minutes without identity drift); likely too heavy for our hardware, note only.
- **EchoMimic — rejected**: published comparisons report poor lip-sync accuracy + reference-image warping.
- **LongCat-Video Avatar 1.5** — judgment gate #1 remains open (was blocked on real GPU time); fold its evaluation into the same session as the MuseTalk venv install so one owner ear/eye-test settles the whole avatar tier.

**Plan of record**: build the MuseTalk venv on the home worker first (already-specced work, no new decisions), eye-test vs Wav2Lip/SadTalker; evaluate LatentSync + LongCat in the same sitting if time allows. Route through the existing `TalkingHeadEngine` interface — no pipeline changes.
