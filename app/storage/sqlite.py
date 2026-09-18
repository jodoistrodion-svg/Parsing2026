from __future__ import annotations

from app.application import *

import aiosqlite

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()


async def db_conn() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_FILE)
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA synchronous=NORMAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def db_close():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def db_execute(query: str, params: tuple = (), commit: bool = False):
    db = await db_conn()
    async with _db_lock:
        cur = await db.execute(query, params)
        if commit:
            await db.commit()
        return cur


async def db_executemany(query: str, params_seq, commit: bool = False):
    db = await db_conn()
    async with _db_lock:
        cur = await db.executemany(query, params_seq)
        if commit:
            await db.commit()
        return cur


async def db_fetchone(query: str, params: tuple = ()):
    db = await db_conn()
    async with _db_lock:
        cur = await db.execute(query, params)
        row = await cur.fetchone()
        await cur.close()
        return row


async def db_fetchall(query: str, params: tuple = ()):
    db = await db_conn()
    async with _db_lock:
        cur = await db.execute(query, params)
        rows = await cur.fetchall()
        await cur.close()
        return rows


async def init_db():
    await db_execute("""
        CREATE TABLE IF NOT EXISTS urls (
            user_id INTEGER,
            url TEXT,
            name TEXT DEFAULT '',
            added_at INTEGER,
            enabled INTEGER DEFAULT 1,
            autobuy INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, url)
        )
    """, commit=True)

    cols = [row[1] for row in await db_fetchall("PRAGMA table_info(urls)")]
    if "enabled" not in cols:
        await db_execute("ALTER TABLE urls ADD COLUMN enabled INTEGER DEFAULT 1", commit=True)
    if "autobuy" not in cols:
        await db_execute("ALTER TABLE urls ADD COLUMN autobuy INTEGER DEFAULT 0", commit=True)
    if "name" not in cols:
        await db_execute("ALTER TABLE urls ADD COLUMN name TEXT DEFAULT ''", commit=True)

    await db_execute("""
        CREATE TABLE IF NOT EXISTS seen (
            user_id INTEGER,
            item_key TEXT,
            seen_at INTEGER,
            PRIMARY KEY(user_id, item_key)
        )
    """, commit=True)

    await db_execute("""
        CREATE TABLE IF NOT EXISTS buy_attempted (
            user_id INTEGER,
            item_key TEXT,
            attempted_at INTEGER,
            PRIMARY KEY(user_id, item_key)
        )
    """, commit=True)

    await db_execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            role TEXT DEFAULT 'unknown',
            allowed INTEGER DEFAULT 0,
            last_error_report INTEGER DEFAULT 0,
            last_request_ts INTEGER DEFAULT 0
        )
    """, commit=True)

    ucols = [row[1] for row in await db_fetchall("PRAGMA table_info(users)")]
    if "allowed" not in ucols:
        await db_execute("ALTER TABLE users ADD COLUMN allowed INTEGER DEFAULT 0", commit=True)
    if "last_request_ts" not in ucols:
        await db_execute("ALTER TABLE users ADD COLUMN last_request_ts INTEGER DEFAULT 0", commit=True)
    if "last_error_report" not in ucols:
        await db_execute("ALTER TABLE users ADD COLUMN last_error_report INTEGER DEFAULT 0", commit=True)

    await db_execute(
        "CREATE INDEX IF NOT EXISTS idx_urls_user_added ON urls(user_id, added_at, url)",
        commit=True,
    )


async def db_ensure_user(user_id: int):
    await db_execute(
        "INSERT OR IGNORE INTO users(user_id, role, allowed, last_error_report, last_request_ts) VALUES (?, ?, ?, ?, ?)",
        (user_id, "unknown", 1 if (ACCESS_OPEN or user_id in OWNER_IDS) else 0, 0, 0),
        commit=True,
    )
    if user_id in OWNER_IDS:
        await db_execute("UPDATE users SET allowed=1 WHERE user_id=?", (user_id,), commit=True)


async def db_is_allowed(user_id: int) -> bool:
    if ACCESS_OPEN or user_id in OWNER_IDS:
        return True
    row = await db_fetchone("SELECT allowed FROM users WHERE user_id=?", (user_id,))
    return bool(row[0]) if row else False


async def db_toggle_allowed(target_user_id: int) -> bool:
    if target_user_id in OWNER_IDS:
        return True
    await db_execute(
        "UPDATE users SET allowed = CASE WHEN COALESCE(allowed,0)=1 THEN 0 ELSE 1 END WHERE user_id=?",
        (target_user_id,),
        commit=True,
    )
    row = await db_fetchone("SELECT allowed FROM users WHERE user_id=?", (target_user_id,))
    return bool(row[0]) if row else False


async def db_list_users(limit: int, offset: int):
    rows = await db_fetchall(
        "SELECT user_id, allowed, role FROM users ORDER BY user_id LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return [(int(r[0]), int(r[1] or 0), str(r[2] or "unknown")) for r in rows]


async def db_count_users() -> int:
    row = await db_fetchone("SELECT COUNT(1) FROM users")
    return int(row[0]) if row and row[0] is not None else 0


async def db_get_last_request_ts(user_id: int) -> int:
    row = await db_fetchone("SELECT last_request_ts FROM users WHERE user_id=?", (user_id,))
    return int(row[0]) if row and row[0] is not None else 0


async def db_set_last_request_ts(user_id: int, ts: int):
    await db_execute("UPDATE users SET last_request_ts=? WHERE user_id=?", (ts, user_id), commit=True)


async def db_get_role(user_id: int) -> str:
    row = await db_fetchone("SELECT role FROM users WHERE user_id=?", (user_id,))
    return row[0] if row else "unknown"


async def db_get_last_report(user_id: int) -> int:
    row = await db_fetchone("SELECT last_error_report FROM users WHERE user_id=?", (user_id,))
    return int(row[0]) if row and row[0] is not None else 0


async def db_set_last_report(user_id: int, ts: int):
    await db_execute("UPDATE users SET last_error_report=? WHERE user_id=?", (ts, user_id), commit=True)


async def db_get_urls(user_id: int):
    rows = await db_fetchall(
        "SELECT url, name, enabled, autobuy FROM urls WHERE user_id=? ORDER BY added_at, url",
        (user_id,),
    )
    return [{"url": url, "name": name or "", "enabled": bool(enabled), "autobuy": bool(autobuy)} for url, name, enabled, autobuy in rows]


async def db_add_url(user_id: int, url: str, name: str):
    await db_execute(
        "INSERT OR IGNORE INTO urls(user_id, url, name, added_at, enabled, autobuy) VALUES (?, ?, ?, ?, 1, 0)",
        (user_id, url, name or "", int(time.time())),
        commit=True,
    )
    await db_execute("UPDATE urls SET name=? WHERE user_id=? AND url=?", (name or "", user_id, url), commit=True)


async def db_set_url_name(user_id: int, url: str, name: str):
    await db_execute("UPDATE urls SET name=? WHERE user_id=? AND url=?", (name or "", user_id, url), commit=True)


async def db_remove_url(user_id: int, url: str):
    await db_execute("DELETE FROM urls WHERE user_id=? AND url=?", (user_id, url), commit=True)


async def db_set_url_enabled(user_id: int, url: str, enabled: bool):
    await db_execute("UPDATE urls SET enabled=? WHERE user_id=? AND url=?", (1 if enabled else 0, user_id, url), commit=True)


async def db_set_url_autobuy(user_id: int, url: str, autobuy: bool):
    await db_execute("UPDATE urls SET autobuy=? WHERE user_id=? AND url=?", (1 if autobuy else 0, user_id, url), commit=True)


def _load_seed_urls() -> list[tuple[str, str]]:
    if not SEED_URLS_JSON:
        return []

    out: list[tuple[str, str]] = []
    try:
        data = json.loads(SEED_URLS_JSON)
    except Exception:
        return out

    if not isinstance(data, list):
        return out

    for i, row in enumerate(data, start=1):
        if isinstance(row, dict):
            raw_url = str(row.get("url") or "").strip()
            raw_name = str(row.get("name") or f"SEED #{i}").strip()
        else:
            raw_url = str(row or "").strip()
            raw_name = f"SEED #{i}"

        if not raw_url:
            continue
        normalized = normalize_url(raw_url)
        ok, _ = validate_market_url(normalized)
        if not ok:
            continue
        out.append((normalized, raw_name))
    return out


async def db_seed_urls_if_empty(user_id: int):
    existing = await db_get_urls(user_id)
    if existing:
        return
    for url, name in _load_seed_urls():
        await db_add_url(user_id, url, name)


async def db_mark_seen_batch(user_id: int, keys: list[str]):
    if not keys:
        return
    now = int(time.time())
    rows = [(user_id, k, now) for k in keys]
    await db_executemany("INSERT OR IGNORE INTO seen(user_id, item_key, seen_at) VALUES (?, ?, ?)", rows, commit=True)


async def db_load_seen(user_id: int):
    rows = await db_fetchall("SELECT item_key FROM seen WHERE user_id=?", (user_id,))
    return {r[0] for r in rows}


async def db_clear_seen(user_id: int):
    await db_execute("DELETE FROM seen WHERE user_id=?", (user_id,), commit=True)


async def db_mark_buy_attempted(user_id: int, key: str):
    await db_execute(
        "INSERT OR IGNORE INTO buy_attempted(user_id, item_key, attempted_at) VALUES (?, ?, ?)",
        (user_id, key, int(time.time())),
        commit=True,
    )


async def db_mark_buy_attempted_batch(user_id: int, keys: list[str]):
    if not keys:
        return
    ts = int(time.time())
    rows = [(user_id, k, ts) for k in keys]
    await db_executemany("INSERT OR IGNORE INTO buy_attempted(user_id, item_key, attempted_at) VALUES (?, ?, ?)", rows, commit=True)


async def db_load_buy_attempted(user_id: int):
    rows = await db_fetchall("SELECT item_key FROM buy_attempted WHERE user_id=?", (user_id,))
    return {r[0] for r in rows}


async def db_clear_buy_attempted(user_id: int):
    await db_execute("DELETE FROM buy_attempted WHERE user_id=?", (user_id,), commit=True)

__all__ = [name for name in globals() if not name.startswith("__")]
