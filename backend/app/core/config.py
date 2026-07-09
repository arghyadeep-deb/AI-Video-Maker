"""Application configuration.

All settings are read from environment variables / a `.env` file at the repo
root. Nothing here is hardcoded to a Windows path — the production target is
an aarch64 Linux VM, so every path is a `pathlib.Path` built relative to the
repo root at import time.
"""
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# Locked base voices — specs/01-requirements/06-languages-hindi-english.md.
# These are the prosody base OpenVoice converts into the user's own timbre;
# also the explicit stock-voice fallback. Confirmed against a live
# `edge-tts --list-voices` at task-05. "en-US" is the optional alternate
# accent (open decision #6, resolved: zero extra work, same edge-tts call).
VOICE_TABLE = {
    "hi": {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"},
    "en": {"female": "en-IN-NeerjaNeural", "male": "en-IN-PrabhatNeural"},
    "en-US": {"female": "en-US-AriaNeural", "male": "en-US-GuyNeural"},
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    gemini_api_key: Optional[str] = None
    pexels_api_key: Optional[str] = None
    pixabay_api_key: Optional[str] = None
    hf_token: Optional[str] = None

    # specs/04-tasks/task-15-quotas-fairness.md: "key pool: rotation only,
    # ToS caveat logged here". Comma-separated ADDITIONAL keys beyond
    # gemini_api_key - rotating keys is resilience against a single
    # transient 429, not extra quota: most providers tie the real quota to
    # the developer/project, not the literal key string.
    gemini_api_key_pool: Optional[str] = None

    # specs/01-requirements/10-hosting-accounts-quotas.md: "~750 LLM calls
    # and ~250 images each" per day is "effectively personal" at 1-2 users -
    # these caps are safety rails set well above that, not rationing.
    gemini_text_daily_cap: int = 700
    genai_image_daily_cap: int = 200
    # specs/04-tasks/task-15-quotas-fairness.md's degradation table: "LLM
    # cap near -> block new scripts before improvements (in-flight work is
    # sacred)". New-script generation stops this many calls earlier than
    # the hard cap, reserving headroom so a user already mid-review-loop
    # can keep refining their script even as the daily budget tightens.
    gemini_text_new_script_reserve: int = 50

    # specs/02-research/08-free-hosting.md: free ZeroGPU accounts get
    # "~300s programmatic" per day - a safety-rail estimate for our own
    # preemptive fallback, not the actual HF-side enforcement (HF enforces
    # its own limit regardless of what we track).
    zerogpu_daily_seconds: float = 300.0
    # The owner's own deployed Space (hf-space/), not a third-party demo -
    # it exposes our custom render(portrait, wav) contract. Unset until the
    # owner deploys it (needs their HF account) - see task-11 Completion notes.
    sadtalker_space_id: Optional[str] = None

    # Same shape as sadtalker_space_id above (task-18) - the owner's own
    # deployed VoxCPM+MuseTalk Space, unset until deployed.
    voxcpm_space_id: Optional[str] = None

    media_root: Path = REPO_ROOT / "media"
    db_path: Path = REPO_ROOT / "media" / "app.db"

    # specs/01-requirements/07-free-stack-lock.md
    script_llm_model: str = "gemini-flash-latest"
    avatar_styling_model: str = "gemini-2.5-flash-image"

    frontend_origin: str = "http://localhost:3000"

    # specs/04-tasks/task-14-auth-accounts.md. Random-per-process default is
    # fine for dev (get_settings() caches one Settings instance, so tokens
    # stay valid for the process's lifetime) - production MUST set a real
    # JWT_SECRET in .env, or every restart invalidates every session.
    jwt_secret: str = secrets.token_hex(32)
    jwt_expire_minutes: int = 60 * 24 * 14  # 2 weeks - a private 1-2 user site, not a bank
    session_cookie_name: str = "session"

    @property
    def voice_table(self) -> dict:
        return VOICE_TABLE

    @property
    def gemini_api_keys(self) -> list[str]:
        """The full rotation pool: gemini_api_key first, then any keys in
        gemini_api_key_pool (comma-separated), de-duplicated, empty/blank
        entries dropped."""
        keys = [self.gemini_api_key] if self.gemini_api_key else []
        if self.gemini_api_key_pool:
            keys += [k.strip() for k in self.gemini_api_key_pool.split(",") if k.strip()]
        seen: set[str] = set()
        deduped = []
        for key in keys:
            if key not in seen:
                seen.add(key)
                deduped.append(key)
        return deduped


@lru_cache
def get_settings() -> Settings:
    return Settings()
