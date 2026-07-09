from app.engines.ffmpeg.audio_mix import build_music_duck_filter
from app.engines.ffmpeg.builder import input_music_looped


def test_duck_filter_references_both_labels():
    filt = build_music_duck_filter("1:a", "0:a", duration_s=30.0)
    assert "[1:a]" in filt
    assert "[0:a]" in filt


def test_duck_filter_uses_sidechaincompress():
    filt = build_music_duck_filter("1:a", "0:a", duration_s=30.0)
    assert "sidechaincompress" in filt


def test_duck_filter_fades_out_near_the_end():
    filt = build_music_duck_filter("1:a", "0:a", duration_s=30.0)
    assert "afade=t=out:st=28.500:d=1.5" in filt


def test_duck_filter_fade_start_never_goes_negative_for_short_clips():
    filt = build_music_duck_filter("1:a", "0:a", duration_s=1.0)
    assert "afade=t=out:st=0.000:d=1.5" in filt


def test_duck_filter_mixes_into_the_requested_output_label():
    filt = build_music_duck_filter("1:a", "0:a", duration_s=30.0, output_label="mixed")
    assert filt.endswith("[mixed]")


def test_duck_filter_splits_the_narration_label_before_reusing_it():
    """A filtergraph label is consumed the first time it's used as an
    input - narration is used twice (sidechain trigger + final mix), so it
    must be asplit first or ffmpeg rejects the graph with "matches no
    streams" (a real bug this test locks in, found by actually running
    ffmpeg, not by reading the filter docs)."""
    filt = build_music_duck_filter("1:a", "0:a", duration_s=30.0)
    assert "asplit=2" in filt
    assert filt.count("[0:a]") == 1  # the raw narration label appears exactly once (feeding asplit)


def test_input_music_looped_puts_dash_t_before_dash_i():
    args = input_music_looped(__file__, 12.5)  # any path-like string works here
    assert args == ["-stream_loop", "-1", "-t", "12.500", "-i", __file__]
