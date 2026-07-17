"""Entry point: `python -m worker_agent [--config path] [--no-tray]`."""
import argparse
import logging
import sys
from pathlib import Path

from worker_agent import gpu
from worker_agent.agent import Agent
from worker_agent.client import VMClient
from worker_agent.config import load_config
from worker_agent.engines import discover


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Video Maker home GPU worker agent")
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).resolve().parents[1] / "config.toml"
    )
    parser.add_argument("--no-tray", action="store_true", help="run headless")
    args = parser.parse_args()

    # Headless launch (pythonw.exe, Scheduled Task at logon) has no console -
    # stdout/stderr are discarded, not merely hidden, so basicConfig's default
    # StreamHandler writes into the void. A FileHandler is the only way to
    # see anything from this process once it's running silently in the
    # background - found live 2026-07-16 while debugging a scene_gen
    # fallback with zero visibility into what the agent actually did.
    log_path = Path(__file__).resolve().parents[1] / "agent_run.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
    )
    log = logging.getLogger("worker_agent")

    if not args.config.exists():
        log.error("No config at %s - copy config.example.toml and fill in vm_url/token", args.config)
        return 2
    config = load_config(args.config)

    status = gpu.probe()
    if status is None:
        log.error("nvidia-smi found no usable GPU - the agent has nothing to offer, exiting")
        return 2
    log.info("GPU: %s, %d MB free", status.name, status.vram_free_mb)

    engines = discover(config, status)
    if not engines:
        log.error(
            "No engines passed their probe (checked: %s) - see setup.md for installing "
            "engine dependencies", ", ".join(config.engines),
        )
        return 2
    log.info("advertising capabilities: %s", ", ".join(sorted(engines)))

    client = VMClient(config.vm_url, config.token, bandwidth_limit_mbps=config.bandwidth_limit_mbps)
    agent = Agent(config, client, engines)

    if args.no_tray:
        try:
            agent.run_forever()
        except KeyboardInterrupt:
            agent.stop()
    else:
        from worker_agent.tray import run_with_tray

        run_with_tray(agent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
