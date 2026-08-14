from __future__ import annotations

from gsuid_core.data_store import get_res_path
from gsuid_core.utils.plugins_config.gs_config import StringConfig

from .config_default import CONFIG_DEFAULT

CONFIG_PATH = get_res_path() / "MikuSnap" / "console_config.json"
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

MIKUSNAP_CONFIG = StringConfig("MikuSnap", CONFIG_PATH, CONFIG_DEFAULT)
MIKUSNAP_CONFIG.plugin_name = "MikuSnap"

# GsCore preserves removed keys by default. Prune legacy options so the
# WebConsole only exposes settings that still affect plugin behavior.
legacy_keys = set(MIKUSNAP_CONFIG.config) - set(CONFIG_DEFAULT)
if legacy_keys:
    for key in legacy_keys:
        MIKUSNAP_CONFIG.config.pop(key)
    MIKUSNAP_CONFIG.write_config()
