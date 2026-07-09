"""StockImages engine interface — specs/02-research/05-stock-image-apis.md.

Every image source (Pexels, Pixabay, nano banana generation) sits behind
this one interface so the fallback chain (task-08's own scope) never
depends on a specific provider's response shape.
"""
from abc import ABC, abstractmethod

from app.models.image import ImageCandidate


class StockImageEngine(ABC):
    @abstractmethod
    async def search(
        self, query: str, orientation: str, per_page: int = 5
    ) -> list[ImageCandidate]:
        """Returns up to `per_page` candidates. Never raises for "no
        results" or "no API key configured" — both come back as an empty
        list so the fallback chain (image_service.py) can proceed to the
        next provider without special-casing errors vs. honest misses.
        Real transport failures (timeouts, 5xx) still raise.
        """
