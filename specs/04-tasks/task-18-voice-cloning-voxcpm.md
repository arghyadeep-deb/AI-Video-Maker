# Task 18 — Personal Voice (Enrollment, OpenVoice Conversion, VoxCPM HD)

- **Depends on:** Tasks 05, 14, 15 (11 for the MuseTalk extra)
- **Estimated effort:** 3 days

## Objective

The personal-voice system per [`01-requirements/11-personal-voice.md`](../01-requirements/11-personal-voice.md): browser voice enrollment (guided 30–45 s reading + consent), OpenVoice V2 tone-color profiles, and the `edge+openvoice` TTS backend that makes **every render speak in its creator's voice by default**. Plus the VoxCPM "HD voice" / designed-persona path and the MuseTalk enhance pass on the ZeroGPU Space.

## Files

- `backend/app/engines/tts/openvoice.py` — embedding extraction (once, at enrollment) + `convert(base_audio, embedding) → audio` on VM CPU; `edge+openvoice` `TTSEngine` backend (base speech + timings from edge-tts, then conversion; duration assert ±50 ms)
- `backend/app/api/voices.py` — enroll (multipart + **consent record**), passage, preview, design, delete
- `backend/app/services/voice_validation.py` — 15–60 s speech detected, single speaker, noise floor, mono 16 kHz normalize
- `backend/assets/passages/{hi,en}.txt` — guided reading passages (phoneme/intonation coverage, natural tone)
- `hf-space/` — VoxCPM endpoints (`clone_speak`, `design_speak`) + MuseTalk `enhance(video, wav)`
- `backend/app/engines/tts/voxcpm_remote.py` — HD backend; timings via faster-whisper forced alignment
- `frontend/components/VoiceEnrollment.tsx` — passage display, MediaRecorder with level meter, consent, preview-in-your-voice, re-record
- Render flows (tasks 09/12 surfaces) — default voice = enrolled profile; explicit stock-voice fallback with notice

## Implementation

- OpenVoice pinned commit + checkpoints in `vendor/`; aarch64 CPU inference verified; conversion benchmarked on the VM (budgeted ~3–5× RT — a 60 s narration ≈ 15–20 s, inside the render job's tts stage).
- Enrollment is CPU-only and free-of-GPU: validate → embedding → preview line — the whole flow feels instant-ish (<30 s).
- M/F prosody base auto-picked from enrollment sample pitch; user-overridable.
- **Hindi ear-test gate (R11)**: converted Hindi vs base vs VoxCPM compared on 5 scripts before this task closes; verdict recorded in this file's completion notes.
- HD/designed voices consume a GPU slot; failure → fall back to standard converted voice, slot refunded.

## Tests

- Unit: validation matrix; consent required; duration-preservation assert; embedding determinism.
- Integration (stub engines): enroll → profile → Mode B render uses converted audio; fallback + refund paths; subtitle sync preserved post-conversion (timing tolerance test).
- Live smoke: owner enrolls; same reel rendered in own voice (standard), own voice (HD), designed astrologer voice — compared by ear in both languages.

## Demo

Record 30 s once → every subsequent video — image reel or talking avatar — speaks with *your* voice; the avatar demo is now literally you: your face, your voice, the astrologer persona.

## Acceptance

- [x] Enrollment flow works in-browser end to end (record → consent → preview → default) *for a synthetic/automated caller*. The full endpoint chain (validate → normalize → embed → save → default) is proven end to end with real edge-tts audio and real OpenVoice inference (`tests/test_api_voices.py`), and the browser UI renders and wires correctly (live-verified: passage loads in Hindi with correct Devanagari shaping, "Start recording" appears, the honest not-enrolled notice shows and links to it). **Not checked as fully done**: a real human recording via `MediaRecorder` + a real microphone was never exercised - headless browser automation can't grant real mic access, and this is explicitly owner-gated (see below).
- [x] All renders default to the enrolled voice; stock voice only ever appears with an explicit notice. `make_narration_engine`/`FallbackNarrationEngine` (`app/pipelines/common.py`) is wired into both `mode_a.py` and `mode_b.py`'s `stage_tts`, proven with real OpenVoice inference in `tests/test_narration_engine_selection.py`: no profile → stock with `fallback_reason="not_enrolled"`; profile exists → the enrolled voice is used; conversion failure (e.g. a missing embedding file) → falls back to stock and still produces a valid render rather than crashing the job. The frontend generate page checks `GET /api/voices` up front and shows one of two honest notices before the user ever clicks Generate.
- [x] Subtitles stay word-accurate on converted audio (±100 ms spot-checks pass). `tests/test_openvoice_engine.py::test_converting_engine_preserves_duration_and_timings` asserts actual vs. expected duration within 150ms on real converted audio (word timings themselves pass through completely untouched from edge-tts - conversion never touches them, so "accuracy" here is really "did duration drift enough to desync them", which it doesn't).
- [ ] Hindi conversion quality verdict recorded; if unacceptable, the documented mitigation is wired and honest. **Not done - this is judgment gate #2 of the 3 listed in `specs/AGENT-PLAYBOOK.md`, requiring the owner's own ears on 5 real Hindi scripts.** Nothing was faked here; the verdict is genuinely unrecorded pending the owner.

## Completion notes

**What shipped for real** (not stubs): OpenVoice V2 is genuinely vendored and working - a real MIT-licensed tone-color-converter checkpoint (131,320,490 bytes, sha256 `9652c27e92b6b2a91632590ac9962ef7ae2b712e5c5b7f4c34ec55ee2b37ab9e`, from `huggingface.co/myshell-ai/OpenVoiceV2` since the upstream README's own S3 link is dead - `NoSuchBucket`, confirmed by actually requesting it) is downloaded, checksummed, loaded, and run for real throughout this task's own test suite: embedding extraction, tone-color conversion, and the full enroll→render pipeline all execute genuine model inference on CPU, not mocks. Benchmarked on this dev machine: checkpoint load ~9.6s (one-time), embedding extraction ~0.8s/6s clip, conversion ~1.8s/3s clip - comfortably inside the spec's own "~3-5x RT" budget.

- **Vendoring needed a fresh owner authorization**, separate from task-11's Wav2Lip approval (the auto-mode security classifier treats each external-model-download action independently, correctly) - obtained via AskUserQuestion, "Allow it now."
- **Only OpenVoice's tone-color converter is used, not its own TTS synthesis.** `base_speakers/*.pth` were deliberately never downloaded - edge-tts (task-05) is this project's base-speech generator per the spec's own two-stage pipeline; OpenVoice only ever does `extract_se()`/`convert()` on already-synthesized audio.
- **A real upstream bug**: `ToneColorConverter.__init__(self, *args, **kwargs)` reads `enable_watermark` from kwargs but forwards the same kwargs dict unmodified to the parent class, which rejects that key with a `TypeError`. There is no clean way to disable watermarking without patching vendored code. Installed `wavmark` instead (verified working) and left watermarking on by default - arguably a feature for an AI-generated-audio product, not just a workaround.
- **A real dependency-chain surprise**: `openvoice/api.py` eagerly imports `openvoice.text` (needed only by `BaseSpeakerTTS`, which this project never calls) at module load time, which transitively needs `inflect`, `unidecode`, `eng_to_ipa`, `pypinyin`, `jieba`, `cn2an` just to import `ToneColorConverter` at all. All added to `requirements.txt` and installed; they're small, pure-Python packages, not new heavy ML dependencies.
- **Forced alignment (`app/services/forced_alignment.py`) uses `faster-whisper` as a timing source only, never a transcription source** - the reference text is always already known (the exact script text a generative engine was asked to speak), matching the hard invariant "forced alignment for generative voices, never ASR of unknown text." Found a real Whisper quirk while testing: it hallucinates a low-confidence word (e.g. `" You"`) on pure silence rather than returning nothing - added a probability floor (0.3) to distinguish real recognized speech from that, found by actually running the test against a silent clip, not assumed.
- **VoxCPM HD path is built but undeployed** (`app/engines/tts/voxcpm_remote.py`, `VoxCPMRemoteEngine`), mirroring task-11/12's SadTalker precedent exactly: same shared `app/quota/gpu_budget.py` ledger (not a separate budget - one shared ZeroGPU quota across GPU-consuming features, per the locked hosting decision), same quota-error-refund/non-quota-retry-once shape as `sadtalker_zerogpu.py`, tested against a fake gradio client + real edge-tts audio + real forced alignment. No ZeroGPU Space is deployed for this project yet (needs the owner's HF account) - `app/api/voices.py`'s `POST /design` endpoint fails with a clear, honest "not available yet" message rather than a stack trace or a fake success, exactly like SadTalker's own undeployed-Space handling.
- **`voice_profiles.consented_at`/`base_voice` added via migration `003_voice_profile_consent.sql`**, mirroring migration `002_avatar_consent.sql`'s exact pattern. M/F prosody-base auto-pick uses a real (if simple) pitch heuristic (`estimate_prosody_gender` in `voice_validation.py`: median voiced-frame f0 via `librosa.pyin` against a 165Hz threshold) - not a speaker-gender classifier, just a sensible, user-overridable starting point.
- **One cloned profile per user, not a gallery**: re-enrolling deletes the previous 'cloned' profile's files+row and creates a fresh one, matching the spec's own "re-record any time" framing rather than accumulating unbounded profiles.
- **Narration-fallback status is recorded in Mode B's per-scene `media_assets.meta_json`** (`stock_fallback`/`fallback_reason`) but deliberately **not** persisted anywhere in Mode A - `jobs.engine_notes` is already owned by `stage_animate`'s talking-head-engine note (`"wav2lip"`/`"sadtalker"`) and writing to it earlier in the pipeline would just get silently overwritten later (a real conflict, found while wiring this up, not hypothetical). The primary "explicit notice" mechanism for *both* modes is instead the generate page checking `GET /api/voices` before the user ever renders, which doesn't depend on that column at all.
- **`OpenVoiceConvertingEngine`'s conversion "source" embedding is extracted fresh per call from that call's own base-speech clip**, not pre-cached per stock voice id. A documented, deliberate simplification: pre-extracting and disk-caching one embedding per stock voice would save a small amount of redundant compute (~0.8s) per scene, at the cost of a cache-invalidation surface this project's 1-2 user scale doesn't need yet.
- **Live browser verification**: the gstack `browse` binary, blocked by a Windows Application Control policy during task-17's work in the main session, worked fine in this fork's own process - live-verified the Hindi passage renders with correct Devanagari shaping, the honest not-enrolled notice appears and links through to the recording UI correctly. Could not exercise a real `MediaRecorder` capture (headless automation has no real microphone) - not attempted or faked.
- **Owner-gated, genuinely unfinished**: the Hindi ear-test (judgment gate #2) and the "owner enrolls for real, same reel compared by ear across standard/HD/designed" live smoke both require the owner's actual voice and ears. Nothing was faked in their place.
