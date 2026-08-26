import os

import pytest

from app.utils.ffmpeg_runner import FfmpegError, extract_thumbnail, transcode

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample.mp4")


def test_transcode_produces_valid_output(tmp_path):
    output_path = str(tmp_path / "out.mp4")
    transcode(
        input_path=FIXTURE,
        output_path=output_path,
        resolution="160x120",
        codec="libx264",
        allowed_protocols="file",
        timeout_seconds=30,
    )
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_thumbnail_extraction_produces_valid_image(tmp_path):
    thumb_path = str(tmp_path / "thumb.jpg")
    extract_thumbnail(
        input_path=FIXTURE,
        output_path=thumb_path,
        allowed_protocols="file",
        timeout_seconds=30,
        at_seconds=0.2,  # fixture is only 1s long
    )
    assert os.path.exists(thumb_path)
    from PIL import Image
    img = Image.open(thumb_path)
    img.load()
    assert img.size[0] > 0


def test_nonexistent_input_raises_ffmpeg_error(tmp_path):
    with pytest.raises(FfmpegError):
        transcode(
            input_path="/tmp/does_not_exist_at_all.mp4",
            output_path=str(tmp_path / "out.mp4"),
            resolution="160x120",
            codec="libx264",
            allowed_protocols="file",
            timeout_seconds=10,
        )


def test_protocol_whitelist_blocks_network_input():
    # Proves the SSRF mitigation actually functions at runtime, not just that the flag
    # is present in the command list (test_ffmpeg_injection.py proves the latter).
    with pytest.raises(FfmpegError):
        transcode(
            input_path="http://169.254.169.254/latest/meta-data/",  # classic SSRF target (cloud metadata endpoint)
            output_path="/tmp/should_not_be_created.mp4",
            resolution="160x120",
            codec="libx264",
            allowed_protocols="file",  # http is NOT in the whitelist — ffmpeg must refuse
            timeout_seconds=10,
        )
    assert not os.path.exists("/tmp/should_not_be_created.mp4")
