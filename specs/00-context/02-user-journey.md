# User Journey (End to End)

```
Describe + pick language → Script generated → Review loop → Accept → Pick mode → Generate → Watch / download
```

## Step by step

0. **Register / log in.** The site is public; users sign up with email + password. The owner's API keys power everything — a user never configures anything. Their daily credits ("3 videos today") are visible from the start.
0.5. **Record your voice (once).** Before the first render, the user records ~30–45 s reading a guided passage — the sample from which their voice profile is built. From then on, **every video they make speaks in their own voice** ([`01-requirements/11-personal-voice.md`](../01-requirements/11-personal-voice.md)).
1. **Create.** User lands on the create page, types an approximate description ("a 1-minute video about why Saturn transit matters, in a wise astrologer tone"), and picks a language: Hindi or English.
2. **Script.** AI writes the script directly in that language. The script appears in an editor view, broken into scenes/segments.
3. **Review loop** (repeats until satisfied):
   - **Accept** → script locks, proceed to step 4.
   - **Scrap** → discard, back to step 1.
   - **Improve a part** → user selects text, optionally types an instruction ("make this funnier"), AI rewrites only the selection.
   - **Manual edit** → user edits the text inline themselves.
4. **Mode choice.**
   - **Mode A — My avatar**: upload a selfie, describe the persona ("astrologer with traditional attire, mystical background"). System generates a styled portrait for approval, then animates it speaking the script.
   - **Mode B — Image video**: no extra input needed; system picks topic-relevant images per scene.
5. **Voice.** Defaults to **their own enrolled voice**. Options: HD version of their voice (GPU slot), a designed persona voice ("elderly wise astrologer"), or a stock M/F voice as explicit fallback.
6. **Generate.** A background job runs the pipeline; the UI shows queue position and stage-by-stage progress (script → audio → visuals → assembly).
7. **Result.** Video plays in the browser; user downloads the MP4. Afterwards they can swap a scene's image, re-render a single scene, or re-render the same script in the other mode. Project, script, and video remain in their library.

## Journey invariants

- Language is chosen **once** at step 1 and flows through everything: script, improvements, narration, avatar speech, subtitles.
- No generation cost is incurred before explicit user actions (script accept, avatar approve, generate click) — important because free-tier quotas are the budget ([`03-zero-cost-constraint.md`](./03-zero-cost-constraint.md)).
- Every step is auth-scoped: users only ever see their own projects, avatars, and videos.

Diagram: [`05-flowcharts/02-user-journey.mmd`](../05-flowcharts/02-user-journey.mmd).
