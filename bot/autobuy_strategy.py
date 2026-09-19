from __future__ import annotations

from urllib.parse import urlsplit


OFFICIAL_MARKET_API_BASES = (
    "https://api.lzt.market",
    "https://prod-api.lzt.market",
)


def _source_base(source_url: str) -> str:
    try:
        parts = urlsplit((source_url or "").strip())
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    hostname = (parts.hostname or "").lower()
    if hostname not in {"api.lzt.market", "prod-api.lzt.market"}:
        return ""
    return f"https://{hostname}"


def _ordered_bases(source_url: str) -> list[str]:
    source_base = _source_base(source_url)
    bases = [source_base] if source_base else []
    bases.extend(base for base in OFFICIAL_MARKET_API_BASES if base not in bases)
    return bases


def build_buy_urls(source_url: str, item_id: int) -> list[str]:
    """
    Return only documented LZT Market purchase endpoints.

    The previous implementation sprayed a matrix of undocumented/legacy paths
    across several hosts. That made live autobuy correctness depend on probing
    endpoints that are not part of the current Market API contract and could
    issue concurrent duplicate purchase requests. The current API documents
    Fast Buy as POST /{item_id}/fast-buy.
    """
    item_id = int(item_id)
    return [f"{base}/{item_id}/fast-buy" for base in _ordered_bases(source_url)]


def prioritize_buy_urls(all_urls: list[str], preferred_urls: list[str] | None = None) -> list[str]:
    preferred = [url for url in (preferred_urls or ()) if url in all_urls]
    return preferred + [url for url in all_urls if url not in preferred]
