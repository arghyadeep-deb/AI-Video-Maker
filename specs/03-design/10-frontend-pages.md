# Frontend Pages (Next.js)

Seven routes. Visual language: dark, editorial, mobile-friendly (many users will be on phones). Consult the frontend-design skill during implementation; this file fixes structure, not pixels.

## `/login`, `/register` — Auth

Minimal email + password forms; register includes the free-product pitch ("3 free videos every day"). Post-login lands on the library. Session via JWT cookie; all other routes redirect here when unauthenticated.

## `/` — Library (home, per-user)

Grid of the user's project cards (thumbnail, title, language chip, status badge, duration). Primary CTA: **New video**. Header shows today's remaining credits ("2/3 videos"). Empty state sells the two modes with sample videos. Secondary: Avatars shelf + Voices shelf (cloned/designed) + account menu (delete account).

## `/create` — Describe

Big description textarea ("Describe the video you want…"), language segmented control (हिन्दी / English), duration presets (30 s / 1 min / 2 min / 5 min), format toggle (9:16 / 16:9). Submit → generating skeleton → redirects to editor. Scrap flow re-enters here with description prefilled.

## `/project/[id]/script` — Script editor (the review loop)

- Scene cards: number, editable text, ~seconds estimate.
- Select text in a card → floating **✨ Improve** button → instruction popover → inline old/new diff with **Keep / Revert**.
- Header: title, version history dropdown (restore), undo.
- Sticky footer: total words + estimated vs target duration, **Scrap** (danger, confirm) and **Accept & choose style** (primary).

## `/project/[id]/generate` — Mode select + setup

- Two large mode cards: **My Avatar** (Mode A) / **Image Video** (Mode B) with honest example frames.
- Mode A drawer: avatar picker (reuse approved) or new — selfie upload + consent checkbox + persona text + presets; portrait approval panel (Approve / Regenerate) when styling job returns; subtitles toggle. ≥2 min scripts: Mode A card disabled with explanation.
- Mode B: music toggle + track pick (small free library), subtitle style (phrase / karaoke).
- Shared: voice section — **defaults to "Your voice"** (enrolled profile, with a preview line); alternatives: "Your voice (HD)" with GPU-slot badge, designed persona voices, stock M/F as explicit fallback. First-time users hit the **voice enrollment flow** here (or from onboarding): guided passage display → browser recording with level meter → consent affirmation → preview in their new voice → confirm. **Generate video** CTA shows the credit it will spend.

## `/project/[id]/result` — Progress → player → post-render tools

- While queued: queue position ("2 jobs ahead of you"). While running: stage checklist (audio ▶ → visuals → subtitles → assembly) with live sub-progress, cancel button, quota-friendly error states with retry.
- When done: video player (streamed, range requests), **Download MP4** (+ SRT/credits), **Make another** → `/create`.
- Post-render toolbar: **Swap an image** (per-scene candidate picker), **Re-render a scene**, **Re-render in the other mode** — each showing its credit cost before confirming.

## Cross-cutting

- API client: thin typed fetch wrapper; job polling hook (`useJob(id)`, 1.5 s interval, stops on terminal status).
- All copy in English (UI localization explicitly out of scope); script content renders in its own language everywhere it appears.
- Error toasts always carry the backend `hint` (e.g. "Free daily limit reached — resets midnight PT").
