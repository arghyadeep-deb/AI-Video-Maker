from pathlib import Path

from app.engines.ffmpeg.finishing import build_scale_pad_filter, escaped_ffmpeg_path, needs_padding


def test_portrait_source_into_9x16_is_native_no_padding():
    assert needs_padding(720, 1280, 1080, 1920) is False


def test_portrait_source_into_16x9_needs_padding():
    assert needs_padding(720, 1280, 1920, 1080) is True


def test_landscape_source_into_16x9_is_native_no_padding():
    assert needs_padding(1280, 720, 1920, 1080) is False


def test_landscape_source_into_9x16_needs_padding():
    assert needs_padding(1280, 720, 1080, 1920) is True


def test_square_avatar_source_never_needs_padding_for_either_format():
    # This product's actual case - avatar portraits are always 1024x1024.
    assert needs_padding(1024, 1024, 1080, 1920) is False
    assert needs_padding(1024, 1024, 1920, 1080) is False


def test_scale_pad_filter_uses_cover_crop_when_no_padding_needed():
    filt = build_scale_pad_filter(1024, 1024, 1080, 1920)
    assert "split=2" not in filt
    assert "gblur" not in filt
    assert "crop=1080:1920" in filt


def test_scale_pad_filter_uses_blurred_pad_when_padding_needed():
    filt = build_scale_pad_filter(1280, 720, 1080, 1920)
    assert "split=2" in filt
    assert "gblur=sigma=20" in filt
    assert "overlay=(W-w)/2:(H-h)/2" in filt


def test_escaped_ffmpeg_path_escapes_windows_drive_colon():
    assert escaped_ffmpeg_path(Path("C:/Users/x/subs.ass")) == "C\\:/Users/x/subs.ass"


def test_escaped_ffmpeg_path_leaves_posix_paths_alone():
    assert escaped_ffmpeg_path(Path("/home/x/subs.ass")) == "/home/x/subs.ass"
