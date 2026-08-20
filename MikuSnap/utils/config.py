from __future__ import annotations

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
