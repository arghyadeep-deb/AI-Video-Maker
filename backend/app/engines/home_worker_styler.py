"""Local portrait styler via the owner's home GPU worker — task-22, risk R2's
wired fallback (specs/06-risks-and-future/01-risks.md). Mirrors
app/engines/talking_head/home_worker.py's pattern exactly: any failure here
(worker offline, no `styler` capability advertised, engine crash, lease
lost) raises for the caller to catch and fall through to the next tier -
avatar_styling.py's existing raw-selfie degrade never goes away, it just
becomes the last resort instead of the only outcome.
"""
from pathlib import Path
from typing import Callable, Optional

from app.core.config import Settings
from app.core.ids import new_id
from app.db.connection import get_connection
from app.jobs import gpu_router
from app.jobs.gpu_router import HomeWorkerUnavailable


class HomeWorkerImageStyler:
    def __init__(
        self,
        db_path: Path,
        settings: Settings,
        cancelled: Optional[Callable[[], bool]] = None,
    ):
        self._db_path = db_path
        self._settings = settings
        self._cancelled = cancelled

    async def style(self, selfie_bytes: bytes, selfie_mime_type: str, persona_description: str) -> bytes:
        conn = get_connection(self._db_path)
        try:
            if "styler" not in gpu_router.worker_capabilities(conn, self._settings):
                raise HomeWorkerUnavailable(
                    "home GPU worker is offline or doesn't advertise styler"
                )
            # A unique per-call scratch file - a fixed shared path would let
            # two concurrent restyle requests clobber each other's input.
            ext = ".png" if selfie_mime_type == "image/png" else ".jpg"
            selfie_path = self._settings.media_root / "tmp" / f"styler_input_{new_id()}{ext}"
            selfie_path.parent.mkdir(parents=True, exist_ok=True)
            selfie_path.write_bytes(selfie_bytes)
            task_id = gpu_router.submit_task(
                conn,
                "styler",
                {"prompt": persona_description, "width": 1024, "height": 1024},
                [{"name": f"selfie{ext}", "path": str(selfie_path)}],
            )
        finally:
            conn.close()

        try:
            # Raises GpuTaskFailed on worker loss / engine crash / timeout —
            # avatar_styling.stage_style catches it and falls to the
            # raw-selfie degrade, exactly as it already does for
            # ImageStylerUnavailableError.
            row = await gpu_router.wait_for_task(
                self._db_path, task_id, self._settings, cancelled=self._cancelled
            )
            return Path(row["result_path"]).read_bytes()
        finally:
            selfie_path.unlink(missing_ok=True)
