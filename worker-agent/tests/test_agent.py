"""Agent loop tests against a fake VM client — no sockets, no GPU."""
import threading
from datetime import datetime
from pathlib import Path

from worker_agent.agent import Agent
from worker_agent.client import RateLimitedReader, TaskLease
from worker_agent.config import AgentConfig
from worker_agent.engines.base import Engine, EngineAborted, EngineError
from worker_agent.gpu import GpuStatus

IDLE_GPU = GpuStatus(util_pct=2.0, vram_free_mb=15500, name="RTX 5070 Ti")
BUSY_GPU = GpuStatus(util_pct=85.0, vram_free_mb=2000, name="RTX 5070 Ti")


def make_config(tmp_path: Path, **overrides) -> AgentConfig:
    cfg = AgentConfig()
    cfg.vm_url = "https://vm.test"
    cfg.token = "t"
    cfg.work_dir = tmp_path / "work"
    cfg.heartbeat_interval_s = 0.05
    cfg.idle_check_interval_s = 0.0
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


class FakeClient:
    def __init__(self, lease=None, still_leased=True):
        self.lease = lease
        self.still_leased = still_leased
        self.polls = []
        self.completed = []
        self.failed = []
        self.downloads = []

    def poll(self, capabilities, vram_free_mb, wait_s):
        self.polls.append(capabilities)
        lease, self.lease = self.lease, None  # one-shot
        return lease

    def heartbeat(self, task_id, progress):
        return self.still_leased

    def download(self, url_path, dest: Path):
        self.downloads.append(url_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"input-bytes")

    def complete(self, task_id, result_path: Path):
        # Read while the file still exists (the agent wipes task_dir after).
        self.completed.append((task_id, result_path.read_bytes()))

    def fail(self, task_id, error):
        self.failed.append((task_id, error))


class OkEngine(Engine):
    name = "fake"
    vram_required_mb = 0

    def probe(self):
        return True

    def run(self, task_dir, inputs, payload, abort, progress):
        assert inputs["scene.jpg"].read_bytes() == b"input-bytes"
        out = task_dir / "result.mp4"
        out.write_bytes(b"rendered")
        progress(100.0)
        return out


class SlowEngine(Engine):
    """Loops until abort fires (or 5 s safety cap) - the reclaim tests."""
    name = "fake"
    vram_required_mb = 0

    def probe(self):
        return True

    def run(self, task_dir, inputs, payload, abort, progress):
        if abort.wait(timeout=5.0):
            raise EngineAborted("reclaimed")
        raise AssertionError("abort never fired")


class CrashEngine(Engine):
    name = "fake"
    vram_required_mb = 0

    def probe(self):
        return True

    def run(self, task_dir, inputs, payload, abort, progress):
        raise EngineError("CUDA OOM")


LEASE = TaskLease(
    id="task-1", kind="fake", payload={"prompt": "x"},
    inputs=[{"name": "scene.jpg", "url": "/api/worker/files/tok"}],
)


def make_agent(tmp_path, client, engine, gpu_status=IDLE_GPU, **cfg_overrides):
    return Agent(
        make_config(tmp_path, **cfg_overrides),
        client,
        {"fake": engine},
        gpu_probe=lambda: gpu_status,
        now_fn=datetime.now,
        sleep_fn=lambda s: None,
    )


# --- owner-first gate --------------------------------------------------------

def test_idle_when_paused(tmp_path):
    agent = make_agent(tmp_path, FakeClient(), OkEngine())
    agent.paused.set()
    assert agent.idle_reason() == "paused by owner"


def test_idle_outside_active_hours(tmp_path):
    agent = make_agent(tmp_path, FakeClient(), OkEngine(), active_hours=["02:00-02:01"])
    agent._now = lambda: datetime(2026, 7, 10, 12, 0)
    assert "active hours" in agent.idle_reason()


def test_idle_when_owner_uses_gpu(tmp_path):
    agent = make_agent(tmp_path, FakeClient(), OkEngine(), gpu_status=BUSY_GPU)
    assert "owner is using the GPU" in agent.idle_reason()


def test_idle_agent_does_not_poll(tmp_path):
    client = FakeClient(lease=LEASE)
    agent = make_agent(tmp_path, client, OkEngine(), gpu_status=BUSY_GPU)
    assert agent.run_once() is False
    assert client.polls == []  # never even talked to the VM


def test_clear_gpu_leases(tmp_path):
    agent = make_agent(tmp_path, FakeClient(), OkEngine())
    assert agent.idle_reason() is None


# --- lease execution ---------------------------------------------------------

def test_happy_path_downloads_runs_uploads_and_wipes(tmp_path):
    client = FakeClient(lease=LEASE)
    agent = make_agent(tmp_path, client, OkEngine())
    assert agent.run_once() is True
    assert client.downloads == ["/api/worker/files/tok"]
    assert client.completed == [("task-1", b"rendered")]
    assert client.failed == []
    # No media library: the task dir is gone, success or not.
    work_dir = tmp_path / "work"
    assert not any(work_dir.iterdir())


def test_lease_reclaimed_aborts_without_fail_report(tmp_path):
    # VM says still_leased=false -> abort fires -> engine raises
    # EngineAborted -> NO complete, NO fail (the VM's expiry path owns
    # re-routing; an explicit fail would wrongly kill the task for good).
    client = FakeClient(lease=LEASE, still_leased=False)
    agent = make_agent(tmp_path, client, SlowEngine())
    assert agent.run_once() is True
    assert client.completed == []
    assert client.failed == []


def test_pause_now_aborts_in_flight_task(tmp_path):
    client = FakeClient(lease=LEASE)
    agent = make_agent(tmp_path, client, SlowEngine())

    timer = threading.Timer(0.2, agent.pause_now)
    timer.start()
    try:
        agent.run_once()
    finally:
        timer.cancel()
    assert client.completed == []
    assert client.failed == []
    assert agent.paused.is_set()


def test_engine_crash_reports_fail(tmp_path):
    client = FakeClient(lease=LEASE)
    agent = make_agent(tmp_path, client, CrashEngine())
    agent.run_once()
    assert client.completed == []
    assert len(client.failed) == 1
    assert "CUDA OOM" in client.failed[0][1]
    work_dir = tmp_path / "work"
    assert not any(work_dir.iterdir())  # wiped on failure too


def test_capabilities_advertised_are_engine_names(tmp_path):
    client = FakeClient()
    agent = make_agent(tmp_path, client, OkEngine())
    agent.run_once()
    assert client.polls == [["fake"]]


# --- upload pacing -----------------------------------------------------------

def test_rate_limited_reader_paces_upload():
    class Src:
        def __init__(self):
            self.remaining = [b"x" * 1024 * 1024] * 4  # 4 MB

        def read(self, size=-1):
            return self.remaining.pop(0) if self.remaining else b""

    sleeps = []
    clock = {"t": 0.0}
    # 8 Mbit/s = 1 MB/s -> 4 MB should be paced to ~4 s of sleep.
    reader = RateLimitedReader(
        Src(), limit_mbps=8.0, sleep=sleeps.append, clock=lambda: clock["t"]
    )
    while reader.read(1024 * 1024):
        pass
    assert sum(sleeps) >= 3.0  # first chunk starts the clock; ~3s of pacing after it


def test_rate_limited_reader_unlimited_never_sleeps():
    class Src:
        def __init__(self):
            self.remaining = [b"x" * 1024] * 3

        def read(self, size=-1):
            return self.remaining.pop(0) if self.remaining else b""

    sleeps = []
    reader = RateLimitedReader(Src(), limit_mbps=0.0, sleep=sleeps.append)
    while reader.read(1024):
        pass
    assert sleeps == []
