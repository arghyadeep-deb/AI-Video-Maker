"""SadTalker on the owner's home GPU via the pull-worker — task-20a,
specs/03-design/11-gpu-worker.md. Tier 1 of the three-tier routing: the
chooser tries this first while the worker is online, and any failure here
(worker went to sleep, engine crash on the PC, lease lost) falls through to
ZeroGPU/Wav2Lip — a user's render never dies because the owner's PC did.
"""
import shutil
from pathlib import Path
from typing import Callable, Optional

from app.core.config import Settings
from app.db.connection import get_connection
from app.engines.talking_head.base import TalkingHeadEngine, TalkingHeadResult
from app.jobs import gpu_router
from app.jobs.gpu_router import HomeWorkerUnavailable


class HomeWorkerTalkingHeadEngine(TalkingHeadEngine):
    def __init__(
        self,
        db_path: Path,
        settings: Settings,
        cancelled: Optional[Callable[[], bool]] = None,
    ):
        self._db_path = db_path
        self._settings = settings
        self._cancelled = cancelled

    async def render(
        self, portrait_path: str, wav_path: str, output_path: str
    ) -> TalkingHeadResult:
        conn = get_connection(self._db_path)
        try:
            if "sadtalker" not in gpu_router.worker_capabilities(conn, self._settings):
                raise HomeWorkerUnavailable(
                    "home GPU worker is offline or doesn't advertise sadtalker"
                )
            task_id = gpu_router.submit_task(
                conn,
                "sadtalker",
                {},
                [
                    {"name": f"portrait{Path(portrait_path).suffix or '.jpg'}", "path": portrait_path},
                    {"name": "audio.wav", "path": wav_path},
                ],
            )
        finally:
            conn.close()

        # Raises GpuTaskFailed on worker loss / engine crash / timeout —
        # the chooser catches it and falls to the next tier.
        row = await gpu_router.wait_for_task(
            self._db_path, task_id, self._settings, cancelled=self._cancelled
        )
        shutil.copyfile(row["result_path"], output_path)
        return TalkingHeadResult(video_path=output_path, engine="sadtalker-home")
