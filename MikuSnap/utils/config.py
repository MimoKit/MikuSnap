from __future__ import annotations

from urllib.parse import urlparse

from ..mikusnap_config import MIKUSNAP_CONFIG


def _config_data(key: str, default: object) -> object:
    if key not in MIKUSNAP_CONFIG.config:
        return default
    return MIKUSNAP_CONFIG.get_config(key).data


def dark_mode_enabled() -> bool:
    return bool(MIKUSNAP_CONFIG.get_config("dark_mode").data)


def cfg_bool(key: str, default: bool = True) -> bool:
    value = _config_data(key, default)
    return bool(value) if isinstance(value, bool) else default


def cfg_str(key: str, default: str = "") -> str:
    value = _config_data(key, default)
    return value.strip() if isinstance(value, str) else default


def cfg_float(key: str, default: float, min_value: float, max_value: float) -> float:
    value = _config_data(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        number = default
    else:
        number = float(value)
    return min(max(number, min_value), max_value)


def cfg_list_str(key: str) -> list[str]:
    value = _config_data(key, [])
    if isinstance(value, str):
        items: list[object] = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def normalize_exit_proxy(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.netloc:
        return ""
    return text


def screenshot_http_proxy() -> str:
    return normalize_exit_proxy(cfg_str("screenshot_http_proxy", ""))
