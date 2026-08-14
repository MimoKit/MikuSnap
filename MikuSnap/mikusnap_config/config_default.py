from __future__ import annotations

from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    "dark_mode": GsBoolConfig(
        "深色模式",
        "开启后向网页声明深色偏好，并适配常见的网站主题标记。",
        True,
    ),
}
