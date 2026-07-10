"""Optional system-tray icon (pause/resume/quit) — pystray + Pillow.
The agent is fully functional headless; the tray is a convenience layer,
so a missing pystray downgrades to console mode instead of crashing.
"""
import logging
import threading

log = logging.getLogger("worker_agent")


def run_with_tray(agent) -> None:
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        log.info("pystray/Pillow not installed - running headless (Ctrl+C to stop)")
        agent.run_forever()
        return

    def _icon_image(active: bool):
        img = Image.new("RGB", (64, 64), (18, 18, 18))
        draw = ImageDraw.Draw(img)
        color = (80, 200, 120) if active else (200, 160, 60)
        draw.ellipse((12, 12, 52, 52), fill=color)
        return img

    def on_pause(icon, item):
        # Design doc rule 2, instant reclaim: aborts the in-flight job too.
        agent.pause_now()
        icon.icon = _icon_image(active=False)

    def on_resume(icon, item):
        agent.resume()
        icon.icon = _icon_image(active=True)

    def on_quit(icon, item):
        agent.stop()
        icon.stop()

    icon = pystray.Icon(
        "aivideomaker-worker",
        _icon_image(active=True),
        "AI Video Maker GPU worker",
        menu=pystray.Menu(
            pystray.MenuItem("Pause now", on_pause),
            pystray.MenuItem("Resume", on_resume),
            pystray.MenuItem("Quit", on_quit),
        ),
    )
    loop = threading.Thread(target=agent.run_forever, daemon=True)
    loop.start()
    icon.run()  # blocks until Quit
