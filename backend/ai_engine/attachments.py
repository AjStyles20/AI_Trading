"""Validation for images attached to AI chat messages.

Images arrive as base64 data URLs from the chat. Each one must be a real PNG,
JPEG, WebP or GIF (the declared type must match the file's leading bytes) and
stay within the size limits before it is forwarded to the AI provider. Images
are never stored; only a short "[n image(s) attached]" note is saved.
"""
from __future__ import annotations

import base64
import binascii
import re

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024

_DATA_URL = re.compile(r"^data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/]+={0,2})$")


def _matches_type(kind: str, data: bytes) -> bool:
    if kind == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if kind == "jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if kind == "gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if kind == "webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def validate_image_data_urls(images: list[str] | None) -> list[str]:
    """Return the validated data URLs, or raise ValueError with a user-facing reason."""
    images = images or []
    if len(images) > MAX_IMAGES:
        raise ValueError(f"Attach at most {MAX_IMAGES} images per message.")
    total = 0
    for index, url in enumerate(images, start=1):
        match = _DATA_URL.match(url if isinstance(url, str) else "")
        if not match:
            raise ValueError(f"Attachment {index} is not a supported image (PNG, JPEG, WebP or GIF).")
        try:
            data = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError):
            raise ValueError(f"Attachment {index} is not valid image data.") from None
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError(f"Attachment {index} is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
        if not _matches_type(match.group(1), data):
            raise ValueError(f"Attachment {index} does not contain the image type it claims to be.")
        total += len(data)
    if total > MAX_TOTAL_BYTES:
        raise ValueError(f"Attachments are larger than {MAX_TOTAL_BYTES // (1024 * 1024)} MB in total.")
    return list(images)


def attachment_note(count: int) -> str:
    return f"[{count} image{'s' if count != 1 else ''} attached]" if count else ""
