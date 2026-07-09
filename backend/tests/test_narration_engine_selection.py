"""specs/AGENT-PLAYBOOK.md hard invariant: "Every render defaults to the
user's enrolled voice; stock voice only with a visible notice." Real
OpenVoice inference where feasible, matching this session's established
rigor.
"""
import pytest

from app.db.connection import get_connection, run_migrations
from app.engines.tts.fake import FakeTTSEngine
from app.engines.tts.openvoice import OpenVoiceUnavailableError, extract_embedding, is_available, save_embedding
from app.pipelines.common import FallbackNarrationEngine, make_narration_engine

pytestmark = pytest.mark.skipif(not is_available(), reason="OpenVoice checkpoint not available")


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    connection = get_connection(db_path)
    connection.execute("INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.com', 'x')")
    connection.commit()
    yield connection
    connection.close()


def _make_tone_wav(path, frequency: int, duration_s: float = 4.0, sr: int = 22050) -> None:
    import subprocess

    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency={frequency}:sample_rate={sr}:duration={duration_s}",
            str(path),
        ],
        check=True, capture_output=True, timeout=20,
    )


class RealAudioFakeTTS(FakeTTSEngine):
    async def speak(self, text, voice, out_path, rate=None):
        result = await super().speak(text, voice, out_path, rate)
        duration_s = (
            (result.timings[-1].offset_ms + result.timings[-1].duration_ms) / 1000
            if result.timings else 1.0
        )
        import subprocess

        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=22050",
                "-t", f"{max(duration_s, 0.5):.3f}", str(out_path),
            ],
            check=True, capture_output=True, timeout=20,
        )
        return result


def test_no_enrolled_profile_falls_back_to_stock_with_a_reason(conn):
    engine = make_narration_engine(conn, "u1", RealAudioFakeTTS())
    assert isinstance(engine, FallbackNarrationEngine)
    assert engine.used_stock_fallback is True
    assert engine.fallback_reason == "not_enrolled"


async def test_enrolled_profile_is_used_by_default(conn, tmp_path):
    ref_wav = tmp_path / "ref.wav"
    _make_tone_wav(ref_wav, frequency=300)
    embedding_path = tmp_path / "embedding.pt"
    save_embedding(extract_embedding(ref_wav), embedding_path)

    conn.execute(
        "INSERT INTO voice_profiles (id, user_id, kind, embedding_path, consented) "
        "VALUES ('vp1', 'u1', 'cloned', ?, 1)",
        (str(embedding_path),),
    )
    conn.commit()

    engine = make_narration_engine(conn, "u1", RealAudioFakeTTS())
    assert engine.used_stock_fallback is False

    out_path = tmp_path / "scene-1.mp3"
    result = await engine.speak("hello world", "any-voice", out_path)

    assert out_path.exists()
    assert engine.used_stock_fallback is False
    assert len(result.timings) == 2


async def test_conversion_failure_falls_back_and_records_the_reason(conn, tmp_path):
    # A voice_profiles row pointing at a nonexistent embedding file -
    # conversion must fail cleanly and fall back, not crash the render.
    conn.execute(
        "INSERT INTO voice_profiles (id, user_id, kind, embedding_path, consented) "
        "VALUES ('vp1', 'u1', 'cloned', ?, 1)",
        (str(tmp_path / "missing-embedding.pt"),),
    )
    conn.commit()

    engine = make_narration_engine(conn, "u1", RealAudioFakeTTS())
    out_path = tmp_path / "scene-1.mp3"
    result = await engine.speak("hello world", "any-voice", out_path)

    assert out_path.exists()  # the stock fallback still produced real audio
    assert engine.used_stock_fallback is True
    assert engine.fallback_reason is not None
    assert len(result.timings) == 2
