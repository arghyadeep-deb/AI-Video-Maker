# Open Decisions

Everything below is **not locked**. Each has a working default so tasks are unblocked, but the default should be revisited with the owner at the marked checkpoint.

| # | Question | Working default | Revisit at |
|---|----------|-----------------|-----------|
| 1 | Avatar backdrop: still portrait background only, or composite the talking head onto a persona-matched background? | Portrait's own background (nano banana renders persona setting into the portrait) | task-10 demo |
| 2 | Should Mode A show a 3-second animated preview before committing to the full render? | No (costs a full pipeline warm-up + GPU); approval gate is on the still portrait | task-11 demo |
| 3 | Default subtitle style: phrase-at-a-time or word-karaoke? (Both ship; this is only the default) | Phrase-at-a-time | task-16 demo |
| 4 | GPU slot pricing: how many daily SadTalker/VoxCPM slots per user vs site-wide? | 1 per user/day, site-wide cap from measured ZeroGPU budget | task-15 |
| 5 | Script length cap for 5-min preset (animation time grows linearly) | Cap Mode A at 2 min; 5 min is Mode B only | task-12 demo |
| 7 | Watermark/credit line on output videos ("Made with …")? | Off; metadata tag only — flip on if abuse observed | task-19 |
| 8 | Pexels/Pixabay attribution: file metadata only, or visible end-card? | Metadata + credits.txt in download bundle | task-08 |
| 9 | Selfie/voice-sample retention: delete originals after portrait/profile approval? | Keep (needed for restyle/re-clone) with a prominent delete button + stated in privacy page | task-19 |
| 10 | Product name: needs a real name before the public URL exists | Working name "AI Video Maker" | task-20 |
| 11 | Per-user daily credit numbers (videos/scripts/stylings) | 3 / 10 / 2 | task-15, re-tune after launch data |
| 12 | Email verification: signed magic-link (no mail dependency) vs free transactional email tier | Magic-link | task-14 |
| 13 | Rendered-video retention on the 200 GB disk | Auto-prune MP4s after 14 days (projects/scripts kept, re-render free-of-charge if pruned) | task-20 |

## Resolution protocol

When a default is confirmed or overturned, move the decision into the appropriate locked requirement file and delete the row here. This file must be empty at task-21 launch.
