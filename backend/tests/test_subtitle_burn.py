"""Render test: burn committed golden ASS onto a color background via
ffmpeg (task-06's own Tests section). Confirms the whole chain — template,
fontsdir, libass/HarfBuzz shaping — actually works, not just that the ASS
text is well-formed. Skips if ffmpeg isn't on PATH (task-01's health check
already reports this honestly; this test doesn't re-litigate it).

Visual correctness (no tofu, correct conjunct/matra shaping) still needs a
human or multimodal look at the output frame — this test only proves the
pipeline runs end-to-end and draws *something* non-blank where subtitles
should be.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

FONTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
GOLDEN_DIR = Path(__file__).parent / "golden"

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def _escaped_fontsdir() -> str:
    # ffmpeg's filtergraph parser splits on ':' - a bare Windows drive
    # letter colon (C:) breaks it; escape it, forward-slash the rest.
    posix = str(FONTS_DIR).replace("\\", "/")
    if len(posix) > 1 and posix[1] == ":":
        posix = posix[0] + "\\:" + posix[2:]
    return posix


def _burn_frame(ass_path: Path, width: int, height: int, seek_s: float, out_name: str) -> Path:
    vf = f"ass={ass_path.name}:fontsdir='{_escaped_fontsdir()}'"
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=0x1a1a2e:s={width}x{height}:d=10",
            "-vf", vf,
            "-update", "1", "-frames:v", "1", "-ss", str(seek_s),
            out_name,
        ],
        cwd=ass_path.parent,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    out_path = ass_path.parent / out_name
    assert out_path.exists()
    return out_path


def _is_mostly_background(png_path: Path) -> bool:
    """Cheap non-blank check: a render with subtitle text burned in should
    differ from a render of the same background with no subtitles at all
    (different file size is a good enough proxy without a PNG decoder).
    """
    return png_path.stat().st_size > 0


@pytest.mark.parametrize(
    "golden_name,width,height,seek_s",
    [
        ("hindi_example.ass", 1080, 1920, 0.5),
        ("english_example.ass", 1920, 1080, 0.5),
    ],
)
def test_burn_golden_ass_onto_color_background(tmp_path, golden_name, width, height, seek_s):
    ass_content = (GOLDEN_DIR / golden_name).read_text(encoding="utf-8")
    ass_path = tmp_path / golden_name
    ass_path.write_text(ass_content, encoding="utf-8")

    out_path = _burn_frame(ass_path, width, height, seek_s, "frame.png")
    assert _is_mostly_background(out_path)

    # A render with subtitles on should be a strictly larger PNG than the
    # bare background (more distinct pixels to encode) - a cheap structural
    # proxy that *something* was actually drawn, not a silent no-op filter.
    blank_ass = ass_path.with_name("blank.ass")
    blank_content = ass_content.split("[Events]")[0] + "[Events]\n"
    blank_ass.write_text(blank_content, encoding="utf-8")
    blank_out = _burn_frame(blank_ass, width, height, seek_s, "blank.png")

    assert out_path.stat().st_size > blank_out.stat().st_size
