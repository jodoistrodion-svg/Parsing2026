from __future__ import annotations
from urllib.parse import urlsplit

def _source_base(source_url:str)->str:
    try:
        p=urlsplit((source_url or "").strip())
        if p.scheme and p.netloc:return f"{p.scheme}://{p.netloc}"
    except Exception:pass
    return ""

def _ordered_bases(source_url:str)->list[str]:
    source_base=_source_base(source_url)
    bases=["https://prod-api.lzt.market","https://api.lzt.market","https://api.lolz.live"]
    low=(source_url or "").lower(); is_api=bool(source_base) and any(x in low for x in ("api.","prod-api."))
    if source_base:
        if is_api:bases.insert(0,source_base)
        else:bases.append(source_base)
    out=[];seen=set()
    for b in bases:
        if b and b not in seen:seen.add(b);out.append(b)
    return out

def build_buy_urls(source_url:str,item_id:int)->list[str]:
    bases=_ordered_bases(source_url)
    official=["{id}/confirm-buy","market/{id}/confirm-buy","{id}/fast-buy","market/{id}/fast-buy"]
    legacy=["{id}/buy","market/{id}/buy","items/{id}/confirm-buy","items/{id}/fast-buy","items/{id}/buy","item/{id}/confirm-buy","item/{id}/fast-buy","item/{id}/buy","{id}/purchase","market/{id}/purchase","item/{id}/purchase","items/{id}/purchase"]
    out=[];seen=set()
    for paths in (official,legacy):
        for tpl in paths:
            for base in bases:
                u=f"{base}/{tpl.format(id=item_id)}"
                if u not in seen:seen.add(u);out.append(u)
    return out

def prioritize_buy_urls(all_urls:list[str],preferred_urls:list[str]|None=None)->list[str]:
    preferred=[u for u in (preferred_urls or []) if u in all_urls]
    return preferred+[u for u in all_urls if u not in preferred]
