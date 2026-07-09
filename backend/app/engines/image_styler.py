"""ImageStyler — selfie + persona -> styled portrait (nano banana image edit).
specs/02-research/04-free-image-generation.md, specs/03-design/04-mode-a-pipeline.md.
"""
from google import genai
from google.genai import types

from app.engines.genai_image_utils import extract_image_bytes

# Fixed suffix pinning identity - specs/03-design/04-mode-a-pipeline.md's
# exact prompt template.
IDENTITY_SUFFIX = (
    ", same person, preserve facial identity, do not beautify or change age or gender, "
    "front-facing, neutral-to-mild expression, shoulders-up portrait, photorealistic, 1024x1024"
)


class ImageStylerUnavailableError(Exception):
    pass


class ImageStyler:
    def __init__(self, api_key: str | None, model: str):
        self._model = model
        self._client = genai.Client(api_key=api_key) if api_key else None

    def style(self, selfie_bytes: bytes, selfie_mime_type: str, persona_description: str) -> bytes:
        if self._client is None:
            raise ImageStylerUnavailableError("GEMINI_API_KEY is not configured")

        prompt = f"Restyle this person as: {persona_description}{IDENTITY_SUFFIX}"
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=selfie_bytes, mime_type=selfie_mime_type),
                    prompt,
                ],
            )
        except Exception as exc:  # noqa: BLE001 - any API failure surfaces honestly
            raise ImageStylerUnavailableError(str(exc)) from exc

        image_bytes = extract_image_bytes(response)
        if image_bytes is None:
            raise ImageStylerUnavailableError("No image returned by the styling model")
        return image_bytes
