"""ScriptLLM — typed Gemini Flash client for script generation and
free-form text rewrites (improve-selection).

specs/01-requirements/07-free-stack-lock.md locks Gemini Flash; every external
call for this capability goes through this one interface so a fallback
(Groq, OpenRouter) can slot in later without touching the pipeline.
"""
import time

from google import genai
from google.genai import types
from google.genai.errors import APIError

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "language": {"type": "string", "enum": ["hi", "en"]},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "text": {"type": "string"},
                    "visual_hint": {"type": "string"},
                },
                "required": ["id", "text", "visual_hint"],
            },
        },
    },
    "required": ["title", "language", "scenes"],
}


class ScriptGenerationError(Exception):
    """Non-quota failure calling the LLM (network, malformed request, etc.)."""


class QuotaExhaustedError(Exception):
    """Free-tier request budget exhausted — an honest UI message, never a stack trace."""

    def __init__(self) -> None:
        super().__init__("Free daily limit reached — resets midnight PT")


def _is_quota_error(exc: APIError) -> bool:
    return exc.code == 429 or "RESOURCE_EXHAUSTED" in str(exc.status).upper()


class ScriptLLM:
    def __init__(self, api_key: str | list[str] | None, model: str, max_retries: int = 2):
        self._model = model
        self._max_retries = max_retries
        self._keys = [api_key] if isinstance(api_key, str) else list(api_key or [])
        self._key_index = 0
        self._client = self._make_client()

    def _make_client(self):
        if not self._keys:
            return None
        return genai.Client(api_key=self._keys[self._key_index])

    def _rotate_key(self) -> bool:
        """specs/04-tasks/task-15-quotas-fairness.md: "key pool: rotation
        only" - resilience against a transient 429 on one key, not extra
        quota (most providers tie the real quota to the developer/project,
        not the literal key string - logged here per the task's own ToS
        caveat instruction). Returns True if there was another key to try.
        """
        if self._key_index + 1 < len(self._keys):
            self._key_index += 1
            self._client = self._make_client()
            return True
        return False

    def _call(self, prompt: str, response_schema: dict | None) -> str:
        """Retries transient 429s with backoff, rotating through the key
        pool first before backing off on the same key; a quota error that
        survives every key and every retry becomes QuotaExhaustedError. Any
        other failure becomes ScriptGenerationError.
        """
        if self._client is None:
            raise ScriptGenerationError("GEMINI_API_KEY is not configured")

        config_kwargs = {}
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema

        delay = 1.0
        attempt = 0
        while True:
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
            except APIError as exc:
                if _is_quota_error(exc):
                    if self._rotate_key():
                        continue  # try the next key immediately, doesn't count as a retry
                    if attempt >= self._max_retries:
                        raise QuotaExhaustedError() from exc
                    time.sleep(delay)
                    delay *= 2
                    attempt += 1
                    continue
                raise ScriptGenerationError(str(exc)) from exc
            else:
                if not response.text:
                    raise ScriptGenerationError("Empty response from Gemini")
                return response.text

    def generate_raw(self, prompt: str) -> str:
        """Structured JSON script generation (task-02)."""
        return self._call(prompt, response_schema=RESPONSE_SCHEMA)

    def generate_text(self, prompt: str) -> str:
        """Free-form text generation, no JSON schema (task-04 improve-selection)."""
        return self._call(prompt, response_schema=None)
