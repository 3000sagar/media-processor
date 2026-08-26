from fastapi import Request
from slowapi import Limiter

from app.config import get_settings


def _key_func(request: Request) -> str:
    settings = get_settings()
    api_key = request.headers.get(settings.api_key_header_name)
    # If auth already failed, this still gives slowapi something to key on; the actual
    # 401 for a missing key is raised by the auth dependency, which runs regardless.
    return api_key or "anonymous"


limiter = Limiter(key_func=_key_func)
