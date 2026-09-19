from __future__ import annotations

import hashlib
import re
import secrets
from typing import Final

from app.storage.sqlite import (
    db_access_code_stats,
    db_create_access_code,
    db_list_access_codes,
    db_redeem_access_code,
    db_revoke_access_for_user,
)

_CODE_PREFIX: Final[str] = "P26"
_ALPHABET: Final[str] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_RAW_LENGTH: Final[int] = 24


def _canonical(raw: str) -> str:
    value = re.sub(r"[\s-]", "", raw or "").upper()
    if value.startswith(_CODE_PREFIX):
        value = value[len(_CODE_PREFIX):]
    if len(value) != _RAW_LENGTH or any(ch not in _ALPHABET for ch in value):
        raise ValueError("Некорректный код доступа")
    return f"{_CODE_PREFIX}-{value[0:6]}-{value[6:12]}-{value[12:18]}-{value[18:24]}"


def _hash(canonical_code: str) -> str:
    return hashlib.sha256(canonical_code.encode("utf-8")).hexdigest()


def generate_access_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(_RAW_LENGTH))
    return _canonical(raw)


async def issue_access_code(created_by: int) -> str:
    for _ in range(5):
        code = generate_access_code()
        if await db_create_access_code(_hash(code), created_by):
            return code
    raise RuntimeError("Не удалось сгенерировать уникальный код доступа")


async def redeem_access_code(user_id: int, raw_code: str) -> str:
    canonical = _canonical(raw_code)
    return await db_redeem_access_code(user_id, _hash(canonical))


async def access_stats() -> dict[str, int]:
    return await db_access_code_stats()


async def recent_access_codes(limit: int = 10):
    return await db_list_access_codes(limit=max(1, min(limit, 50)))


async def revoke_user_access(user_id: int) -> int:
    return await db_revoke_access_for_user(user_id)
