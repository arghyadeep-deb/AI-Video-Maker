"""The agent loop — specs/03-design/11-gpu-worker.md.

Per cycle: owner-first checks (pause -> schedule -> GPU busy), then one
long-poll. A lease runs the engine with a 10 s heartbeat thread; losing the
lease (VM says still_leased=false) or a tray pause flips the abort event —
work stops, output is discarded, the VM's lease-expiry path re-routes the
job. Task files are deleted after upload, success or not: the agent keeps
no media library (privacy: user media only transits this PC).
"""
import logging
import shutil
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from worker_agent import gpu, schedule
from worker_agent.client import TaskLease, VMClient
from worker_agent.config import AgentConfig
from worker_agent.engines.base import Engine, EngineAborted

log = logging.getLogger("worker_agent")


class Agent:
    def __init__(
        self,
        config: AgentConfig,
        client: VMClient,
        engines: dict[str, Engine],
        gpu_probe: Callable[[], Optional[gpu.GpuStatus]] = gpu.probe,
        now_fn: Callable[[], datetime] = datetime.now,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self._config = config
        self._client = client
        self._engines = engines
        self._gpu_probe = gpu_probe
        self._now = now_fn
        self._sleep = sleep_fn
        self.paused = threading.Event()   # tray "Pause now" sets this
        self._abort_current = threading.Event()
        self._stopping = threading.Event()

    # --- owner-first gate (checked between jobs, never mid-session) -------

    def idle_reason(self) -> Optional[str]:
        """None = clear to lease. A string = why the agent sits this cycle
        out (logged + shown in the tray tooltip)."""
        if self.paused.is_set():
            return "paused by owner"
        if not schedule.in_active_window(self._now().time(), self._config.active_hours):
            return "outside active hours"
        status = self._gpu_probe()
        if status is None:
            return "no usable GPU visible"
        if gpu.owner_is_using_gpu(
            status, self._config.max_gpu_util_pct, self._config.min_vram_free_mb
        ):
            return (
                f"owner is using the GPU (util {status.util_pct:.0f}%, "
                f"{status.vram_free_mb} MB free)"
            )
        return None

    # --- lease execution ---------------------------------------------------

    def pause_now(self) -> None:
        """Instant reclaim: stop leasing AND abort the in-flight task. No
        fail report on purpose — the VM's lease-expiry sweep re-queues it
        to the ZeroGPU/CPU tiers (design doc rule 2)."""
        self.paused.set()
        self._abort_current.set()

    def resume(self) -> None:
        self.paused.clear()

    def stop(self) -> None:
        self._stopping.set()
        self._abort_current.set()

    def run_once(self) -> bool:
        """One cycle. Returns True if a task was executed."""
        reason = self.idle_reason()
        if reason is not None:
            log.debug("idle: %s", reason)
            self._sleep(self._config.idle_check_interval_s)
            return False

        status = self._gpu_probe()
        lease = self._client.poll(
            capabilities=sorted(self._engines),
            vram_free_mb=status.vram_free_mb if status else None,
            wait_s=self._config.poll_wait_s,
        )
        if lease is None:
            return False
        self._run_task(lease)
        return True

    def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                self.run_once()
            except Exception:  # noqa: BLE001 - VM unreachable etc.: log, back off, keep living
                log.exception("cycle failed; backing off")
                self._sleep(self._config.idle_check_interval_s)

    def _run_task(self, lease: TaskLease) -> None:
        engine = self._engines[lease.kind]
        self._abort_current = abort = threading.Event()
        progress_value = {"pct": 0.0}

        def report_progress(pct: float) -> None:
            progress_value["pct"] = pct

        stop_beats = threading.Event()

        def heartbeat_loop() -> None:
            while not stop_beats.wait(self._config.heartbeat_interval_s):
                try:
                    still_leased = self._client.heartbeat(lease.id, progress_value["pct"])
                except Exception:  # noqa: BLE001 - transient network blip: skip this beat
                    log.warning("heartbeat failed for %s", lease.id)
                    continue
                if not still_leased:
                    log.info("lease %s reclaimed by VM; aborting", lease.id)
                    abort.set()
                    return

        self._config.work_dir.mkdir(parents=True, exist_ok=True)
        task_dir = Path(tempfile.mkdtemp(prefix=f"task-{lease.id}-", dir=self._config.work_dir))
        beats = threading.Thread(target=heartbeat_loop, daemon=True)
        beats.start()
        try:
            inputs: dict[str, Path] = {}
            for spec in lease.inputs:
                dest = task_dir / "inputs" / spec["name"]
                self._client.download(spec["url"], dest)
                inputs[spec["name"]] = dest

            log.info("running %s task %s", lease.kind, lease.id)
            result_path = engine.run(task_dir, inputs, lease.payload, abort, report_progress)
            if abort.is_set():
                log.info("task %s aborted post-run; discarding result", lease.id)
                return
            self._client.complete(lease.id, result_path)
            log.info("task %s uploaded", lease.id)
        except EngineAborted:
            log.info("task %s aborted; VM lease expiry will re-route it", lease.id)
        except Exception as exc:  # noqa: BLE001 - engine/download/upload failure
            log.exception("task %s failed", lease.id)
            if not abort.is_set():
                try:
                    self._client.fail(lease.id, str(exc))
                except Exception:  # noqa: BLE001
                    log.warning("could not report failure for %s", lease.id)
        finally:
            stop_beats.set()
            beats.join(timeout=self._config.heartbeat_interval_s + 5)
            # No media library on this PC — success or not, wipe everything.
            shutil.rmtree(task_dir, ignore_errors=True)
