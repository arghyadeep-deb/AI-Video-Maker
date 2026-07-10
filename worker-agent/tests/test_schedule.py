from datetime import time

from worker_agent.schedule import in_active_window


def test_empty_windows_means_always_active():
    assert in_active_window(time(3, 0), [])


def test_simple_daytime_window():
    assert in_active_window(time(12, 0), ["09:00-17:00"])
    assert not in_active_window(time(8, 59), ["09:00-17:00"])
    assert not in_active_window(time(17, 0), ["09:00-17:00"])  # end-exclusive


def test_overnight_window_crosses_midnight():
    windows = ["22:00-08:00"]
    assert in_active_window(time(23, 30), windows)
    assert in_active_window(time(3, 0), windows)
    assert not in_active_window(time(12, 0), windows)
    assert in_active_window(time(22, 0), windows)   # start-inclusive
    assert not in_active_window(time(8, 0), windows)  # end-exclusive


def test_multiple_windows_any_match_wins():
    windows = ["06:00-08:00", "20:00-23:00"]
    assert in_active_window(time(7, 0), windows)
    assert in_active_window(time(21, 0), windows)
    assert not in_active_window(time(12, 0), windows)
