# Problem Statement

Making a decent short video today requires either on-camera confidence + editing skill, or paid tools (HeyGen, Synthesia, InVideo) that charge per video and mostly ignore Indian languages. There is no free path from "I have an idea for a video" to "here is a finished video in my language, optionally fronted by *me*".

We are building a **deployed website for 1–2 known users** (the owner + at most one other person) that closes that gap end-to-end, free:

- **Private access on a public URL.** Invite-only login (no open registration); the **owner supplies all API keys** — users never configure anything. Because only 1–2 people share the free quotas, each video can spend them *generously* — including tens of GPU-minutes of real generative footage per video.
- **Idea → script.** The user types an approximate description of the video they want; AI writes a full script directly in their preferred language (Hindi or English — not translated after the fact).
- **User owns the script.** Nothing is rendered until the user is satisfied: they can accept it, scrap it entirely, select any part and ask AI to improve just that part, or edit the text themselves. This loop repeats as long as needed.
- **Script → video, two ways.**
  - **Mode A — Personal AI avatar**: the user uploads a selfie and describes a persona (astrologer, businessman, teacher, …); we generate a styled avatar that looks like them and speaks the script in their own voice.
  - **Mode B — Visual video**: per-scene visuals over TTS narration with background music and synced subtitles. Visuals come in two quality levels: **stock/AI images with cinematic motion** (fast, CPU) or **fully AI-generated video footage** — a real generative clip per scene, rendered on the owner's GPU (the "proper AI video" mode).
- **Watch, then download.** The finished video plays on the site and downloads as an MP4.
- **Completely free to run.** No paid API, no subscription, no per-video cost — for the owner *or* the users. Free-tier APIs + open-source models + free hosting only. Because those free quotas are shared by everyone, per-user daily credits and fair queueing are part of the product. See [`03-zero-cost-constraint.md`](./03-zero-cost-constraint.md).

## Who it's for

Creators, students, and small businesses in India who want reels/shorts-style content in Hindi or English without a camera, an editor, or a budget. The astrologer/businessman persona examples come straight from the target use case: personality-fronted advice/explainer content.

## Explicitly out of scope (not deferred — just not this product)

- Post-generation video *editing* (trims, cuts, transitions) — only the script is editable, before generation.
- Languages beyond Hindi / English (Bengali was considered and dropped 2026-07; the pipeline can take it later).
- A third "mixed" mode (avatar + b-roll) and direct auto-posting to platforms.

Full list with rationale: [`06-risks-and-future/02-explicitly-out.md`](../06-risks-and-future/02-explicitly-out.md).
