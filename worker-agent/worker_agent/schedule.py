"""Work-hours schedule — specs/03-design/11-gpu-worker.md rule 3.

Windows are "HH:MM-HH:MM" strings; a window may cross midnight
("22:00-08:00" = overnight). Empty list = always active. Outside every
window the agent idles at zero GPU cost (it doesn't even poll the VM,
which is what flips the site's tier badge to offline).
"""
from datetime import time


def _parse_window(window: str) -> tuple[time, time]:
    start_s, end_s = window.split("-")
    sh, sm = start_s.strip().split(":")
    eh, em = end_s.strip().split(":")
    return time(int(sh), int(sm)), time(int(eh), int(em))


def in_active_window(now: time, windows: list[str]) -> bool:
    if not windows:
        return True
    for window in windows:
        start, end = _parse_window(window)
        if start <= end:
            if start <= now < end:
                return True
        else:  # crosses midnight
            if now >= start or now < end:
                return True
    return False
