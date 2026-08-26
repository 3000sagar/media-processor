import os

from app.utils.ffmpeg_runner import FfmpegError, extract_thumbnail

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample.mp4")


def test_thumbnail_seek_past_duration_raises_not_silently_empty(tmp_path):
    """Documents the exact failure mode that caused the original bug: ffmpeg exits 0
    but produces no file when -ss seeks past the clip's actual length. This must raise,
    not silently succeed with a missing/empty file — video_tasks.py depends on this
    raising so it can fall back to a t=0 retry instead of uploading a nonexistent thumbnail.
    """
    thumb_path = str(tmp_path / "thumb.jpg")
    # fixture is 1 second long; seeking to 5s is past the end.
    try:
        extract_thumbnail(FIXTURE, thumb_path, allowed_protocols="file", timeout_seconds=30, at_seconds=5.0)
        assert False, "expected FfmpegError for a seek point past the clip's duration"
    except FfmpegError:
        pass
    assert not os.path.exists(thumb_path) or os.path.getsize(thumb_path) == 0


def test_thumbnail_at_t_zero_always_succeeds_as_fallback(tmp_path):
    thumb_path = str(tmp_path / "thumb.jpg")
    extract_thumbnail(FIXTURE, thumb_path, allowed_protocols="file", timeout_seconds=30, at_seconds=0.0)
    assert os.path.exists(thumb_path)
    assert os.path.getsize(thumb_path) > 0
