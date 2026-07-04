"""WebScreenshot - GsCore 网页自动截图插件。"""
from __future__ import annotations

try:
    from gsuid_core.sv import Plugins
except ModuleNotFoundError:
    Plugins = None  # type: ignore[assignment]

if Plugins is not None:
    Plugins(
        name="WebScreenshot",
        disable_force_prefix=True,
        allow_empty_prefix=True,
        alias=["web_screenshot", "网页截图"],
    )

    from . import webscreenshot_config  # noqa: F401
    from . import webscreenshot_capture  # noqa: F401
