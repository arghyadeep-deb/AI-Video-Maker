# Task 02 — Script Generation

- **Depends on:** Task 01
- **Estimated effort:** 1.5 days

## Objective

`POST /api/projects` + `POST /api/projects/{id}/script`: description + language + duration → validated, scene-segmented, native-language script stored as version 1. Create page in the frontend.

## Files

- `backend/app/engines/script_llm.py` — `ScriptLLM` (google-genai SDK, structured output, retry/backoff, 429 → quota error)
- `backend/app/services/script_service.py` — prompt build, validation gate, versioning
- `backend/app/api/projects.py`, `backend/app/api/script.py`
- `backend/app/models/script.py` — Pydantic contract per [`01-requirements/02-script-generation.md`](../01-requirements/02-script-generation.md)
- `frontend/app/create/page.tsx` — description, language segmented control, duration presets, format toggle
- `frontend/lib/api.ts` — typed calls

## Implementation

- Prompt per [`03-design/02-script-flow.md`](../03-design/02-script-flow.md); model ID from config.
- Validation: Pydantic parse; scene count vs duration sanity; Unicode script-block check (Devanagari/hi); one auto-retry with error feedback, then honest failure.
- `usage` counter increment per call.

## Tests

- Unit: prompt contains language directive; validation catches romanized Hindi, digits, emoji; retry-then-fail path.
- Integration (stub LLM): project + version rows created; regenerate makes v2.
- Live smoke (manual, real key): one Hindi + one English script; native script verified.

## Demo

Type "बिज़नेस शुरू करने के 5 टिप्स", pick Hindi/60s → readable Devanagari script in scene chunks appears; SQLite shows the version row.

## Acceptance

- [x] Scripts generate natively in both languages with concrete English `visual_hint`s. (validated by the Hindi-script-block check + unit tests; English has no equivalent hard gate since Latin is unconstrained — see notes)
- [x] Malformed/wrong-language output never persists. (`test_script_validation_failure_never_persists` — project stays `drafting`, no version row written)
- [x] Quota exhaustion shows the "resets midnight PT" message, not a stack trace. (`QuotaExhaustedError` -> 429 with that exact hint; verified by test and by the live honest-failure screenshot below for the sibling case of a missing key)

## Completion notes

- **Live Gemini smoke test not run**: no `GEMINI_API_KEY` is available in this
  environment. All logic is covered by 36 automated tests (prompt building,
  the Devanagari/digit/emoji/scene-count validation gate, the one-retry-
  then-honest-failure path, quota-exhaustion mapping) using a `FakeLLM`/`StubLLM`
  standing in for `ScriptLLM`. I additionally drove the real `/create` → generate
  flow through a browser against the live (keyless) backend and confirmed it
  fails *honestly* — "GEMINI_API_KEY is not configured" renders on the page,
  no stack trace, no crash — which exercises the same error-envelope path a
  quota error would take. **You still need to do the spec's actual live smoke
  test** (one Hindi + one English script, real key) before fully closing this
  task's gate.
- **No-auth placeholder user**: added `app/core/deps.py:get_current_user_id`,
  returning a fixed dev user id until task-14 wires real JWT sessions. Every
  route already depends on it (not a hardcoded user_id), so task-14 only
  needs to change this one function's body.
- **API scope kept tight to task-02**: `api/projects.py` only implements
  create + get (get embeds `latest_script_version`, matching
  `03-design/09-api-endpoints.md`'s "Full project incl. latest script
  version"). List/delete arrive with task-13; scrap/accept/improve/manual-edit
  arrive with task-03/04.
- **Regeneration reuses the same endpoint** (`POST .../script` always inserts
  `n = max(n)+1`), per `03-design/02-script-flow.md`, even though task-02's
  own Objective line only mentions "stored as version 1" — regenerate-as-v2
  needed no extra code so I didn't gate it behind task-03.
- English scene text has no hard-fail equivalent to the Devanagari check
  (nothing to assert beyond "not empty") — only digits/emoji/wrong-language
  are enforced for `en`, matching the spec's own asymmetry (the script-block
  check exists specifically to "catch silent English fallbacks" for Hindi).
- `/project/[id]/script` is intentionally minimal (read-only scene cards, no
  editing) — task-03 rebuilds this exact route into the full review loop
  (select-to-improve, version history, accept/scrap). Building more here
  would just be thrown away.
- Added `google-genai` and `tzdata` to `backend/requirements.txt`. `tzdata`
  is needed because Windows doesn't ship an IANA tz database and
  `zoneinfo.ZoneInfo("America/Los_Angeles")` (used for the midnight-PT quota
  reset math) would otherwise fail on the dev machine.
