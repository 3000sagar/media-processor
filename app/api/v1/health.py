
from typing import Any

from fastapi import APIRouter, Depends
from redis import Redis

from app.config import Settings, get_settings
from app.errors import service_unavailable
from app.services.redis_service import get_redis_client
from app.services.s3_service import get_s3_client

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
async def liveness() -> dict[str, str]:
    # Deliberately checks nothing external — must always respond fast so orchestrators
    # don't kill a healthy process just because a downstream dependency is slow.
    return {"status": "ok"}


@router.get("/api/v1/ready")
async def readiness(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    checks: dict[str, str] = {}

    try:
        redis_client: Redis[str] = get_redis_client(settings)
        redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    try:
        client = get_s3_client(settings)
        client.head_bucket(Bucket=settings.s3_bucket_raw)
        checks["s3"] = "ok"
    except Exception as exc:
        checks["s3"] = f"error: {exc}"

    if any(v != "ok" for v in checks.values()):
        raise service_unavailable(f"Dependency check failed: {checks}")

    return {"status": "ready", "checks": checks}
