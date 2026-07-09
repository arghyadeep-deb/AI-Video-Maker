"""Pixabay — secondary stock image source. specs/02-research/05-stock-image-apis.md."""
import httpx

from app.engines.images.base import StockImageEngine
from app.models.image import ImageCandidate

BASE_URL = "https://pixabay.com/api/"
ORIENTATION_MAP = {"9x16": "vertical", "16x9": "horizontal"}


class PixabayUnavailableError(Exception):
    pass


class PixabayImages(StockImageEngine):
    def __init__(self, api_key: str | None, timeout: float = 10.0):
        self._api_key = api_key
        self._timeout = timeout

    async def search(
        self, query: str, orientation: str, per_page: int = 5
    ) -> list[ImageCandidate]:
        if not self._api_key:
            return []

        params = {
            "key": self._api_key,
            "q": query,
            "image_type": "photo",
            "orientation": ORIENTATION_MAP.get(orientation, "vertical"),
            "per_page": max(per_page, 3),  # Pixabay's API minimum is 3
            "safesearch": "true",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(BASE_URL, params=params)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PixabayUnavailableError(str(exc)) from exc

        data = response.json()
        return [
            ImageCandidate(
                source="pixabay",
                source_id=str(hit["id"]),
                url=hit["largeImageURL"],
                width=hit["imageWidth"],
                height=hit["imageHeight"],
                photographer=hit.get("user"),
                photographer_url=(
                    f"https://pixabay.com/users/{hit['user']}-{hit['user_id']}/"
                    if hit.get("user") and hit.get("user_id")
                    else None
                ),
            )
            for hit in data.get("hits", [])[:per_page]
        ]
