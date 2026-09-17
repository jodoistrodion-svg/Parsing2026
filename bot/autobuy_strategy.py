from __future__ import annotations

from urllib.parse import urlsplit


def _source_base(source_url: str) -> str:
    try:
        parts = urlsplit((source_url or "").strip())
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    except Exception:
        pass
    return ""


def _ordered_bases(source_url: str) -> list[str]:
    source_base = _source_base(source_url)
    bases = [
        "https://prod-api.lzt.market",
        "https://api.lzt.market",
        "https://api.lolz.live",
    ]
    low = (source_url or "").lower()
    is_api = bool(source_base) and any(host in low for host in ("api.", "prod-api."))
    if source_base:
        if is_api:
            bases.insert(0, source_base)
        else:
            bases.append(source_base)

    out: list[str] = []
    seen: set[str] = set()
    for base in bases:
        if base and base not in seen:
            seen.add(base)
            out.append(base)
    return out


def build_buy_urls(source_url: str, item_id: int) -> list[str]:
    bases = _ordered_bases(source_url)
    official = [
        "{id}/confirm-buy",
        "market/{id}/confirm-buy",
        "{id}/fast-buy",
        "market/{id}/fast-buy",
    ]
    legacy = [
        "{id}/buy",
        "market/{id}/buy",
        "items/{id}/confirm-buy",
        "items/{id}/fast-buy",
        "items/{id}/buy",
        "item/{id}/confirm-buy",
        "item/{id}/fast-buy",
        "item/{id}/buy",
        "{id}/purchase",
        "market/{id}/purchase",
        "item/{id}/purchase",
        "items/{id}/purchase",
    ]

    out: list[str] = []
    seen: set[str] = set()
    for paths in (official, legacy):
        for template in paths:
            for base in bases:
                url = f"{base}/{template.format(id=item_id)}"
                if url not in seen:
                    seen.add(url)
                    out.append(url)
    return out


def prioritize_buy_urls(
    all_urls: list[str], preferred_urls: list[str] | None = None
) -> list[str]:
    preferred = [url for url in (preferred_urls or []) if url in all_urls]
    return preferred + [url for url in all_urls if url not in preferred]
