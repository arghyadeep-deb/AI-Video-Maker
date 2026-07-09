from typing import Literal, Optional

from pydantic import BaseModel


MusicMood = Literal["calm", "upbeat", "mystical", "corporate"]


class VideoRequest(BaseModel):
    mode: Literal["a", "b"]
    avatar_id: Optional[str] = None
    voice_profile_id: Optional[str] = None
    subtitles: bool = True
    subtitle_style: Literal["phrase", "karaoke"] = "phrase"
    hd_requested: bool = False
    # specs/04-tasks/task-16-music-subtitle-styles.md: off by default in
    # both modes (Mode A explicitly - "talking head reads better dry" - and
    # Mode B as the safe default for a brand new toggle).
    music_enabled: bool = False
    music_mood: Optional[MusicMood] = None
