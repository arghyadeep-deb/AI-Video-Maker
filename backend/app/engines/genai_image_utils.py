"""Shared helper for extracting generated image bytes from a Gemini
image-model response — used by both the Mode B genai fallback (task-08)
and avatar styling (task-10).
"""
from typing import Optional


def extract_image_bytes(response) -> Optional[bytes]:
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline_data = getattr(part, "inline_data", None)
            if inline_data is not None and inline_data.data:
                return inline_data.data
    return None
