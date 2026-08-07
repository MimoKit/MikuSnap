from __future__ import annotations

from gsuid_core.data_store import get_res_path
from gsuid_core.utils.plugins_config.gs_config import StringConfig

from .config_default import CONFIG_DEFAULT

CONFIG_PATH = get_res_path() / "MikuSnap" / "console_config.json"
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

MIKUSNAP_CONFIG = StringConfig("MikuSnap", CONFIG_PATH, CONFIG_DEFAULT)
MIKUSNAP_CONFIG.plugin_name = "MikuSnap"
