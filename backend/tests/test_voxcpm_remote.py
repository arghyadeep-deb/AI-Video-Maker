import pytest

from app.db.connection import get_connection, run_migrations
from app.engines.tts.voxcpm_remote import VoxCPMEngineError, VoxCPMQuotaExhaustedError, VoxCPMRemoteEngine
from app.quota import gpu_budget


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    connection = get_connection(db_path)
    connection.execute("INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')")
    connection.commit()
    yield connection
    connection.close()


class FakeGradioClient:
    def __init__(self, result_path=None, error=None, calls=None):
        self._result_path = result_path
        self._error = error
        self._calls = calls if calls is not None else []

    def predict(self, *args, **kwargs):
        self._calls.append((args, kwargs))
        if self._error:
            raise self._error
        return self._result_path


def test_requires_either_reference_or_persona():
    with pytest.raises(ValueError):
        VoxCPMRemoteEngine(space_id="x", hf_token=None, conn=None, daily_limit_seconds=300)


async def test_missing_space_id_is_an_honest_error(conn, tmp_path):
    engine = VoxCPMRemoteEngine(
        space_id=None, hf_token=None, conn=conn, daily_limit_seconds=300,
        persona_description="wise old astrologer",
    )
    with pytest.raises(VoxCPMEngineError, match="not configured"):
        await engine.speak("hello", "voice", tmp_path / "out.mp3")


async def test_budget_exhausted_rejects_before_calling(conn, tmp_path):
    gpu_budget.record_usage(conn, 290)
    calls = []
    engine = VoxCPMRemoteEngine(
        space_id="owner/voxcpm-space", hf_token=None, conn=conn,
        daily_limit_seconds=300, estimate_seconds=30,
        persona_description="wise old astrologer",
        client_factory=lambda: FakeGradioClient(calls=calls),
    )
    with pytest.raises(VoxCPMQuotaExhaustedError):
        await engine.speak("hello", "voice", tmp_path / "out.mp3")
    assert calls == []


async def test_successful_clone_speak_returns_result_with_aligned_timings(conn, tmp_path):
    from app.engines.tts.edge import EdgeTTSEngine

    text = "Hello there, this is a short test sentence."
    result_file = tmp_path / "voxcpm_result.mp3"
    try:
        await EdgeTTSEngine().speak(text, "en-US-AriaNeural", result_file)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"edge-tts unreachable in this environment: {exc}")

    ref_wav = tmp_path / "ref.wav"
    ref_wav.write_bytes(b"fake-reference-audio")
    output_path = tmp_path / "out.mp3"

    engine = VoxCPMRemoteEngine(
        space_id="owner/voxcpm-space", hf_token=None, conn=conn,
        daily_limit_seconds=300, estimate_seconds=30,
        reference_wav_path=ref_wav,
        client_factory=lambda: FakeGradioClient(result_path=str(result_file)),
    )
    result = await engine.speak(text, "voice", output_path)

    assert output_path.exists()
    assert len(result.timings) > 0
    assert gpu_budget.seconds_used_today(conn) >= 30


async def test_quota_error_refunds_and_raises(conn, tmp_path):
    engine = VoxCPMRemoteEngine(
        space_id="owner/voxcpm-space", hf_token=None, conn=conn,
        daily_limit_seconds=300, estimate_seconds=30,
        persona_description="wise old astrologer",
        client_factory=lambda: FakeGradioClient(error=RuntimeError("You have exceeded your GPU quota")),
    )
    with pytest.raises(VoxCPMQuotaExhaustedError):
        await engine.speak("hello", "voice", tmp_path / "out.mp3")

    assert gpu_budget.seconds_used_today(conn) == 0.0


async def test_non_quota_error_retries_once_then_keeps_the_charge(conn, tmp_path):
    calls = []
    engine = VoxCPMRemoteEngine(
        space_id="owner/voxcpm-space", hf_token=None, conn=conn,
        daily_limit_seconds=300, estimate_seconds=30,
        persona_description="wise old astrologer",
        client_factory=lambda: FakeGradioClient(error=ConnectionError("network blip"), calls=calls),
    )
    with pytest.raises(VoxCPMEngineError):
        await engine.speak("hello", "voice", tmp_path / "out.mp3")

    assert len(calls) == 2
    assert gpu_budget.seconds_used_today(conn) == 30
