"""R2 text fallback chain (Gemini -> Groq -> OpenRouter), wired 2026-07-11.

The Gemini leg is monkeypatched at the _call_gemini boundary (its own
retry/rotation behavior is already covered by test_script_llm.py); the
OpenAI-compatible legs are tested against a stubbed httpx.post.
"""
import json

import httpx
import pytest

from app.core.config import Settings
from app.engines.script_llm import (
    FallbackProvider,
    QuotaExhaustedError,
    ScriptGenerationError,
    ScriptLLM,
    _strip_code_fences,
    make_script_llm,
)

GROQ = FallbackProvider("groq", "https://groq.test/openai/v1", "gk", "llama-x")
OPENROUTER = FallbackProvider("openrouter", "https://or.test/api/v1", "ok", "meta/llama-x:free")


def _llm(fallbacks):
    return ScriptLLM(api_key="gemini-key", model="gemini-flash-latest", fallbacks=fallbacks)


def _gemini_quota_fails(llm, monkeypatch):
    def boom(prompt, response_schema):
        raise QuotaExhaustedError()

    monkeypatch.setattr(llm, "_call_gemini", boom)


def _fake_chat_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
        request=httpx.Request("POST", "https://x.test"),
    )


def test_gemini_success_never_touches_fallbacks(monkeypatch):
    llm = _llm([GROQ])
    monkeypatch.setattr(llm, "_call_gemini", lambda p, r: '{"ok": true}')

    def no_http(*a, **k):
        raise AssertionError("fallback called despite Gemini success")

    monkeypatch.setattr(httpx, "post", no_http)
    assert llm.generate_raw("prompt") == '{"ok": true}'
    assert llm.last_provider == "gemini"


def test_gemini_quota_falls_to_groq(monkeypatch):
    llm = _llm([GROQ, OPENROUTER])
    _gemini_quota_fails(llm, monkeypatch)
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return _fake_chat_response('{"title": "from groq"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    result = llm.generate_raw("prompt")
    assert result == '{"title": "from groq"}'
    assert llm.last_provider == "groq"
    url, body, headers = calls[0]
    assert url.startswith("https://groq.test")
    assert body["model"] == "llama-x"
    assert body["response_format"] == {"type": "json_object"}
    assert headers["Authorization"] == "Bearer gk"


def test_groq_failure_falls_to_openrouter(monkeypatch):
    llm = _llm([GROQ, OPENROUTER])
    _gemini_quota_fails(llm, monkeypatch)

    def fake_post(url, json=None, headers=None, timeout=None):
        if "groq.test" in url:
            raise httpx.ConnectError("groq down")
        return _fake_chat_response('{"title": "from openrouter"}')

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm.generate_raw("prompt") == '{"title": "from openrouter"}'
    assert llm.last_provider == "openrouter"


def test_all_providers_fail_reraises_the_honest_gemini_error(monkeypatch):
    llm = _llm([GROQ, OPENROUTER])
    _gemini_quota_fails(llm, monkeypatch)

    def fake_post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectError("everything down")

    monkeypatch.setattr(httpx, "post", fake_post)
    # The user-facing message stays the honest quota one, not a stack trace
    # from whichever fallback died last.
    with pytest.raises(QuotaExhaustedError):
        llm.generate_raw("prompt")


def test_gemini_non_quota_error_also_triggers_fallback(monkeypatch):
    """R2 covers availability, not just quota - a shut-down model (like the
    image preview was) surfaces as ScriptGenerationError and must fail over."""
    llm = _llm([GROQ])

    def boom(prompt, response_schema):
        raise ScriptGenerationError("404 model retired")

    monkeypatch.setattr(llm, "_call_gemini", boom)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _fake_chat_response("rescued"))
    assert llm.generate_text("prompt") == "rescued"


def test_no_fallbacks_configured_behaves_as_before(monkeypatch):
    llm = _llm([])
    _gemini_quota_fails(llm, monkeypatch)
    with pytest.raises(QuotaExhaustedError):
        llm.generate_raw("prompt")


def test_response_format_rejection_retries_plain(monkeypatch):
    """Some OpenRouter models 400 on response_format - one plain retry."""
    llm = _llm([OPENROUTER])
    _gemini_quota_fails(llm, monkeypatch)
    bodies = []

    def fake_post(url, json=None, headers=None, timeout=None):
        bodies.append(dict(json))
        if "response_format" in json:
            return httpx.Response(400, json={"error": "response_format unsupported"},
                                  request=httpx.Request("POST", url))
        return _fake_chat_response('```json\n{"title": "fenced"}\n```')

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm.generate_raw("prompt") == '{"title": "fenced"}'
    assert "response_format" in bodies[0] and "response_format" not in bodies[1]


def test_code_fence_stripping():
    assert _strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_code_fences('{"a": 1}') == '{"a": 1}'
    # Sanity: the stripped result is valid JSON
    assert json.loads(_strip_code_fences('```json\n{"a": 1}\n```')) == {"a": 1}


def test_free_form_text_calls_send_no_response_format(monkeypatch):
    llm = _llm([GROQ])
    _gemini_quota_fails(llm, monkeypatch)
    bodies = []

    def fake_post(url, json=None, headers=None, timeout=None):
        bodies.append(dict(json))
        return _fake_chat_response("improved text")

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm.generate_text("improve this") == "improved text"
    assert "response_format" not in bodies[0]


def test_make_script_llm_builds_chain_from_settings():
    settings = Settings(
        _env_file=None, gemini_api_key="g", groq_api_key="q", openrouter_api_key="o"
    )
    llm = make_script_llm(settings)
    assert [p.name for p in llm._fallbacks] == ["groq", "openrouter"]

    settings = Settings(_env_file=None, gemini_api_key="g")
    assert make_script_llm(settings)._fallbacks == []
