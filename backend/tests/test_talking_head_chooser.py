import pytest

from app.engines.talking_head.base import TalkingHeadEngineError, TalkingHeadResult
from app.engines.talking_head.chooser import render_with_fallback
from app.engines.talking_head.sadtalker_zerogpu import ZeroGpuQuotaExhaustedError
from app.jobs.gpu_router import GpuTaskFailed, HomeWorkerUnavailable


class FakeEngine:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = 0

    async def render(self, portrait_path, wav_path, output_path):
        self.calls += 1
        if self._error:
            raise self._error
        return self._result


@pytest.mark.asyncio
async def test_default_uses_wav2lip_when_hd_not_requested():
    sadtalker = FakeEngine()
    wav2lip = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="wav2lip"))

    result = await render_with_fallback(
        hd_requested=False, sadtalker_engine=sadtalker, wav2lip_engine=wav2lip,
        portrait_path="p.png", wav_path="a.wav", output_path="out.mp4",
    )
    assert result.engine == "wav2lip"
    assert sadtalker.calls == 0
    assert wav2lip.calls == 1


@pytest.mark.asyncio
async def test_hd_requested_uses_sadtalker_when_available():
    sadtalker = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="sadtalker"))
    wav2lip = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="wav2lip"))

    result = await render_with_fallback(
        hd_requested=True, sadtalker_engine=sadtalker, wav2lip_engine=wav2lip,
        portrait_path="p.png", wav_path="a.wav", output_path="out.mp4",
    )
    assert result.engine == "sadtalker"
    assert wav2lip.calls == 0


@pytest.mark.asyncio
async def test_zerogpu_quota_exhausted_falls_back_to_wav2lip():
    sadtalker = FakeEngine(error=ZeroGpuQuotaExhaustedError("budget exhausted"))
    wav2lip = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="wav2lip"))

    result = await render_with_fallback(
        hd_requested=True, sadtalker_engine=sadtalker, wav2lip_engine=wav2lip,
        portrait_path="p.png", wav_path="a.wav", output_path="out.mp4",
    )
    assert result.engine == "wav2lip"
    assert sadtalker.calls == 1
    assert wav2lip.calls == 1


@pytest.mark.asyncio
async def test_non_quota_sadtalker_error_does_not_fall_back_silently():
    """A genuine SadTalker crash (not a quota rejection) should surface, not
    be swallowed into a silent Wav2Lip substitution - only the honest
    "budget exhausted, degrading" case falls back automatically."""
    sadtalker = FakeEngine(error=TalkingHeadEngineError("SadTalker crashed"))
    wav2lip = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="wav2lip"))

    with pytest.raises(TalkingHeadEngineError, match="crashed"):
        await render_with_fallback(
            hd_requested=True, sadtalker_engine=sadtalker, wav2lip_engine=wav2lip,
            portrait_path="p.png", wav_path="a.wav", output_path="out.mp4",
        )
    assert wav2lip.calls == 0


@pytest.mark.asyncio
async def test_no_sadtalker_engine_configured_uses_wav2lip_even_if_hd_requested():
    wav2lip = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="wav2lip"))

    result = await render_with_fallback(
        hd_requested=True, sadtalker_engine=None, wav2lip_engine=wav2lip,
        portrait_path="p.png", wav_path="a.wav", output_path="out.mp4",
    )
    assert result.engine == "wav2lip"


# --- three-tier routing (task-20a): home worker -> ZeroGPU -> CPU -----------

@pytest.mark.asyncio
async def test_hd_prefers_home_worker_over_zerogpu():
    home = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="sadtalker-home"))
    sadtalker = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="sadtalker"))
    wav2lip = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="wav2lip"))

    result = await render_with_fallback(
        hd_requested=True, sadtalker_engine=sadtalker, wav2lip_engine=wav2lip,
        portrait_path="p.png", wav_path="a.wav", output_path="out.mp4",
        home_engine=home,
    )
    assert result.engine == "sadtalker-home"
    assert sadtalker.calls == 0 and wav2lip.calls == 0


@pytest.mark.asyncio
async def test_home_worker_offline_falls_to_zerogpu():
    home = FakeEngine(error=HomeWorkerUnavailable("PC offline"))
    sadtalker = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="sadtalker"))
    wav2lip = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="wav2lip"))

    result = await render_with_fallback(
        hd_requested=True, sadtalker_engine=sadtalker, wav2lip_engine=wav2lip,
        portrait_path="p.png", wav_path="a.wav", output_path="out.mp4",
        home_engine=home,
    )
    assert result.engine == "sadtalker"
    assert home.calls == 1 and wav2lip.calls == 0


@pytest.mark.asyncio
async def test_worker_lost_mid_render_falls_all_the_way_to_cpu():
    """PC slept mid-render (GpuTaskFailed) and no ZeroGPU Space deployed:
    the render still succeeds on the CPU floor - a user's video never dies
    because the owner's PC did."""
    home = FakeEngine(error=GpuTaskFailed("worker lost (lease expired)"))
    wav2lip = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="wav2lip"))

    result = await render_with_fallback(
        hd_requested=True, sadtalker_engine=None, wav2lip_engine=wav2lip,
        portrait_path="p.png", wav_path="a.wav", output_path="out.mp4",
        home_engine=home,
    )
    assert result.engine == "wav2lip"
    assert home.calls == 1


@pytest.mark.asyncio
async def test_hd_not_requested_never_touches_home_worker():
    home = FakeEngine()
    wav2lip = FakeEngine(result=TalkingHeadResult(video_path="out.mp4", engine="wav2lip"))

    result = await render_with_fallback(
        hd_requested=False, sadtalker_engine=None, wav2lip_engine=wav2lip,
        portrait_path="p.png", wav_path="a.wav", output_path="out.mp4",
        home_engine=home,
    )
    assert result.engine == "wav2lip"
    assert home.calls == 0
