from enum import StrEnum

from app.config import Settings


class ModerationResult(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    MANUAL_REVIEW = "manual_review"


def scan_file(settings: Settings, local_path: str) -> ModerationResult:
    """Vendor-agnostic moderation gate. Every processed file must pass through this
    before being promoted to the public-facing processed bucket / CDN path.

    settings.moderation_provider == "none" is only valid for internal/non-UGC deployments
    (e.g. a demo/academic build with no real end users). Flipping a real production
    deployment on with "none" here is a compliance gap, not a neutral default — this is
    exactly the kind of decision that belongs in DECISIONS_NEEDED.md, not silently shipped.
    """
    if settings.moderation_provider == "none":
        return ModerationResult.APPROVED

    if settings.moderation_provider == "aws_rekognition":
        return _scan_with_rekognition(settings, local_path)

    if settings.moderation_provider == "hive":
        return _scan_with_hive(settings, local_path)

    raise ValueError(f"Unknown moderation_provider: {settings.moderation_provider}")


def _scan_with_rekognition(settings: Settings, local_path: str) -> ModerationResult:
    # Vendor integration intentionally not implemented here — requires an AWS account,
    # IAM permissions, and a threshold-tuning decision that is out of scope for this
    # sandbox build. Wire this up once DECISIONS_NEEDED.md item #2 is answered.
    raise NotImplementedError("AWS Rekognition moderation integration not yet configured")


def _scan_with_hive(settings: Settings, local_path: str) -> ModerationResult:
    raise NotImplementedError("Hive moderation integration not yet configured")
