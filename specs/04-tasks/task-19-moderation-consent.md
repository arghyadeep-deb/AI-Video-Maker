# Task 19 — Consent Basics & Provenance (Private Site)

- **Depends on:** Tasks 14, 15
- **Estimated effort:** 0.5 day

## Objective

The site serves 1–2 known users, so the public-abuse apparatus (reports, takedowns, signup throttles, moderation queues) is **out**. What stays is the responsible floor for likeness tech: consent records, an impersonation guard, and provenance tagging.

## Files

- `backend/app/moderation/consent.py` — logged consent record (timestamp) per avatar/voice profile; deletion always available
- Styling/script prompt templates — persona guard clauses
- `frontend` — consent affirmations on selfie + voice upload; short "responsible use" page

## Implementation

- **Likeness consent**: affirmation + logged record per selfie/voice profile; delete buttons everywhere the artifact appears.
- **Persona guard**: styling prompt hard-forbids "make me look like <named real person>" edits; Gemini's built-in safety refusals pass through honestly on scripts.
- **Provenance**: metadata tag in output MP4s (`comment=AI-generated`); visible watermark stays off.
- If the site is ever opened beyond 1–2 users, the full public-safety package (reports, takedown, abuse throttles, text gates) becomes a prerequisite — noted in [`06-risks-and-future/01-risks.md`](../06-risks-and-future/01-risks.md) R4.

## Tests

- Unit: consent-record-required paths; persona-guard clauses present in prompts.
- Integration: styling with an impersonation-style persona description is declined cleanly; deleting a profile removes sample + embedding + consent record linkage.

## Demo

Selfie and voice enrollment both require the affirmation; output MP4 carries the AI-generated metadata tag.

## Acceptance

- [x] Every likeness artifact (selfie, portrait, voice sample) has a logged consent record and a working delete. Selfies/avatars: `avatars.consented`/`consented_at` (task-10) + `DELETE /api/avatars/{id}/selfie` and `DELETE /api/avatars/{id}`. Voice samples: `voice_profiles.consented`/`consented_at` (task-18) + `DELETE /api/voices/{id}`. Both enrollment endpoints now share one `require_consent()` helper (`app/moderation/consent.py`) instead of duplicating the reject-and-stamp logic.
- [x] Impersonation-style persona requests are declined with a clear message. `app/moderation/persona_guard.py`'s `check_persona_description()`, wired into both avatar creation and restyle. Real regex-based heuristic (resemblance verb + a 2+-word capitalized name), tested against 5 generic personas that must pass and 5 impersonation phrasings that must be declined.
- [x] Outputs carry the provenance tag. `-metadata comment=AI-generated` added to both pipelines' final ffmpeg mux step; verified via a real ffprobe read of the actual rendered file in both `test_mode_a_pipeline.py` and `test_mode_b_pipeline.py`'s existing happy-path tests, not a new mocked test.

## Completion notes

- **Consent de-duplication**: `avatars.py` and `voices.py` each independently implemented "reject if `consent` is false, else insert with `consented=1, consented_at=<timestamp>`" (voices.py's own comment already said "same rejection shape as avatars.py" - now it's actually the same code, via `require_consent()` in the new `app/moderation/` package). No new schema or audit table was added: the row's own `consented`/`consented_at` columns already satisfy "a logged consent record (timestamp) per avatar/voice profile" at this site's 1-2 user scale - a separate audit-log table would be scope creep for a private site where the full public-abuse apparatus is explicitly out.
- **Persona guard is a narrow, testable heuristic, not a general NER-based filter**: it fires on a resemblance verb ("look like", "resemble", "dress as", "become", "as if I'm/you're") immediately followed by a 2+-word capitalized sequence, e.g. "make me look like Tom Cruise". This is deliberately narrow so ordinary persona descriptions with incidental capitalization ("Indian classical musician", "British detective") aren't false-flagged - tested explicitly for both directions. A known, documented gap: single-name mononyms ("look like Madonna") aren't caught, since the 2+-word requirement is the only reliable proper-name signal available without a real named-entity model - locked in as an explicit test (`test_single_name_mononyms_are_not_caught`) so the gap stays visible rather than silently assumed fixed. Matches the task's own framing: "the responsible floor for likeness tech" at 1-2 known users, not an adversarial-user-proof filter.
- **Provenance tag placement**: added at the very last ffmpeg mux step in both pipelines (the `loudnorm` + `faststart` finishing pass that already exists in both `mode_a.py::_finalize` and `mode_b.py::stage_finalize`) rather than a separate re-mux pass, since both already re-encode/remux the container at that point - free to attach container-level metadata there.
- **Scope note - what's still "1-2 known users" and staying that way**: per the task's own framing and R4 in `06-risks-and-future/01-risks.md`, no reports/takedown/abuse-throttle machinery was added - if the site is ever opened beyond 1-2 users, that full package becomes a prerequisite, not something this task tries to partially cover.
- **Frontend**: both `AvatarSetup.tsx`'s and `VoiceEnrollment.tsx`'s existing consent checkboxes (real `useState`-backed affirmations already gating the upload button, from tasks 10/18) now link to a new static `/responsible-use` page (no auth required, explaining own-likeness-only, personas-not-impersonation, and the AI-generated tag) rather than needing new consent UI - it already existed and was already correct, just needed the explanatory page to point to.
- 388 backend tests passing (11 new: `test_persona_guard.py`, `test_consent.py`, plus additions to `test_api_avatars.py` and the mode_a/mode_b pipeline tests). Frontend `tsc --noEmit`/`eslint`/`next build` all clean, including the new `/responsible-use` static route.
