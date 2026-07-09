"""Single async job worker — specs/03-design/07-job-queue-and-progress.md.

One media job at a time (media steps saturate a small VM; concurrency would
thrash). Runs as an asyncio task inside the FastAPI process — no external
broker, per specs/01-requirements/07-free-stack-lock.md.
"""
import asyncio
import json
import traceback
from pathlib import Path

from app.core.time_utils import iso_now
from app.db.connection import get_connection
from app.jobs import queue as job_queue
from app.jobs.registry import AwaitingUser, JobCancelled, JobContext, get_pipeline

MAX_ERROR_CHARS = 2000
POLL_INTERVAL_S = 0.05


class Worker:
    def __init__(self, db_path: Path, poll_interval: float = POLL_INTERVAL_S):
        self._db_path = db_path
        self._poll_interval = poll_interval
        self._cancel_flags: set[str] = set()
        self._processes: dict[str, list[asyncio.subprocess.Process]] = {}
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            await self._task
            self._task = None

    def request_cancel(self, job_id: str) -> None:
        self._cancel_flags.add(job_id)
        for proc in self._processes.get(job_id, []):
            if proc.returncode is None:
                proc.kill()

    async def _run_forever(self) -> None:
        while not self._stopping:
            conn = get_connection(self._db_path)
            try:
                job = job_queue.claim_next_job(conn)
            finally:
                conn.close()

            if job is None:
                await asyncio.sleep(self._poll_interval)
                continue

            await self._run_job(job["id"], job["type"], json.loads(job["payload_json"] or "{}"))

    async def _run_job(self, job_id: str, job_type: str, payload: dict) -> None:
        conn = get_connection(self._db_path)
        try:
            try:
                pipeline = get_pipeline(job_type)
            except KeyError as exc:
                self._fail(conn, job_id, str(exc))
                return

            def cancelled() -> bool:
                return job_id in self._cancel_flags

            def register_process(proc: asyncio.subprocess.Process) -> None:
                self._processes.setdefault(job_id, []).append(proc)

            def make_report(stage_name: str):
                def _report(pct: float) -> None:
                    conn.execute(
                        "UPDATE jobs SET stage = ?, progress = ? WHERE id = ?",
                        (stage_name, pct, job_id),
                    )
                    conn.commit()

                return _report

            try:
                for stage_name, step in pipeline:
                    if cancelled():
                        self._mark_cancelled(conn, job_id)
                        return
                    conn.execute(
                        "UPDATE jobs SET stage = ?, progress = 0 WHERE id = ?", (stage_name, job_id)
                    )
                    conn.commit()
                    ctx = JobContext(
                        job_id=job_id,
                        payload=payload,
                        report=make_report(stage_name),
                        cancelled=cancelled,
                        register_process=register_process,
                    )
                    await step(ctx)
                    if cancelled():
                        self._mark_cancelled(conn, job_id)
                        return
                self._mark_done(conn, job_id)
            except JobCancelled:
                self._mark_cancelled(conn, job_id)
            except AwaitingUser:
                self._mark_awaiting_user(conn, job_id)
            except Exception as exc:  # noqa: BLE001 - any pipeline step failure lands here
                message = f"{exc}\n{traceback.format_exc()}"[-MAX_ERROR_CHARS:]
                self._fail(conn, job_id, message)
        finally:
            self._cancel_flags.discard(job_id)
            self._processes.pop(job_id, None)
            conn.close()

    def _mark_done(self, conn, job_id: str) -> None:
        conn.execute(
            "UPDATE jobs SET status = 'done', stage = NULL, progress = 100, finished_at = ? WHERE id = ?",
            (iso_now(), job_id),
        )
        conn.commit()

    def _mark_cancelled(self, conn, job_id: str) -> None:
        conn.execute(
            "UPDATE jobs SET status = 'cancelled', finished_at = ? WHERE id = ?",
            (iso_now(), job_id),
        )
        conn.commit()

    def _mark_awaiting_user(self, conn, job_id: str) -> None:
        # finished_at is set even though this isn't a truly terminal state -
        # the fairness scheduler (queue.py:_last_served_at) uses it to know
        # this user's worker turn is over; the job just isn't "done" yet.
        conn.execute(
            "UPDATE jobs SET status = 'awaiting_user', finished_at = ? WHERE id = ?",
            (iso_now(), job_id),
        )
        conn.commit()

    def _fail(self, conn, job_id: str, message: str) -> None:
        conn.execute(
            "UPDATE jobs SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
            (message, iso_now(), job_id),
        )
        conn.commit()
