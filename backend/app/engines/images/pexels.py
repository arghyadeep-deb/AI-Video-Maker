"""Pexels — primary stock image source. specs/02-research/05-stock-image-apis.md."""
import httpx

from app.engines.images.base import StockImageEngine
from app.models.image import ImageCandidate

BASE_URL = "https://api.pexels.com/v1/search"
ORIENTATION_MAP = {"9x16": "portrait", "16x9": "landscape"}


class PexelsUnavailableError(Exception):
    pass


class PexelsImages(StockImageEngine):
    def __init__(self, api_key: str | None, timeout: float = 10.0):
        self._api_key = api_key
        self._timeout = timeout

    async def search(
        self, query: str, orientation: str, per_page: int = 5
    ) -> list[ImageCandidate]:
        if not self._api_key:
            return []  # no key configured -> honest miss, caller falls back

        params = {
            "query": query,
            "orientation": ORIENTATION_MAP.get(orientation, "portrait"),
            "per_page": per_page,
        }
        headers = {"Authorization": self._api_key}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(BASE_URL, params=params, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PexelsUnavailableError(str(exc)) from exc

        data = response.json()
        return [
            ImageCandidate(
                source="pexels",
                source_id=str(photo["id"]),
                url=photo["src"]["original"],
                width=photo["width"],
                height=photo["height"],
                photographer=photo.get("photographer"),
                photographer_url=photo.get("photographer_url"),
            )
            for photo in data.get("photos", [])
        ]
