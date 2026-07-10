"""HTTP client for the VM's /api/worker protocol. All connections are
outbound HTTPS initiated here — the PC exposes nothing.

The transport is injectable (any requests-compatible session) so the agent
loop is tested against a fake VM without sockets.
"""
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


@dataclass
class TaskLease:
    id: str
    kind: str
    payload: dict
    inputs: list[dict]  # [{"name": …, "url": relative path}]


class RateLimitedReader:
    """Paces a file upload to a configured Mbit/s so a night of scene_gen
    uploads doesn't saturate the owner's uplink (config: bandwidth cap)."""

    def __init__(self, fileobj, limit_mbps: float, sleep=time.sleep, clock=time.monotonic):
        self._f = fileobj
        self._bytes_per_s = limit_mbps * 1024 * 1024 / 8 if limit_mbps > 0 else 0
        self._sleep = sleep
        self._clock = clock
        self._started: float | None = None
        self._sent = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._f.read(size)
        if not chunk or not self._bytes_per_s:
            return chunk
        if self._started is None:
            self._started = self._clock()
        self._sent += len(chunk)
        expected_elapsed = self._sent / self._bytes_per_s
        actual_elapsed = self._clock() - self._started
        if expected_elapsed > actual_elapsed:
            self._sleep(expected_elapsed - actual_elapsed)
        return chunk


class VMClient:
    def __init__(self, vm_url: str, token: str, session: Optional[requests.Session] = None,
                 bandwidth_limit_mbps: float = 0.0):
        self._vm_url = vm_url.rstrip("/")
        self._session = session or requests.Session()
        self._headers = {"X-Worker-Token": token}
        self._bandwidth_limit_mbps = bandwidth_limit_mbps

    def poll(self, capabilities: list[str], vram_free_mb: Optional[int],
             wait_s: float) -> Optional[TaskLease]:
        resp = self._session.post(
            f"{self._vm_url}/api/worker/poll",
            json={"capabilities": capabilities, "vram_free_mb": vram_free_mb, "wait_s": wait_s},
            headers=self._headers,
            timeout=wait_s + 15,
        )
        resp.raise_for_status()
        task = resp.json().get("task")
        if task is None:
            return None
        return TaskLease(id=task["id"], kind=task["kind"], payload=task["payload"],
                         inputs=task["inputs"])

    def heartbeat(self, task_id: str, progress: float) -> bool:
        """False = the lease was reclaimed; abort and discard."""
        resp = self._session.post(
            f"{self._vm_url}/api/worker/heartbeat",
            json={"task_id": task_id, "progress": progress},
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        return bool(resp.json().get("still_leased"))

    def download(self, url_path: str, dest: Path) -> None:
        """Signed one-time URL: the token in the path is the credential."""
        resp = self._session.get(f"{self._vm_url}{url_path}", timeout=120, stream=True)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)

    def complete(self, task_id: str, result_path: Path) -> None:
        with result_path.open("rb") as f:
            reader = RateLimitedReader(f, self._bandwidth_limit_mbps)
            resp = self._session.post(
                f"{self._vm_url}/api/worker/complete/{task_id}",
                files={"result": (result_path.name, reader)},
                headers=self._headers,
                timeout=30 * 60,
            )
        resp.raise_for_status()

    def fail(self, task_id: str, error: str) -> None:
        resp = self._session.post(
            f"{self._vm_url}/api/worker/fail",
            json={"task_id": task_id, "error": error[:2000]},
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
