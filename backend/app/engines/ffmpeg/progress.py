"""FFmpeg `-progress` stdout parser + subprocess runner —
specs/03-design/07-job-queue-and-progress.md (FFmpeg sub-progress -> `report(pct)`).

Note: ffmpeg's `-progress` key `out_time_ms` is, despite the name, actually
in *microseconds* (a long-standing ffmpeg naming quirk kept for backwards
compatibility) — confirmed against this project's installed ffmpeg 8.1.2.
"""
import asyncio
from typing import Callable, Optional

MAX_STDERR_TAIL_LINES = 20


def parse_progress_line(line: str) -> Optional[tuple[str, str]]:
    line = line.strip()
    if not line or "=" not in line:
        return None
    key, _, value = line.partition("=")
    return key, value


class FFmpegError(Exception):
    pass


async def run_with_progress(
    args: list[str],
    total_duration_s: float,
    report: Callable[[float], None],
    register_process: Optional[Callable[[asyncio.subprocess.Process], None]] = None,
) -> None:
    full_args = [*args, "-progress", "pipe:1", "-nostats"]
    process = await asyncio.create_subprocess_exec(
        *full_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if register_process is not None:
        register_process(process)

    stderr_lines: list[str] = []

    async def _drain_stderr() -> None:
        assert process.stderr is not None
        async for raw in process.stderr:
            stderr_lines.append(raw.decode(errors="replace").rstrip("\n"))

    stderr_task = asyncio.create_task(_drain_stderr())

    assert process.stdout is not None
    async for raw_line in process.stdout:
        parsed = parse_progress_line(raw_line.decode(errors="replace"))
        if parsed is None:
            continue
        key, value = parsed
        if key in ("out_time_us", "out_time_ms") and total_duration_s > 0:
            try:
                microseconds = int(value)
            except ValueError:
                continue
            out_s = microseconds / 1_000_000
            report(min(100.0, max(0.0, out_s / total_duration_s * 100)))
        elif key == "progress" and value == "end":
            report(100.0)

    returncode = await process.wait()
    await stderr_task

    if returncode != 0:
        tail = "\n".join(stderr_lines[-MAX_STDERR_TAIL_LINES:])
        raise FFmpegError(f"ffmpeg exited {returncode}:\n{tail}")
