# API Endpoints (FastAPI)

All JSON; errors follow `{error: {code, message, hint?}}`. **Every route below `/api/` except `/api/auth/*` and `/api/meta/health` requires a valid JWT session; all resources are scoped to the authenticated user.** Mutating routes pass the credit/quota middleware first — quota failures return 429 with `{hint: "2 of 3 daily videos used", resets_at}`.

## Auth (fastapi-users)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/auth/register` | Email + password signup |
| POST | `/api/auth/login` / `logout` | JWT cookie session |
| POST | `/api/auth/verify` / `forgot-password` | Verification + reset flows |
| GET | `/api/me` | Profile + today's remaining credits |
| DELETE | `/api/me` | Full account deletion (rows + media) |

## Projects

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/projects` | Create: `{description, language, duration_s, format}` |
| GET | `/api/projects` | Library list (+ status, thumbnail) |
| GET | `/api/projects/{id}` | Full project incl. latest script version |
| DELETE | `/api/projects/{id}` | Delete project + media folder (confirm in UI) |

## Script (synchronous, seconds)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/projects/{id}/script` | Generate (or regenerate) → new version |
| POST | `/api/projects/{id}/script/improve` | `{version_id, scene_id, start, end, instruction?}` → `{old_span, new_span, proposed_scene_text}` (not persisted) |
| POST | `/api/projects/{id}/script/apply` | Persist a proposed improvement → new version |
| PUT | `/api/projects/{id}/script/scene/{sid}` | Manual edit `{text}` → new version |
| POST | `/api/projects/{id}/script/restore/{version_id}` | Undo/history restore → new version |
| POST | `/api/projects/{id}/script/accept` | Freeze version; project → `accepted` |
| DELETE | `/api/projects/{id}/script` | Scrap; project → `drafting` |

## Avatar (Mode A)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/avatars` | multipart: selfie + `{persona_description, name}` → `avatar_styling` job |
| GET | `/api/avatars` | Reusable approved avatars |
| POST | `/api/avatars/{id}/approve` | Approve portrait |
| POST | `/api/avatars/{id}/restyle` | New persona text → re-run styling job |
| DELETE | `/api/avatars/{id}` | Delete incl. selfie/portrait files |

## Voices

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/voices` | User's enrolled profile + designed profiles + stock fallbacks |
| GET | `/api/voices/passage?lang=` | The guided reading passage for enrollment |
| POST | `/api/voices/enroll` | multipart 30–45 s recording + consent → validate → OpenVoice embedding → profile (CPU, seconds; **the default voice for all renders**) |
| POST | `/api/voices/enroll/preview` | Synthesize a short line in the freshly enrolled voice for confirmation |
| POST | `/api/voices/design` | `{description}` → designed VoxCPM voice profile (GPU-slot gated) |
| DELETE | `/api/voices/{id}` | Delete profile + sample + embedding |

## Generation & jobs

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/projects/{id}/video` | `{mode, voice? (stock voice table ID - the enrolled/cloned voice, if any, always wins regardless), hd_voice?, subtitles?, subtitle_style?, music?, avatar_id?}` → `render_mode_a/b` job |
| POST | `/api/projects/{id}/rerender` | `{mode}` → `rerender_other_mode` job (same accepted script) |
| POST | `/api/projects/{id}/scenes/{sid}/rerender` | Re-render one scene (audio+image), re-splice video |
| GET | `/api/projects/{id}/scenes/{sid}/candidates` | Image candidates for swap picker |
| POST | `/api/projects/{id}/scenes/{sid}/image` | `{candidate_id}` → swap + re-splice |
| GET | `/api/jobs/{id}` | `{status, stage, progress, error}` — polled |
| POST | `/api/jobs/{id}/cancel` | Cancel between stages |
| POST | `/api/jobs/{id}/import-render` | multipart MP4 — Colab-manual path feeds the assemble stage |
| GET | `/api/projects/{id}/video` | Stream MP4 (range requests for the player) |
| GET | `/api/projects/{id}/video/download` | Download with filename + sidecar SRT/credits zip |

## Misc

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/meta/health` | ffmpeg present, keys configured, GPU budget remaining (admin sees usage counters) |
