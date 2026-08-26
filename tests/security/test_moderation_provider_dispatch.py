import pytest

from app.config import get_settings
from app.services import moderation_service


def test_none_provider_approves_everything():
    get_settings.cache_clear()
    settings = get_settings()
    settings.moderation_provider = "none"
    result = moderation_service.scan_file(settings, "/tmp/whatever.jpg")
    assert result == moderation_service.ModerationResult.APPROVED


def test_rekognition_provider_not_yet_wired_raises_clearly():
    get_settings.cache_clear()
    settings = get_settings()
    settings.moderation_provider = "aws_rekognition"
    with pytest.raises(NotImplementedError):
        moderation_service.scan_file(settings, "/tmp/whatever.jpg")


def test_hive_provider_not_yet_wired_raises_clearly():
    get_settings.cache_clear()
    settings = get_settings()
    settings.moderation_provider = "hive"
    with pytest.raises(NotImplementedError):
        moderation_service.scan_file(settings, "/tmp/whatever.jpg")


def test_unknown_provider_raises_value_error():
    get_settings.cache_clear()
    settings = get_settings()
    settings.moderation_provider = "some_typo_vendor"
    with pytest.raises(ValueError):
        moderation_service.scan_file(settings, "/tmp/whatever.jpg")
