from app.schemas.job import MediaType
from app.services.s3_service import derive_object_key


def test_traversal_attempt_does_not_escape_prefix():
    key = derive_object_key("owner_1", "job-abc", "../../etc/passwd", MediaType.IMAGE)
    assert key.startswith("raw-uploads/owner_1/job-abc")
    assert ".." not in key
    assert "etc/passwd" not in key


def test_disallowed_extension_falls_back_safely():
    key = derive_object_key("owner_1", "job-abc", "payload.exe", MediaType.IMAGE)
    assert key.endswith((".jpg", ".jpeg", ".png", ".webp"))
    assert "exe" not in key


def test_key_is_scoped_to_owner_and_job_only():
    key = derive_object_key("owner_1", "job-abc", "vacation.jpg", MediaType.IMAGE)
    assert key == "raw-uploads/owner_1/job-abc.jpg"


def test_filename_with_null_byte_and_slashes_is_neutralized():
    from app.schemas.job import JobCreateRequest

    req = JobCreateRequest(
        media_type=MediaType.IMAGE,
        declared_filename="../../../etc/passwd",
        operations=["resize"],
    )
    assert "/" not in req.declared_filename
    assert ".." not in req.declared_filename
