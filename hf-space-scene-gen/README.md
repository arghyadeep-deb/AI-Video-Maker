---
title: AI Video Maker - Scene Generator
emoji: 🎬
colorFrom: red
colorTo: orange
sdk: gradio
sdk_version: 5.0.0
app_file: app.py
pinned: false
license: apache-2.0
---

# Scene Generator ZeroGPU Space

Backs Mode B's "Generated footage" visual level
(`specs/04-tasks/task-23-quality-and-ops.md`). Given a scene's own text
description, generates a matching image (FLUX.1-schnell) then animates it
into a short real motion clip (LTX-Video) — replacing both stock-photo
keyword search (which often didn't match the scene) and the home GPU
worker's `scene_gen` engine (too slow on a 12GB laptop card without
`enable_model_cpu_offload()`, which ZeroGPU's H200 doesn't need).

Called by `backend/app/engines/scene_gen/zerogpu.py` via `gradio_client`,
`api_name="/generate"`.
