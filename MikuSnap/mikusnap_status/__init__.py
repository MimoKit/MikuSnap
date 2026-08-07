from __future__ import annotations

from PIL import Image

from gsuid_core.status.plugin_status import register_status

from ..utils.resource.RESOURCE_PATH import SCREENSHOT_PATH
from ..mikusnap_help.get_help import ICON


async def get_screenshot_count() -> int:
    """截图缓存文件总数"""
    if not SCREENSHOT_PATH.exists():
        return 0
    return sum(1 for p in SCREENSHOT_PATH.rglob("*.png") if p.is_file())


async def get_cache_size() -> str:
    """截图缓存总大小"""
    if not SCREENSHOT_PATH.exists():
        return "0MB"
    total = sum(p.stat().st_size for p in SCREENSHOT_PATH.rglob("*") if p.is_file())
    return f"{total / 1024 / 1024:.1f}MB"


register_status(
    Image.open(ICON),
    "MikuSnap",
    {
        "截图文件": get_screenshot_count,
        "缓存大小": get_cache_size,
    },
)
