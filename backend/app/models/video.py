from typing import Literal, Optional

from pydantic import BaseModel


MusicMood = Literal["calm", "upbeat", "mystical", "corporate"]


class VideoRequest(BaseModel):
    mode: Literal["a", "b"]
    avatar_id: Optional[str] = None
    # A stock voice table ID (e.g. "hi-IN-MadhurNeural") - the male/female
    # picker on the generate page. Persisted onto projects.voice at render
    # start (below) so stage_tts's existing `project["voice"] or default`
    # lookup honors it; the user's own enrolled/cloned voice, if any, still
    # takes priority over this at the narration-engine level regardless
    # (make_narration_engine), matching the "every render defaults to your
    # own voice" rule - this only picks the stock fallback's gender.
    voice: Optional[str] = None
    subtitles: bool = True
    subtitle_style: Literal["phrase", "karaoke"] = "phrase"
    # None = "let the server decide at render time": HD by default while
    # the home GPU worker is online (specs/03-design/11-gpu-worker.md:
    # "worker online -> SadTalker HD by default"), off otherwise. An
    # explicit True/False from the UI always wins.
    hd_requested: Optional[bool] = None
    # Mode B visual quality level (task-20a) - "footage" = a real AI-generated
    # clip per scene via the home GPU worker's scene_gen engine;
    # specs/01-requirements/05-mode-b-image-video.md's two-level table.
    visual_level: Literal["photo", "footage"] = "photo"
    # specs/04-tasks/task-16-music-subtitle-styles.md: off by default in
    # both modes (Mode A explicitly - "talking head reads better dry" - and
    # Mode B as the safe default for a brand new toggle).
    music_enabled: bool = False
    music_mood: Optional[MusicMood] = None
