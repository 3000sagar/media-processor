from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.errors import unauthorized


def _parse_key_map(raw: str) -> dict[str, str]:
    """Parses 'key1:owner1,key2:owner2' into {key: owner_id}.

    MVP-only storage mechanism. Production replacement (DB-backed key table with
    rotation/revocation) is a [HUMAN DECISION REQUIRED] item — see DECISIONS_NEEDED.md.
    """
    mapping: dict[str, str] = {}
    if not raw:
        return mapping
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        key, owner = pair.split(":", 1)
        mapping[key.strip()] = owner.strip()
    return mapping


async def get_owner_id(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    """FastAPI dependency: validates the API key header and returns the caller's owner_id.

    Raise unauthorized() rather than returning None/"" on failure — callers must not be
    able to accidentally treat "no key" as "public owner" through a falsy-value bug.
    """
    header_name = settings.api_key_header_name
    api_key = request.headers.get(header_name)
    if not api_key:
        raise unauthorized(f"Missing '{header_name}' header")

    key_map = _parse_key_map(settings.valid_api_keys)
    owner_id = key_map.get(api_key)
    if owner_id is None:
        raise unauthorized("Invalid API key")

    return owner_id
