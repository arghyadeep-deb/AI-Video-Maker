# Deploying the SadTalker Space (owner action)

This directory is deployable as-is once SadTalker itself is vendored in —
that step isn't automated here since it means cloning a third-party
research repo and downloading its pretrained weights (same category of
action as `backend/vendor/wav2lip/`, done under explicit authorization
during task-11 for that repo; do the same review for this one).

1. Clone SadTalker at a **pinned commit** (not `main`) into `hf-space/SadTalker/`:
   ```
   git clone https://github.com/OpenTalker/SadTalker.git SadTalker
   cd SadTalker && git checkout <pin a specific commit SHA here>
   ```
2. Download its pretrained checkpoints using SadTalker's own official
   `scripts/download_models.sh` (or the equivalent documented in its
   README at the pinned commit) into `hf-space/SadTalker/checkpoints/`.
3. Create a Space on huggingface.co: **Gradio SDK**, **ZeroGPU** hardware.
4. Push this `hf-space/` directory (including the now-vendored `SadTalker/`
   subfolder and its checkpoints) to the Space's git remote.
5. Set `SADTALKER_SPACE_ID` (e.g. `yourusername/ai-video-maker-sadtalker`)
   and, if the Space is private, `HF_TOKEN` in the backend's `.env`.
6. Verify: call it once via `gradio_client` manually (or let
   `backend/app/engines/talking_head/sadtalker_zerogpu.py` hit it through
   the normal render_mode_a pipeline once task-12 wires that up) with a
   real portrait + short WAV, and confirm a playable MP4 comes back.
7. Record the LongCat-Video Avatar 1.5 vs SadTalker judgment-gate verdict
   (specs/AGENT-PLAYBOOK.md's gate #1) in
   `specs/04-tasks/task-11-talking-head.md` once you've compared them.
