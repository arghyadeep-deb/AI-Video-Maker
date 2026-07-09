---
title: AI Video Maker - SadTalker
emoji: 🗣️
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 5.0.0
app_file: app.py
pinned: false
license: other
---

# SadTalker ZeroGPU Space

Backs the "HD avatar" tier of AI Video Maker's Mode A
(`specs/03-design/04-mode-a-pipeline.md`). Called by
`backend/app/engines/talking_head/sadtalker_zerogpu.py` via `gradio_client`.

See `SETUP.md` for the one-time deploy steps (owner action — not automated
in this repo, since it involves fetching and running a third-party research
repo's pretrained weights).
