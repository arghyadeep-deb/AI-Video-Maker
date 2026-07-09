# Music track licenses

All 9 tracks are by **Jason Shaw (audionautix.com)**, mirrored on Wikimedia
Commons, licensed **CC BY 3.0 Unported** (Creative Commons Attribution 3.0):
https://creativecommons.org/licenses/by/3.0/

Required attribution for every track (per the file's own Commons page):
**"music by audionautix.com"**

Files were downloaded from Wikimedia Commons (`upload.wikimedia.org`,
stable CDN URLs, verified against each file's own description page before
downloading) and re-encoded from their original bitrate (160-320kbps) down
to a consistent 128kbps MP3 to keep repo size reasonable — re-encoding a
CC-BY work is permitted (the license permits remixing/adapting), and the
128kbps copies are what's actually bundled in `backend/assets/music/`.

| Filename | Title | Mood | Source page |
|---|---|---|---|
| calm-blue-lake.mp3 | Calm Blue Lake | calm | https://commons.wikimedia.org/wiki/File:Audionautix-com-ccby-calmbluelake.mp3 |
| serenity.mp3 | Serenity | calm | https://commons.wikimedia.org/wiki/File:Audionautix-com-ccby-serenity.mp3 |
| namaste.mp3 | Namaste | calm | https://commons.wikimedia.org/wiki/File:Audionautix-com-ccby-namaste.mp3 |
| funky-junky.mp3 | Funky Junky | upbeat | https://commons.wikimedia.org/wiki/File:Audionautix-com-ccby-funkyjunky.mp3 |
| kicked-up-pumps.mp3 | Kicked Up Pumps | upbeat | https://commons.wikimedia.org/wiki/File:Audionautix-com-ccby-kickeduppumps.mp3 |
| dark-mystery.mp3 | Dark Mystery | mystical | https://commons.wikimedia.org/wiki/File:Audionautix-com-ccby-darkmystery.mp3 |
| ocean-floor.mp3 | Ocean Floor | mystical | https://commons.wikimedia.org/wiki/File:Audionautix-com-ccby-oceanfloor.mp3 |
| corporation-motivation.mp3 | Corporation Motivation | corporate | https://commons.wikimedia.org/wiki/File:Audionautix-com-ccby-corporationmotivation.mp3 |
| algorithm.mp3 | Algorithm | corporate | https://commons.wikimedia.org/wiki/File:Audionautix-com-ccby-algorithm.mp3 |

## Where this attribution appears in the product

Per the existing task-08/task-09 pattern for image credits, the track used
in a render should be recorded in that scene's/project's `credits.txt` in
the download bundle, e.g.:

```
Background music: "Calm Blue Lake" — music by audionautix.com
Licensed under CC BY 3.0 (https://creativecommons.org/licenses/by/3.0/)
```

## Why Audionautix / Wikimedia Commons, not Pixabay Music

Pixabay's official API (`pixabay.com/api/docs/`, the same one this project
already uses for images) documents image and video search only — no music
endpoint. Pixabay Music's own website blocks non-browser fetches (403 on
direct HTTP fetch), and its downloads are gated behind JS-rendered buttons
that aren't reliably scriptable. Wikimedia Commons mirrors a large,
well-documented catalog of Audionautix's CC-BY tracks with stable direct
download URLs and per-file license metadata, so it was used instead. All 9
tracks are genuinely instrumental (verified via each file's own Commons
description/mood tags — no vocals) and license terms were confirmed by
reading each file's actual Commons page, not assumed from memory.
