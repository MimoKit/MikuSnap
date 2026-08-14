from __future__ import annotations

from ..mikusnap_config import MIKUSNAP_CONFIG


def dark_mode_enabled() -> bool:
    return bool(MIKUSNAP_CONFIG.get_config("dark_mode").data)
