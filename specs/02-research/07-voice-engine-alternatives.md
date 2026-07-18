# Research — Voice Engines (edge-tts, OpenVoice, VoxCPM, Supertonic, Voicebox — and the 2026-07-18 IndicF5 addendum below)

Analyzed July 2026. Verdict up front: **every video is narrated in the user's own voice** via a two-stage pipeline — **edge-tts base speech → OpenVoice V2 tone-color conversion on the VM CPU**. VoxCPM on ZeroGPU is the "HD voice" upgrade + designed-persona voices; Supertonic is the edge-tts-outage fallback; Voicebox rejected. One `TTSEngine` interface, pluggable backends.

## OpenVoice V2 — the personal-voice workhorse ([github.com/myshell-ai/OpenVoice](https://github.com/myshell-ai/openvoice))

- **MIT licensed** (V1 and V2, since April 2024) — commercial-safe, no research-license trap.
- Core idea: separates **tone color** (speaker timbre) from **style/prosody**. A base TTS speaks; the tone-color converter re-voices the audio into the target speaker extracted from a short reference clip.
- **The converter runs 3–5× real-time on a modern CPU core** — a 60 s narration converts in ~15–20 s on the free VM. This is what makes "every render in the user's voice" affordable with zero GPU.
- **Cross-lingual zero-shot**: reference-clip language and speech language don't need to match training languages. Native base-language list (en/es/fr/zh/ja/ko) does **not** include Hindi — but our base speech comes from edge-tts `hi-IN` voices and the converter only touches timbre. Quality for Hindi is plausible but **must be ear-tested (risk R11, task-18)**.
- Enrollment artifact: a tone-color embedding computed once per user from their 30–45 s recording; conversion is then embedding + audio → audio, duration-preserving (word timings survive within tolerance).

## The candidates

| | edge-tts (current) | Supertonic | VoxCPM2 | Voicebox |
|---|---|---|---|---|
| What | Cloud neural voices (unofficial MS) | 99 M-param on-device ONNX TTS | 2 B-param tokenizer-free TTS | Desktop app wrapping 7 OSS engines |
| Hindi/English | ✅ both, Azure quality | ✅ both (31 langs) | ✅ both (30 langs) | ✅ both |
| Word timings | ✅ **native** (WordBoundary) | ❌ none — needs forced alignment | ⚠️ via stable-ts post-pass | ❌ none |
| Hardware | none (tiny lib) | **CPU, real-time, even Raspberry Pi** | **~8 GB VRAM GPU** | varies by engine |
| Voice cloning/design | ❌ | separate Voice Builder tool | ✅ cloning + **voice design from text description** | ✅ cloning |
| License | unofficial (risk R1) | MIT / OpenRAIL-M | **Apache-2.0** (commercial-safe) | MIT (app) |
| Setup weight | pip install | small ONNX models | multi-GB model download | full app/Docker |

## Role assignment

- **edge-tts stays the base layer.** Still the only option with zero setup, zero hardware, studio Azure voices, and *native* word timings (our subtitle system's backbone). It now generates the **prosody base** that OpenVoice converts into the user's timbre; word timings pass through conversion unchanged.
- **OpenVoice V2 = the default voice of every render** (see above).
- **Supertonic replaces Parler-TTS as the R1 fallback.** If Microsoft kills the endpoint: MIT-licensed, CPU-only, real-time, English + Hindi covered, ships as ONNX with a Python SDK — far lighter than Parler-TTS. Cost: word timings must come from forced alignment (faster-whisper against the known script text — already our designed fallback path in [`03-design/06-subtitle-timing.md`](../03-design/06-subtitle-timing.md)). Hindi quality must be ear-tested before being declared ready (99 M params is small; naturalness may lag Azure noticeably).
- **VoxCPM = the "HD voice" upgrade + designed personas (task-18).** Apache-2.0, 2 M hours of training data, 48 kHz output. Where OpenVoice *converts* edge-tts audio (timbre transfer, prosody stays stock), VoxCPM *generates* speech in the cloned voice end-to-end — higher fidelity, more "really them". It also does **voice design from text** ("elderly wise astrologer voice, warm and slow"). Needs ~8 GB VRAM → ZeroGPU Space, daily GPU-slot budget, deliberate per-render choice. Timings via stable-ts / forced alignment.
- **Voicebox: skipped.** It's an aggregator *app*, not an engine — its engines (Chatterbox, Qwen3-TTS, Kokoro) are individually available, and our backend wants a library/API, not a desktop studio plus a second server to babysit. VoxCPM + Supertonic cover cloning and CPU-fallback better with less dependency surface.

## Design consequence (already true, now load-bearing)

All of this lands behind the single `TTSEngine` interface (`speak(text, voice_profile) → (audio, word_timings)`). Backends: `edge+openvoice` (default — base speech then CPU tone conversion), `edge` (stock-voice fallback, explicit notice), `supertonic` (edge-tts-outage fallback, alignment-augmented), `voxcpm_remote` (HD/designed voices, GPU slots). Config-selected, pipeline-invisible.

## Addendum (2026-07-18) — expressiveness upgrade for Hinglish narration: IndicF5

**Problem, observed live**: the shipped default (edge-tts base → OpenVoice conversion) produces the user's *timbre* but keeps edge-tts's flat stock *prosody* — the single biggest "this is AI" tell in short-form video. Compounding it: scripts now deliberately come out in Hinglish (task-23 script-quality fix), and edge-tts `hi-IN` voices read Devanagari-transliterated English loanwords stiffly. The owner has prioritized fixing this (task-23).

**New primary candidate — IndicF5** ([hf.co/ai4bharat/IndicF5](https://huggingface.co/ai4bharat/IndicF5), AI4Bharat, 330M):

- Voice cloning is its *native operating mode*: reference audio + that audio's transcript → generated speech in the cloned voice, prosody and all. Our existing 30–45s enrollment recording is directly reusable as the reference prompt (transcript of it required — one-time, can be produced at enrollment).
- Trained on 1417h of Indian speech (Rasa, IndicTTS, LIMMITS, IndicVoices-R) across 11 Indian languages incl. Hindi — Indian-accent English loanwords are in-distribution, unlike any Western multilingual model.
- The open `hinglish-tts` project ([harrrshall/hinglish-tts](https://github.com/harrrshall/hinglish-tts), built on IndicF5) adds mixed-script normalization (IndicXlit) + a small duration patch, scoring 4.70/5.0 intelligibility on code-mixed eval — direct evidence the base model handles Hinglish well with light preprocessing.
- Delivery options, in preference order: (1) AI4Bharat's own public HF Space via the proven `gradio_client` pattern (zero hosting — verify per-call latency and quota first); (2) home GPU worker engine (330M is small; well within the 12GB laptop 5070 Ti even alongside other engines); (3) own ZeroGPU Space once HF hosting unblocks (~2026-08-16).
- **Open items before adoption**: license must be confirmed for the licenses page (AI4Bharat models are typically permissive but IndicF5's exact terms + its explicit "clone only with permission" use-policy need recording alongside our existing consent machinery — which already satisfies the permission requirement); word timings don't exist → subtitle timing uses the already-designed forced-alignment path (faster-whisper against known script text, `03-design/06-subtitle-timing.md`) — the same path Supertonic/VoxCPM already require; and the decisive gate is an **owner ear-test** (Hinglish script lines, IndicF5-cloned vs current edge+openvoice) — same protocol as judgment gate #2.

**Backup candidate — Chatterbox Multilingual** (Resemble AI, MIT, 500M, [github](https://github.com/resemble-ai/chatterbox)): zero-shot cloning from ~10s reference, 23 languages incl. Hindi, 8–16GB VRAM. Held back because it takes a single `language_id` per utterance — Hinglish code-switching quality is unproven and must be ear-tested before it could win. Kokoro-82M (task-23 spike) remains a distant third: has word timestamps but no cloning (would still need OpenVoice on top, keeping the flat-prosody problem it's meant to solve).

**Role if adopted**: new `indicf5` backend behind the same `TTSEngine` interface, becoming the enrolled-voice default; `edge+openvoice` demotes to always-available fallback (network/quota failures degrade to it silently-honestly, per the existing `FallbackNarrationEngine` pattern); `edge` stock-voice notice path unchanged. No pipeline code changes — config-selected, exactly as this file's design consequence intended.
