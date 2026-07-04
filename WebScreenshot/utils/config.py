from __future__ import annotations

from collections.abc import Iterable
from typing import Any

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "auto_enable": True,
    "max_urls_per_message": 2,
    "max_concurrency": 1,
    "send_skip_reason": True,
    "skip_reason_template": "网页截图已跳过：{reason}\n链接：{url}",
    "forward_enable": True,
    "ai_name": "解析",
    "forward_node_name": "解析",
    "forward_title_template": "{ai_name} | 网页 {title}",
    "first_node_template": "{ai_name} | 网页\n{title}",
    "split_long_page": True,
    "segment_height": 900,
    "segment_overlap": 80,
    "max_segments": 8,
    "viewport_width": 1365,
    "viewport_height": 900,
    "load_timeout": 30.0,
    "screenshot_timeout": 30.0,
    "head_timeout": 8.0,
    "settle_delay": 1.5,
    "block_private_hosts": True,
    "extra_video_hosts": [],
    "user_agent": "",
    "debug_skip_log": True,
    "debug_success_log": True,
    "debug_detail_log": False,
}


def get_config_value(key: str, default: Any | None = None) -> Any:
    fallback = DEFAULTS[key] if key in DEFAULTS else default
    try:
        from ..webscreenshot_config import WEBSHOT_CONFIG
    except (ImportError, ModuleNotFoundError):
        return fallback
    try:
        return WEBSHOT_CONFIG.get_config(key).data
    except (AttributeError, KeyError, TypeError):
        return fallback


def cfg_bool(key: str, default: bool = False) -> bool:
    return bool(get_config_value(key, default))


def cfg_str(key: str, default: str = "") -> str:
    value = get_config_value(key, default)
    return str(value if value is not None else default)


def cfg_int(key: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    value = get_config_value(key, default)
    try:
        result = int(float(value))
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def cfg_float(key: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    value = get_config_value(key, default)
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def cfg_list_str(key: str) -> list[str]:
    value = get_config_value(key, [])
    if isinstance(value, str):
        items: Iterable[object] = [value]
    elif isinstance(value, Iterable):
        items = value
    else:
        items = []
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result
