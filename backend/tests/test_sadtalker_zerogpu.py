import pytest

from app.db.connection import get_connection, run_migrations
from app.engines.talking_head.base import TalkingHeadEngineError
from app.engines.talking_head.sadtalker_zerogpu import SadTalkerZeroGPUEngine, ZeroGpuQuotaExhaustedError
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


@pytest.mark.asyncio
async def test_missing_space_id_is_an_honest_error(conn, tmp_path):
    engine = SadTalkerZeroGPUEngine(
        space_id=None, hf_token=None, conn=conn, daily_limit_seconds=300,
    )
    with pytest.raises(TalkingHeadEngineError, match="not configured"):
        await engine.render("portrait.png", "audio.wav", str(tmp_path / "out.mp4"))


@pytest.mark.asyncio
async def test_budget_exhausted_rejects_before_calling(conn, tmp_path):
    gpu_budget.record_usage(conn, 290)
    calls = []
    engine = SadTalkerZeroGPUEngine(
        space_id="owner/sadtalker-space", hf_token=None, conn=conn,
        daily_limit_seconds=300, estimate_seconds=60,
        client_factory=lambda: FakeGradioClient(calls=calls),
    )
    with pytest.raises(ZeroGpuQuotaExhaustedError):
        await engine.render("portrait.png", "audio.wav", str(tmp_path / "out.mp4"))
    assert calls == []  # never even called the Space


@pytest.mark.asyncio
async def test_successful_render_returns_result_and_charges_budget(conn, tmp_path):
    # handle_file() validates the input paths exist on disk before the fake
    # client is ever called - real (placeholder-content) files needed here.
    portrait_path = tmp_path / "portrait.png"
    audio_path = tmp_path / "audio.wav"
    portrait_path.write_bytes(b"fake-portrait")
    audio_path.write_bytes(b"fake-audio")

    fixture_bytes = b"\x00\x00\x00\x18ftypisommp4-fixture-bytes"
    result_file = tmp_path / "result.mp4"
    result_file.write_bytes(fixture_bytes)
    output_path = tmp_path / "out.mp4"

    engine = SadTalkerZeroGPUEngine(
        space_id="owner/sadtalker-space", hf_token=None, conn=conn,
        daily_limit_seconds=300, estimate_seconds=60,
        client_factory=lambda: FakeGradioClient(result_path=str(result_file)),
    )
    result = await engine.render(str(portrait_path), str(audio_path), str(output_path))

    assert result.engine == "sadtalker"
    assert result.video_path == str(output_path)
    assert output_path.read_bytes() == fixture_bytes
    assert gpu_budget.seconds_used_today(conn) >= 60


@pytest.mark.asyncio
async def test_quota_error_refunds_and_raises_zerogpu_exhausted(conn, tmp_path):
    portrait_path = tmp_path / "portrait.png"
    audio_path = tmp_path / "audio.wav"
    portrait_path.write_bytes(b"fake-portrait")
    audio_path.write_bytes(b"fake-audio")

    engine = SadTalkerZeroGPUEngine(
        space_id="owner/sadtalker-space", hf_token=None, conn=conn,
        daily_limit_seconds=300, estimate_seconds=60,
        client_factory=lambda: FakeGradioClient(error=RuntimeError("You have exceeded your GPU quota")),
    )
    with pytest.raises(ZeroGpuQuotaExhaustedError):
        await engine.render(str(portrait_path), str(audio_path), str(tmp_path / "out.mp4"))

    assert gpu_budget.seconds_used_today(conn) == 0.0  # refunded, not left charged


@pytest.mark.asyncio
async def test_non_quota_error_retries_once_then_keeps_the_charge(conn, tmp_path):
    portrait_path = tmp_path / "portrait.png"
    audio_path = tmp_path / "audio.wav"
    portrait_path.write_bytes(b"fake-portrait")
    audio_path.write_bytes(b"fake-audio")

    calls = []
    engine = SadTalkerZeroGPUEngine(
        space_id="owner/sadtalker-space", hf_token=None, conn=conn,
        daily_limit_seconds=300, estimate_seconds=60,
        client_factory=lambda: FakeGradioClient(error=ConnectionError("network blip"), calls=calls),
    )
    with pytest.raises(TalkingHeadEngineError):
        await engine.render(str(portrait_path), str(audio_path), str(tmp_path / "out.mp4"))

    assert len(calls) == 2  # one retry
    assert gpu_budget.seconds_used_today(conn) == 60  # charge kept, not refunded
