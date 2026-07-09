from types import SimpleNamespace

import pytest
from google.genai.errors import APIError

from app.engines.script_llm import ScriptGenerationError, ScriptLLM, QuotaExhaustedError


def _make_llm(max_retries=2) -> ScriptLLM:
    llm = ScriptLLM(api_key="fake-key", model="gemini-flash-test", max_retries=max_retries)
    return llm


def test_no_api_key_raises_generation_error():
    llm = ScriptLLM(api_key=None, model="gemini-flash-test")
    with pytest.raises(ScriptGenerationError):
        llm.generate_raw("hello")


def test_successful_call_returns_text(monkeypatch):
    llm = _make_llm()
    monkeypatch.setattr(
        llm._client.models,
        "generate_content",
        lambda **kwargs: SimpleNamespace(text='{"ok": true}'),
    )
    assert llm.generate_raw("hello") == '{"ok": true}'


def test_quota_error_retries_then_raises_quota_exhausted(monkeypatch):
    llm = _make_llm(max_retries=1)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    calls = {"n": 0}

    def fake_generate(**kwargs):
        calls["n"] += 1
        raise APIError(code=429, response_json={"error": {"message": "RESOURCE_EXHAUSTED"}})

    monkeypatch.setattr(llm._client.models, "generate_content", fake_generate)

    with pytest.raises(QuotaExhaustedError):
        llm.generate_raw("hello")
    assert calls["n"] == 2  # initial attempt + 1 retry


def test_non_quota_api_error_raises_generation_error(monkeypatch):
    llm = _make_llm()

    def fake_generate(**kwargs):
        raise APIError(code=400, response_json={"error": {"message": "bad request"}})

    monkeypatch.setattr(llm._client.models, "generate_content", fake_generate)

    with pytest.raises(ScriptGenerationError):
        llm.generate_raw("hello")


def test_empty_response_raises_generation_error(monkeypatch):
    llm = _make_llm()
    monkeypatch.setattr(
        llm._client.models, "generate_content", lambda **kwargs: SimpleNamespace(text="")
    )
    with pytest.raises(ScriptGenerationError):
        llm.generate_raw("hello")


def test_quota_error_rotates_to_the_next_key_before_backing_off(monkeypatch):
    """specs/04-tasks/task-15-quotas-fairness.md: "key pool: rotation on
    429" - a 429 on the first key should try the next key immediately,
    not count as one of the backoff retries."""
    monkeypatch.setattr("time.sleep", lambda *_: None)
    created_with_keys: list[str] = []

    class FakeClient:
        def __init__(self, api_key):
            created_with_keys.append(api_key)
            self.models = SimpleNamespace(generate_content=self._generate)
            self._api_key = api_key

        def _generate(self, **kwargs):
            if self._api_key == "key-1":
                raise APIError(code=429, response_json={"error": {"message": "RESOURCE_EXHAUSTED"}})
            return SimpleNamespace(text='{"ok": true}')

    monkeypatch.setattr("app.engines.script_llm.genai.Client", FakeClient)

    llm = ScriptLLM(api_key=["key-1", "key-2"], model="gemini-flash-test", max_retries=0)
    result = llm.generate_raw("hello")

    assert result == '{"ok": true}'
    assert created_with_keys == ["key-1", "key-2"]


def test_quota_error_on_every_key_still_raises_quota_exhausted(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)

    class FakeClient:
        def __init__(self, api_key):
            self.models = SimpleNamespace(generate_content=self._generate)

        def _generate(self, **kwargs):
            raise APIError(code=429, response_json={"error": {"message": "RESOURCE_EXHAUSTED"}})

    monkeypatch.setattr("app.engines.script_llm.genai.Client", FakeClient)

    llm = ScriptLLM(api_key=["key-1", "key-2"], model="gemini-flash-test", max_retries=0)
    with pytest.raises(QuotaExhaustedError):
        llm.generate_raw("hello")


def test_single_string_api_key_still_works():
    llm = ScriptLLM(api_key="a-single-key", model="gemini-flash-test")
    assert llm._keys == ["a-single-key"]
