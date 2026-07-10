from typing import Literal, Optional

from pydantic import BaseModel


MusicMood = Literal["calm", "upbeat", "mystical", "corporate"]


class VideoRequest(BaseModel):
    mode: Literal["a", "b"]
    avatar_id: Optional[str] = None
    voice_profile_id: Optional[str] = None
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
