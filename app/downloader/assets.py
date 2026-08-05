"""Save video thumbnail to disk."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)


def save_thumbnail(
    thumbnail_url: str,
    output_path: Path,
) -> Optional[Path]:
    """Download and save thumbnail as JPEG."""
    if not thumbnail_url:
        return None
    try:
        response = requests.get(thumbnail_url, timeout=20)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        image.save(output_path, format="JPEG", quality=90)
        logger.info("Saved thumbnail: %s", output_path.name)
        return output_path
    except Exception as exc:
        logger.warning("Thumbnail save failed: %s", exc)
        return None
