import magic

from app.schemas.job import MediaType

_ALLOWED_MIME_BY_TYPE: dict[MediaType, set[str]] = {
    MediaType.IMAGE: {"image/jpeg", "image/png", "image/webp"},
    MediaType.VIDEO: {"video/mp4", "video/quicktime", "video/x-matroska"},
}


def detect_mime_type(filepath: str) -> str:
    return magic.from_file(filepath, mime=True)


def verify_file_type(filepath: str, declared_type: MediaType) -> tuple[bool, str]:
    """Verifies the file's REAL content (magic bytes) matches what the client declared.

    This is the fix for the "client says image, actually uploads whatever" vulnerability —
    the declared media_type in the API request is a hint, never trusted for processing
    decisions until this check passes.
    """
    detected = detect_mime_type(filepath)
    allowed = _ALLOWED_MIME_BY_TYPE.get(declared_type, set())
    return detected in allowed, detected


def apply_pillow_safety_limit(max_pixels: int) -> None:
    """Must be called once at worker startup, before any Image.open() call.

    Pillow raises Image.DecompressionBombError once MAX_IMAGE_PIXELS is exceeded,
    which callers must catch explicitly — this stops a crafted small file from
    expanding into a multi-gigapixel image and OOM-killing the worker.
    """
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = max_pixels
