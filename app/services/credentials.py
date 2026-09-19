from __future__ import annotations

import asyncio
import time

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import CREDENTIAL_ENCRYPTION_KEY
from app.storage.sqlite import db_delete_lzt_credential, db_get_lzt_credential, db_upsert_lzt_credential


_lock = asyncio.Lock()
_token_cache: dict[int, str] = {}


def _fernet() -> Fernet:
    if not CREDENTIAL_ENCRYPTION_KEY:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(CREDENTIAL_ENCRYPTION_KEY.encode("ascii"))
    except Exception as exc:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key") from exc


def _encrypt(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def _decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError("Stored LZT credential cannot be decrypted") from exc


async def get_lzt_token(user_id: int) -> str | None:
    cached = _token_cache.get(int(user_id))
    if cached:
        return cached
    async with _lock:
        cached = _token_cache.get(int(user_id))
        if cached:
            return cached
        row = await db_get_lzt_credential(int(user_id))
        if not row or row["status"] != "active":
            return None
        token = _decrypt(row["ciphertext"])
        _token_cache[int(user_id)] = token
        return token


async def save_lzt_token(user_id: int, token: str, *, account_label: str = "", verified_at: int | None = None) -> None:
    token = (token or "").strip()
    if not token or len(token) > 4096:
        raise ValueError("Invalid LZT token")
    ciphertext = _encrypt(token)
    now = int(time.time())
    await db_upsert_lzt_credential(
        int(user_id),
        ciphertext,
        now,
        verified_at or now,
        account_label[:128],
    )
    async with _lock:
        _token_cache[int(user_id)] = token


async def delete_lzt_token(user_id: int) -> None:
    await db_delete_lzt_credential(int(user_id))
    async with _lock:
        _token_cache.pop(int(user_id), None)


async def has_lzt_token(user_id: int) -> bool:
    row = await db_get_lzt_credential(int(user_id))
    return bool(row and row["status"] == "active")


async def lzt_credential_status(user_id: int) -> dict[str, object]:
    row = await db_get_lzt_credential(int(user_id))
    if not row:
        return {"connected": False, "status": "missing", "verified_at": None, "account_label": ""}
    return {
        "connected": row["status"] == "active",
        "status": row["status"],
        "verified_at": row["last_verified_at"],
        "account_label": row["account_label"] or "",
    }
