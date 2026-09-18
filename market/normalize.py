from __future__ import annotations
from urllib.parse import parse_qsl,urlencode,urlsplit,urlunsplit
_ALIASES={"genshinlevelmin":"genshin_level_min","genshinlevelmax":"genshin_level_max","brawl_cupmin":"brawl_cup_min","brawl_cupmax":"brawl_cup_max","clash_cupmin":"clash_cup_min","clash_cupmax":"clash_cup_max","orderby":"order_by"}
def normalize_market_url(url: str) -> str:
    """Canonical public normalizer; kept as the legacy compatibility name."""
    return normalize_url(url)



VALID_API_HOSTS = {"api.lzt.market", "prod-api.lzt.market", "api.lolz.live"}


def validate_market_url(url: str):
    try:
        parts = urlsplit((url or "").strip())
    except Exception:
        return False, "❌ Это не похоже на URL."
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False, "❌ Это не похоже на URL."
    hostname = (parts.hostname or "").lower()
    if hostname not in VALID_API_HOSTS:
        return False, "❌ Нужна API-ссылка LZT: prod-api.lzt.market / api.lzt.market / api.lolz.live."
    return True, None


def normalize_url(url: str) -> str:
    if not url:
        return url
    s = (url or "").strip().replace(" ", "").replace("\t", "").replace("\n", "")
    parts = urlsplit(s)
    scheme = parts.scheme or "https"
    netloc = (parts.hostname or "").lower()
    path = parts.path or ""
    query = parts.query or ""
    alias_map = {"lzt.market": "api.lzt.market", "www.lzt.market": "api.lzt.market", "api.lolz.guru": "api.lzt.market"}
    netloc = alias_map.get(netloc, netloc)
    query = query.replace("genshinlevelmin", "genshin_level_min").replace("genshinlevel_min", "genshin_level_min").replace("genshin_levelmin", "genshin_level_min")
    query = query.replace("brawl_cupmin", "brawl_cup_min").replace("clash_cupmin", "clash_cup_min").replace("clashcupmin", "clash_cup_min").replace("clashcupmax", "clash_cup_max").replace("clash_cupmax", "clash_cup_max").replace("orderby", "order_by")
    query = query.replace("order_by=pdate_to_down_upoad", "order_by=pdate_to_down_upload").replace("order_by=pdate_to_down_up", "order_by=pdate_to_down_upload").replace("order_by=pdate_to_downupload", "order_by=pdate_to_down_upload")
    try:
        query_pairs = parse_qsl(query, keep_blank_values=True)
        qmap = {k: v for k, v in query_pairs}
        if "order_by" not in qmap or not str(qmap.get("order_by", "")).strip():
            query_pairs = [(k, v) for k, v in query_pairs if k != "order_by"]
            query_pairs.append(("order_by", "pdate_to_down_upload"))
            query = urlencode(query_pairs)
    except Exception:
        pass
    return urlunsplit((scheme, netloc, path, query, ""))
