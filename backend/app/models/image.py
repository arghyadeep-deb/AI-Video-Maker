from typing import Literal, Optional

from pydantic import BaseModel


class ImageCandidate(BaseModel):
    source: Literal["pexels", "pixabay", "genai", "flux"]
    source_id: str
    width: int
    height: int
    # Pexels/Pixabay: a URL to download; genai/flux: None (bytes already in hand).
    url: Optional[str] = None
    # genai/flux only: the generated image is returned in-memory, no hosted URL.
    image_bytes: Optional[bytes] = None
    photographer: Optional[str] = None
    photographer_url: Optional[str] = None
