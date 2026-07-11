"""ScriptLLM — typed Gemini Flash client for script generation and
free-form text rewrites (improve-selection), with risk R2's wired text
fallback chain: Gemini -> Groq -> OpenRouter.

specs/01-requirements/07-free-stack-lock.md locks Gemini Flash as primary;
specs/06-risks-and-future/01-risks.md R2 names Groq/OpenRouter as the text
fallback (wired 2026-07-11, the day R2's image half fired for real). The
fallbacks are OpenAI-compatible REST free tiers, called with plain httpx —
no extra SDK. Output still flows through script_service's validation gate
(Devanagari checks + one retry), so a weaker fallback model degrades to an
honest validation error, never silent garbage.
"""
import re
import time
from dataclasses import dataclass

import httpx
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


@dataclass(frozen=True)
class FallbackProvider:
    """One OpenAI-compatible chat-completions endpoint in the R2 chain."""

    name: str  # "groq" | "openrouter"
    base_url: str
    api_key: str
    model: str


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def _strip_code_fences(text: str) -> str:
    """Fallback models love wrapping JSON in markdown fences; Gemini's
    structured output never does. Downstream json.loads needs them gone."""
    return _CODE_FENCE.sub("", text.strip())


class ScriptLLM:
    def __init__(
        self,
        api_key: str | list[str] | None,
        model: str,
        max_retries: int = 2,
        fallbacks: list[FallbackProvider] | None = None,
    ):
        self._model = model
        self._max_retries = max_retries
        self._keys = [api_key] if isinstance(api_key, str) else list(api_key or [])
        self._key_index = 0
        self._client = self._make_client()
        self._fallbacks = fallbacks or []
        # Which provider actually answered the last call - "gemini" or a
        # fallback's name. Surfaced for logging/tests; honest provenance.
        self.last_provider: str | None = None

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
        """Gemini first (key rotation + backoff), then the R2 fallback
        chain in order. The original Gemini error is preserved and re-raised
        only if every provider fails - an exhausted quota stays an honest
        QuotaExhaustedError, never a stack trace."""
        try:
            result = self._call_gemini(prompt, response_schema)
            self.last_provider = "gemini"
            return result
        except (QuotaExhaustedError, ScriptGenerationError) as gemini_error:
            for provider in self._fallbacks:
                try:
                    result = self._call_openai_compat(provider, prompt, response_schema)
                    self.last_provider = provider.name
                    return result
                except Exception:  # noqa: BLE001 - each fallback failure moves to the next
                    continue
            raise gemini_error

    def _call_openai_compat(
        self, provider: FallbackProvider, prompt: str, response_schema: dict | None
    ) -> str:
        """One chat-completions call. JSON mode is requested where asked;
        a provider/model that rejects response_format gets one plain retry
        (the prompt itself already demands raw JSON, and the validation
        gate downstream is the real enforcement)."""
        body = {
            "model": provider.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if response_schema is not None:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {provider.api_key}"}

        response = httpx.post(
            f"{provider.base_url}/chat/completions", json=body, headers=headers, timeout=120
        )
        if response.status_code == 400 and "response_format" in body:
            del body["response_format"]
            response = httpx.post(
                f"{provider.base_url}/chat/completions", json=body, headers=headers, timeout=120
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not content:
            raise ScriptGenerationError(f"Empty response from {provider.name}")
        return _strip_code_fences(content)

    def _call_gemini(self, prompt: str, response_schema: dict | None) -> str:
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


def make_script_llm(settings) -> ScriptLLM:
    """The one blessed constructor: Gemini key pool + whatever R2 fallback
    providers have keys configured, in chain order."""
    fallbacks = []
    if settings.groq_api_key:
        fallbacks.append(
            FallbackProvider("groq", GROQ_BASE_URL, settings.groq_api_key, settings.groq_model)
        )
    if settings.openrouter_api_key:
        fallbacks.append(
            FallbackProvider(
                "openrouter", OPENROUTER_BASE_URL, settings.openrouter_api_key,
                settings.openrouter_model,
            )
        )
    return ScriptLLM(
        api_key=settings.gemini_api_keys, model=settings.script_llm_model, fallbacks=fallbacks
    )
