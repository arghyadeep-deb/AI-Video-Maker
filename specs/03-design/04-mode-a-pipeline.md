# Mode A Pipeline — Avatar Video

Two jobs, separated by the human approval gate.

## Job 1: `avatar_styling` (seconds, cheap)

```
selfie upload → validate (face present? front-facing? via cheap face-detect)
→ ImageStyler.style(selfie, persona_description)   # nano banana, identity-pinned prompt
→ portrait saved → status: awaiting_approval
```

- UI shows portrait with **Approve** / **Regenerate** (edit persona text and retry).
- Approved portraits stored in `avatars` table — reusable in any future project (skip Job 1 entirely).
- Prompt template: persona description + fixed suffix: *"same person, preserve facial identity, front-facing, neutral-to-mild expression, shoulders-up portrait, photorealistic, 1024×1024"*.

## Job 2: `render_mode_a` (minutes, staged)

| Stage | % | What happens |
|-------|---|--------------|
| tts | 0–20 | `TTSEngine.speak(full script, user's voice profile)` → **edge-tts base speech + word timings, then OpenVoice tone conversion on the VM CPU → the user's own voice**; WAV 16 kHz for the animator. HD/designed voices route to VoxCPM on ZeroGPU instead |
| animate | 20–85 | `TalkingHeadEngine.render(portrait, wav)` → raw talking-head MP4. Wav2Lip (VM CPU) by default; SadTalker via ZeroGPU when a GPU slot is spent; engine logged on the job |
| assemble | 85–100 | FFmpeg: scale/pad to chosen format (blurred pad if aspect mismatch), burn ASS subtitles if toggle ON, loudnorm, final H.264 encode |

## Long-script handling

SadTalker render time grows linearly with audio length. Rule (open decision #5 default): Mode A available for ≤2 min scripts; UI steers 5-min scripts to Mode B. Progress for the animate stage is estimated from audio duration (SadTalker gives no usable progress callback) — show elapsed/estimated, not a fake precise bar.

## Engine selection (three-tier — [`11-gpu-worker.md`](./11-gpu-worker.md))

- **Owner's GPU worker online (common case): SadTalker HD is the default** — full head motion, renders a 60 s video in low minutes on the RTX 5070 Ti.
- **Worker offline, ZeroGPU slots left:** SadTalker via the Space as a rationed option; Wav2Lip default.
- **Both exhausted:** Wav2Lip on the VM CPU — always available, honest note in UI ("head still, lips animated").
- Routing is automatic with live UI state ("HD available" / "HD limited today"); mid-job worker loss re-queues and re-routes.
- Admin escape hatch: a bundled Colab notebook + `import-render` endpoint lets the owner render a stuck job manually; not exposed to end users.

## Failure modes

| Failure | Handling |
|---------|----------|
| No face detected in selfie | Reject at upload with clear message |
| Styling drifts identity | User regenerates (approval gate exists for this) |
| Animator crash / OOM | Job → failed with stderr tail captured; auto-suggest retry on Wav2Lip |
| ZeroGPU quota exhausted mid-job | Fall back to Wav2Lip with user notice; GPU slot refunded |

Diagram: [`05-flowcharts/04-mode-a-pipeline.mmd`](../05-flowcharts/04-mode-a-pipeline.mmd).
