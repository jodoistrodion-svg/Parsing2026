DRY_RUN = settings.dry_run
AUTOBUY_MODE = settings.autobuy_mode
SEED_URLS_JSON = settings.seed_urls_json
FAST_AUTOBUY_TIMEOUT = settings.fast_autobuy_timeout


def validate_runtime_config() -> None:
    errors: list[str] = []
    if not API_TOKEN:
        errors.append("API_TOKEN is missing (accepted aliases: TELEGRAM_BOT_TOKEN, BOT_TOKEN)")
    if not ACCESS_OPEN and not OWNER_IDS:
        errors.append("OWNER_ID/OWNER_IDS is required when ACCESS_MODE=closed (legacy alias: ADMIN_TELEGRAM_ID)")
    if ACCESS_MODE not in {"closed", "open", "all", "public", "0"}:
        errors.append(f"ACCESS_MODE has unsupported value: {ACCESS_MODE!r}")
    if LOG_FORMAT not in {"plain", "json"}:
        errors.append("LOG_FORMAT must be 'plain' or 'json'")
    if AUTOBUY_MODE not in {"live", "dry-run"}:
        errors.append("AUTOBUY_MODE must be 'live' or 'dry-run'")
    if LZT_BASE_URL not in {
        "https://api.lzt.market",
    }:
        errors.append("LZT_BASE_URL must point to an allowed LZT API host")
    if errors:
        raise RuntimeError("; ".join(errors))


def describe_runtime_config() -> dict[str, object]:
    return settings.redacted()


__all__ = [
    name
    for name in globals()
    if name.isupper() or name in {"Settings", "settings", "load_settings", "validate_runtime_config", "describe_runtime_config"}
]