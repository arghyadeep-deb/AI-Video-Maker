"""nano banana (Gemini 2.5 Flash Image) — last-resort Mode B image fallback,
only reached when both stock providers return zero usable candidates.
specs/02-research/04-free-image-generation.md.
"""
from google import genai

from app.engines.genai_image_utils import extract_image_bytes
from app.engines.images.base import StockImageEngine
from app.models.image import ImageCandidate

# Consistent style suffix so generated images across one video don't clash
# visually — specs/04-tasks/task-08-image-sourcing.md.
STYLE_SUFFIX = ", cinematic lighting, photorealistic, consistent visual style"

GENERATED_WIDTH = 1024
GENERATED_HEIGHT = 1024


class GenaiImageUnavailableError(Exception):
    pass


class GenaiFallbackImages(StockImageEngine):
    def __init__(self, api_key: str | None, model: str):
        self._model = model
        self._client = genai.Client(api_key=api_key) if api_key else None

    async def search(
        self, query: str, orientation: str, per_page: int = 1
    ) -> list[ImageCandidate]:
        if self._client is None:
            raise GenaiImageUnavailableError("GEMINI_API_KEY is not configured")

        prompt = f"{query}{STYLE_SUFFIX}"
        try:
            response = self._client.models.generate_content(model=self._model, contents=prompt)
        except Exception as exc:  # noqa: BLE001 - any API failure surfaces honestly
            raise GenaiImageUnavailableError(str(exc)) from exc

        image_bytes = extract_image_bytes(response)
        if image_bytes is None:
            return []

        return [
            ImageCandidate(
                source="genai",
                source_id=f"genai:{abs(hash(prompt))}",
                width=GENERATED_WIDTH,
                height=GENERATED_HEIGHT,
                image_bytes=image_bytes,
            )
        ]
