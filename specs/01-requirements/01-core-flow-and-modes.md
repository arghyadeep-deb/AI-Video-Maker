# Core Flow and the Two Modes

**Question.** What is the non-negotiable product shape?

**Decision.** A strictly ordered pipeline with a human gate between script and video, and exactly **two** video generation modes.

## The pipeline (locked)

```
Description + Language → Script → Review loop (human gate) → Mode choice → Video generation → Delivery
```

- No video generation ever starts before the user explicitly **accepts** the script.
- Mode is chosen **after** script acceptance; the same accepted script can be **re-rendered in the other mode with one click** (spends a video credit).

## The two modes (locked)

| | Mode A — Personal AI Avatar | Mode B — Image Video |
|---|---|---|
| Visual | Talking avatar generated from the **user's selfie**, restyled per a **persona description** (astrologer, businessman, teacher, …) | Sequence of topic-relevant images, one or more per script scene |
| Audio | Avatar speaks the script (TTS + lip-sync) | TTS narration over the images |
| Subtitles | Optional toggle (default ON) | **Required** — synced to audio |
| Extra inputs | Selfie upload + persona description | None |
| Spec | [`04-mode-a-avatar.md`](./04-mode-a-avatar.md) | [`05-mode-b-image-video.md`](./05-mode-b-image-video.md) |

## Why exactly two modes

They cover the two content archetypes of the target user: personality-fronted content (Mode A: "the astrologer tells you…") and faceless explainer content (Mode B: reels-style narration). Anything else (screen recordings, templates, stock video clips, mixed avatar+b-roll) is explicitly excluded — see [`06-risks-and-future/02-explicitly-out.md`](../06-risks-and-future/02-explicitly-out.md).

## Post-render controls (in scope)

Timeline editing stays out, but three targeted fix-ups are in: **swap a scene's image** (candidate picker), **re-render a single scene**, and **re-render the whole script in the other mode**. All operate on the frozen accepted script — the script remains the only editable artifact.
