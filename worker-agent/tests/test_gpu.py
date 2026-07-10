import subprocess

from worker_agent.gpu import GpuStatus, owner_is_using_gpu, probe


def test_probe_parses_nvidia_smi_csv():
    status = probe(runner=lambda cmd: "3, 15022, NVIDIA GeForce RTX 5070 Ti\n")
    assert status == GpuStatus(util_pct=3.0, vram_free_mb=15022, name="NVIDIA GeForce RTX 5070 Ti")


def test_probe_returns_none_when_nvidia_smi_missing():
    def runner(cmd):
        raise FileNotFoundError("nvidia-smi")

    assert probe(runner=runner) is None


def test_probe_returns_none_on_subprocess_failure():
    def runner(cmd):
        raise subprocess.CalledProcessError(1, cmd)

    assert probe(runner=runner) is None


def test_probe_returns_none_on_garbage_output():
    assert probe(runner=lambda cmd: "ERR!\n") is None
    assert probe(runner=lambda cmd: "") is None


def test_yield_on_high_utilization():
    status = GpuStatus(util_pct=45.0, vram_free_mb=15000, name="x")
    assert owner_is_using_gpu(status, max_util_pct=20.0, min_vram_free_mb=10240)


def test_yield_on_low_free_vram_even_at_zero_util():
    # A paused training run: 0% util but VRAM held - must still yield.
    status = GpuStatus(util_pct=0.0, vram_free_mb=4000, name="x")
    assert owner_is_using_gpu(status, max_util_pct=20.0, min_vram_free_mb=10240)


def test_idle_card_is_leaseable():
    status = GpuStatus(util_pct=2.0, vram_free_mb=15500, name="x")
    assert not owner_is_using_gpu(status, max_util_pct=20.0, min_vram_free_mb=10240)
