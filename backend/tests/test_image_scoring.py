from app.engines.images.scoring import (
    MIN_SHORT_EDGE,
    matches_orientation,
    meets_resolution_bar,
    orientation_of,
    pick_best,
    usable_candidates,
)
from app.models.image import ImageCandidate


def _candidate(source_id: str, width: int, height: int, source: str = "pexels") -> ImageCandidate:
    return ImageCandidate(source=source, source_id=source_id, url="https://x/img.jpg", width=width, height=height)


def test_meets_resolution_bar():
    assert meets_resolution_bar(_candidate("1", 1920, 1200))  # short edge 1200 >= 1080
    assert not meets_resolution_bar(_candidate("2", 800, 1200))  # short edge 800 < 1080
    assert meets_resolution_bar(_candidate("3", MIN_SHORT_EDGE, 2000))


def test_orientation_of():
    assert orientation_of(_candidate("1", 1080, 1920)) == "9x16"  # taller than wide
    assert orientation_of(_candidate("2", 1920, 1080)) == "16x9"  # wider than tall
    assert orientation_of(_candidate("3", 1080, 1080)) == "9x16"  # square counted as portrait (height >= width)


def test_matches_orientation():
    portrait = _candidate("1", 1080, 1920)
    assert matches_orientation(portrait, "9x16")
    assert not matches_orientation(portrait, "16x9")


def test_usable_candidates_filters_low_resolution():
    good = _candidate("1", 1920, 1200)
    bad = _candidate("2", 500, 900)
    assert usable_candidates([good, bad]) == [good]


def test_pick_best_prefers_orientation_match():
    landscape = _candidate("1", 1920, 1080)
    portrait = _candidate("2", 1080, 1920)
    chosen = pick_best([landscape, portrait], "9x16", already_used=set())
    assert chosen.source_id == "2"


def test_pick_best_prefers_unused_when_orientation_ties():
    used = _candidate("used", 1080, 1920)
    fresh = _candidate("fresh", 1080, 1920)
    chosen = pick_best([used, fresh], "9x16", already_used={"used"})
    assert chosen.source_id == "fresh"


def test_pick_best_falls_back_to_reuse_rather_than_none():
    # Only a wrong-orientation, already-used candidate exists - still better
    # than leaving the scene with no image at all.
    only_option = _candidate("used", 1920, 1080)
    chosen = pick_best([only_option], "9x16", already_used={"used"})
    assert chosen is not None
    assert chosen.source_id == "used"


def test_pick_best_empty_list_returns_none():
    assert pick_best([], "9x16", set()) is None
