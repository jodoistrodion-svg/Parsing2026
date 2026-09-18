from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

VALID_API_HOSTS = {
    "api.lzt.market",
    "prod-api.lzt.market",
    "api.lolz.live",
}

HOST_ALIASES = {
    "lzt.market": "api.lzt.market",
    "www.lzt.market": "api.lzt.market",
    "api.lolz.guru": "api.lzt.market",
}

PARAM_ALIASES = {
    "genshinlevelmin": "genshin_level_min",
    "genshinlevelmax": "genshin_level_max",
    "brawl_cupmin": "brawl_cup_min",
    "brawl_cupmax": "brawl_cup_max",
    "clash_cupmin": "clash_cup_min",
    "clash_cupmax": "clash_cup_max",
    "clashcupmin": "clash_cup_min",
    "clashcupmax": "clash_cup_max",
    "orderby": "order_by",
}

ORDER_BY_CORRECTIONS = {
    "pdate_to_down_upoad": "pdate_to_down_upload",
    "pdate_to_down_up": "pdate_to_down_upload",
    "pdate_to_downupload": "pdate_to_down_upload",
}


def validate_market_url(url: str) -> tuple[bool, str | None]:
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return False, "❌ Это не похоже на URL."

    hostname = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not hostname:
        return False, "❌ Это не похоже на URL."

    canonical_host = HOST_ALIASES.get(hostname, hostname)
    if canonical_host not in VALID_API_HOSTS:
        return False, "❌ Нужна API-ссылка LZT: prod-api.lzt.market / api.lzt.market / api.lolz.live."

    return True, None


def normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return raw

    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    hostname = (parts.hostname or "").lower()
    canonical_host = HOST_ALIASES.get(hostname, hostname)

    normalized_pairs: list[tuple[str, str]] = []
    has_order_by = False

    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        normalized_key = PARAM_ALIASES.get(key, key)
        normalized_value = value
        if normalized_key == "order_by":
            has_order_by = True
            normalized_value = ORDER_BY_CORRECTIONS.get(
                normalized_value,
                normalized_value,
            )
        normalized_pairs.append((normalized_key, normalized_value))

    if not has_order_by:
        normalized_pairs.append(("order_by", "pdate_to_down_upload"))

    return urlunsplit(
        (
            scheme,
            canonical_host,
            parts.path or "",
            urlencode(normalized_pairs, doseq=True),
            "",
        )
    )


def normalize_market_url(url: str) -> str:
    """Compatibility name for the canonical URL normalizer."""
    return normalize_url(url)
