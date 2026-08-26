import io
import os

from PIL import Image

from app.schemas.job import MediaType
from app.services.file_validation import verify_file_type


def _write_jpeg(path: str) -> None:
    img = Image.new("RGB", (10, 10), color=(1, 2, 3))
    img.save(path, "JPEG")


def _write_text_file_disguised_as_jpeg(path: str) -> None:
    with open(path, "wb") as f:
        f.write(b"this is not an image, just plain text pretending to be one" * 20)


def test_genuine_image_matches_declared_type(tmp_path):
    p = tmp_path / "real.jpg"
    _write_jpeg(str(p))
    valid, detected = verify_file_type(str(p), MediaType.IMAGE)
    assert valid is True
    assert detected == "image/jpeg"


def test_disguised_text_file_fails_image_validation(tmp_path):
    p = tmp_path / "fake.jpg"
    _write_text_file_disguised_as_jpeg(str(p))
    valid, detected = verify_file_type(str(p), MediaType.IMAGE)
    assert valid is False
    assert detected != "image/jpeg"


def test_real_image_declared_as_video_fails(tmp_path):
    p = tmp_path / "real.jpg"
    _write_jpeg(str(p))
    valid, detected = verify_file_type(str(p), MediaType.VIDEO)
    assert valid is False
    assert detected == "image/jpeg"
