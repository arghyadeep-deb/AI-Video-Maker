# Task 10 — Avatar Styling + Approval Gate

- **Depends on:** Tasks 01, 07
- **Estimated effort:** 2 days

## Objective

Selfie upload (with consent checkbox + face validation) → nano banana persona styling → portrait approval gate → reusable `avatars` records.

## Files

- `backend/app/engines/image_styler.py` — `ImageStyler.style(selfie, persona) → portrait` (genai image edit, identity-pinned template per [`02-research/04-free-image-generation.md`](../02-research/04-free-image-generation.md))
- `backend/app/services/face_check.py` — cheap face presence/frontal check (mediapipe or opencv haar — pick lightest)
- `backend/app/api/avatars.py` — CRUD, approve, restyle
- `backend/app/pipelines/avatar_styling.py` — job: validate → style → `awaiting_user`
- `frontend/components/AvatarSetup.tsx` — upload+preview, consent checkbox (blocking), persona text + preset chips, portrait approve/regenerate panel

## Implementation

- Presets: Astrologer, Businessman, Teacher, Doctor, News Anchor — each a well-crafted persona prompt the user can edit.
- Regenerate = restyle job with edited persona text; previous portraits kept until approval (pick between attempts).
- Approved avatar persists (name, persona, paths) and appears in the reuse shelf.

## Tests

- Unit: prompt template pins identity clauses; consent flag required by API (400 without).
- Integration (stub styler): upload → job → awaiting_user → approve → avatar approved; restyle loop.
- Live smoke (manual, real key + real selfie): astrologer + businessman personas; identity subjectively preserved.

## Demo

Upload selfie, pick "Astrologer" → seconds later a portrait of *you* in saffron robes with a mystical study behind you; regenerate with tweaked text; approve — it appears in the avatar shelf.

## Acceptance

- [x] No upload without consent checkbox; no styling without a detected face. (both enforced synchronously at upload, before any DB row or job is created — `test_upload_without_consent_is_rejected`, `test_upload_without_a_detected_face_is_rejected`)
- [x] Approval gate blocks any animation work until approved. (the styling job parks itself at `awaiting_user` via a new `AwaitingUser` worker signal — it never reaches `done`; nothing downstream exists to consume an unapproved avatar yet, and `render_mode_a` (task-11/12) will read `avatars.approved` before using one)
- [x] Approved avatars reusable across projects without re-styling. (`GET /api/avatars` returns only `approved = 1` rows; portraits persist on disk keyed by avatar id, not by project)

## Completion notes

- **`cv2.CascadeClassifier` doesn't exist in this installed opencv-python-headless build (5.0.0)** — confirmed by direct probe (`AttributeError: module 'cv2' has no attribute 'CascadeClassifier'`), and the wheel's bundled `cv2/data/` directory is empty besides `__init__.py`. Used `cv2.FaceDetectorYN` (YuNet) instead — a modern, still-lightweight DNN face detector bundled as an API in this same build. Its ONNX model isn't bundled either; pulled the standard Apache-2.0 model from the OpenCV Zoo GitHub repo (note: had to fetch via `media.githubusercontent.com/media/...`, not `raw.githubusercontent.com`, since the file is stored via Git LFS and the raw host serves the LFS pointer text, not the binary — a 131-byte "download" was the tell). Bundled at `backend/assets/face_detection_yunet.onnx`.
- **Found and documented a pre-existing asset-path inconsistency**: task-01 bundled fonts at `backend/assets/fonts/` (outside `app/`); task-06 bundled the subtitle ASS template at `backend/app/assets/subtitle_template.ass` (inside `app/`) — both per their own task files' literal wording, so neither is "wrong", but they disagree. Put the new face-detection model at `backend/assets/` (matching task-01's precedent) and got the `Path(__file__).resolve().parents[N]` depth wrong on the first pass (copied task-06's `parents[1]` pattern without checking it matched the actual file location) — caught immediately by a real `FaceCheckError: model not found` when testing against a real image, not by unit tests alone (the model-not-found path wasn't itself under test). Fixed the offset; left both existing locations alone rather than moving files and risking a wider unrelated diff. A future cleanup task should pick one location.
- **Design doc's failure-modes table ("No face detected → reject at upload with a clear message") drove a structural choice**: the face-presence check runs synchronously inside the `POST /api/avatars` request handler, not as a pipeline stage — so a bad selfie fails immediately with a 400, never touching the job queue or writing an avatar row. Consent is checked the same way. A real face check needed access to a real photo to prove the positive case, not just reject — used OpenCV's own official face-detection tutorial sample image (`samples/data/messi5.jpg`, BSD, opencv/opencv repo) as a committed test fixture (`backend/tests/fixtures/test_face.jpg`) so `test_detects_a_real_frontal_face` is a genuine positive-case test, not just a noise-image negative case.
- **New job-lifecycle primitive: `AwaitingUser`** (`app/jobs/registry.py`), a pipeline-step exception the worker now handles (`app/jobs/worker.py`) by marking the job `status = 'awaiting_user'` (with `finished_at` set, so the fairness scheduler treats the user's turn as over) instead of `done`, and running no further stages. This is the first job in the system that doesn't end in done/failed/cancelled — designed generically since task-11's Wav2Lip/SadTalker parking and any future human-in-the-loop step can reuse it without new worker plumbing.
- **Added a consent column that was missing from the locked schema**: `avatars` had no `consented`/`consented_at` fields (unlike `voice_profiles`, which already had one from `001_init.sql`) even though the hard invariant ("likeness artifacts require logged consent records") applies now, not just at task-19. Added via `002_avatar_consent.sql`. This bumped `PRAGMA user_version` from 1 to 2, which broke three tests in `test_migrations.py`/`test_meta.py` that hardcoded `== 1` — fixed by deriving the expected version from the migrations directory instead of hardcoding it, so the next migration won't repeat this.
- **Kept previous portrait attempts on disk, not just the latest one**: the task's own Implementation notes call for "previous portraits kept until approval (pick between attempts)". The first pass overwrote a fixed `portrait.png` filename on every restyle, silently destroying earlier attempts. Fixed by naming each attempt `portrait_<job_id>.png` and pointing `avatars.portrait_path` at the latest; old files survive on disk. **Not fully implemented**: there's no UI or endpoint yet to browse back through earlier attempts and pick one — only the latest is ever shown. Regression test: `test_restyle_keeps_the_previous_portrait_file`.
- **Found and fixed a real frontend bug via live browser verification, not by reading code**: after a "Regenerate" restyle, the portrait `<img>` kept showing the *previous* attempt's picture even though the server-side file and the DB's `persona_description` had both genuinely updated (verified independently via direct `curl` + a raw pixel probe through ffmpeg) — because `avatarPortraitUrl(avatarId)` returns the exact same URL both times, so the browser's own HTTP cache served the stale image without ever re-requesting. Fixed by cache-busting with the styling job's id (`?v=${jobId}`) in `AvatarSetup.tsx`'s portrait `<img>`, and re-verified live (direct URL fetch + fresh page reload) that the new persona's color shows correctly. The `/avatars` list page's grid thumbnails use the same bare (non-busted) URL — currently safe because the UI has no way to restyle an *already-approved* avatar, but this is a latent version of the same bug if that ever changes; flagging rather than fixing preemptively since it's unreachable today.
- **`ImageStyler` (nano banana selfie edit) and the pre-existing `GenaiFallbackImages` (task-08's stock-image fallback) both parsed inline image bytes out of a Gemini response with duplicated logic** — factored the shared bit into `app/engines/genai_image_utils.py:extract_image_bytes` and had both call it, rather than leaving two copies to drift.
- **No real GEMINI_API_KEY was available**, so `ImageStyler.style()` itself was only exercised against the "no key configured" honest-failure path (`test_image_styler_conforms_expected_interface`) and, for the rest of the pipeline/API surface, a `StubImageStyler`. **Owner action still needed**: a real live smoke test per the task's own Tests section ("astrologer + businessman personas; identity subjectively preserved") once a Gemini key is available — this is a judgment call (does the styled portrait still look like *you*?) that no automated test can make.
- **`GET /{avatar_id}`, `GET /{avatar_id}/selfie`, and `GET /{avatar_id}/portrait`** aren't in the locked endpoint table but were necessary additions: the approval-gate UI needs to poll one specific (possibly not-yet-approved) avatar's state, and `selfie_path`/`portrait_path` are server-local filesystem paths with no way to reach the actual image bytes over HTTP otherwise. Same category of small, documented gap-filling as task-03's `GET /script/versions`.
- **`/avatars` is a real, working page but isn't linked from anywhere yet** — there's no library/home page or nav bar in this product yet, and Mode A itself isn't selectable in `/project/[id]/generate` until task-12 wires up `render_mode_a`. Built it anyway so task-10's own deliverable (upload → style → approve) is actually usable and testable now, matching the pattern already set by task-07's `/debug/jobs`.
