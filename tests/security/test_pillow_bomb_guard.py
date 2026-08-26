import pytest
from PIL import Image

from app.services.file_validation import apply_pillow_safety_limit


def test_bomb_guard_raises_past_configured_limit(tmp_path, monkeypatch):
    # Set an artificially tiny limit so we don't need to generate a real gigapixel image
    # to prove the guard fires — the mechanism under test is "does Pillow enforce
    # MAX_IMAGE_PIXELS", not "can we construct a multi-GB fixture file".
    apply_pillow_safety_limit(max_pixels=100)  # 100 pixels total, e.g. 10x10

    img = Image.new("RGB", (50, 50))  # 2500 pixels — exceeds the 100-pixel limit
    path = tmp_path / "oversized.png"
    img.save(path)

    # Restore a sane global limit immediately after, so this test doesn't leak state that
    # breaks other tests in the same process (Image.MAX_IMAGE_PIXELS is a module-level global).
    try:
        with pytest.raises(Image.DecompressionBombError):
            opened = Image.open(path)
            opened.load()  # decompression bomb check fires on load, not on open()
    finally:
        apply_pillow_safety_limit(max_pixels=178_956_970)


def test_normal_sized_image_is_unaffected(tmp_path):
    apply_pillow_safety_limit(max_pixels=178_956_970)
    img = Image.new("RGB", (200, 200))
    path = tmp_path / "normal.png"
    img.save(path)

    opened = Image.open(path)
    opened.load()  # should not raise
    assert opened.size == (200, 200)
