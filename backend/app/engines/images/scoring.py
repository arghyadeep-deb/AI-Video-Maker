"""Resolution/orientation/dedupe scoring — specs/02-research/05-stock-image-apis.md.

Selection heuristic (design input for task-08):
    1. Query = scene visual_hint; request 5 candidates.
    2. Score: resolution >=1080px short edge -> orientation match -> not
       already used in this video.
    3. Zero usable results from both stock APIs -> nano banana generation.

"Usable" means clearing the resolution bar; orientation match and
not-already-used are tiebreak preferences among usable candidates, not
hard filters (a usable-but-wrong-orientation repeat still beats no image
at all for that scene).
"""
from app.models.image import ImageCandidate

MIN_SHORT_EDGE = 1080


def short_edge(candidate: ImageCandidate) -> int:
    return min(candidate.width, candidate.height)


def meets_resolution_bar(candidate: ImageCandidate) -> bool:
    return short_edge(candidate) >= MIN_SHORT_EDGE


def orientation_of(candidate: ImageCandidate) -> str:
    return "9x16" if candidate.height >= candidate.width else "16x9"


def matches_orientation(candidate: ImageCandidate, target_format: str) -> bool:
    return orientation_of(candidate) == target_format


def usable_candidates(candidates: list[ImageCandidate]) -> list[ImageCandidate]:
    return [c for c in candidates if meets_resolution_bar(c)]


def pick_best(
    candidates: list[ImageCandidate], target_format: str, already_used: set[str]
) -> ImageCandidate | None:
    """Picks the highest-priority candidate: orientation match first, then
    not-already-used-in-this-project. Callers should pass already-usable
    (resolution-qualified) candidates; this function only breaks ties among
    them.
    """
    if not candidates:
        return None

    def priority(c: ImageCandidate) -> tuple[bool, bool]:
        return (matches_orientation(c, target_format), c.source_id not in already_used)

    return max(candidates, key=priority)
