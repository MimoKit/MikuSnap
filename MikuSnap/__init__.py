"""MikuSnap - GsCore 网页自动截图插件。"""
from __future__ import annotations

try:
    from gsuid_core.sv import Plugins
except ModuleNotFoundError:
    Plugins = None  # type: ignore[assignment]

if Plugins is not None:
    Plugins(
        name="MikuSnap",
        disable_force_prefix=True,
        allow_empty_prefix=True,
        alias=["miku_snap", "网页截图"],
    )

    from . import mikusnap_config  # noqa: F401
    from . import mikusnap_capture  # noqa: F401
    from . import mikusnap_github  # noqa: F401
    from . import mikusnap_help  # noqa: F401
    from . import mikusnap_status  # noqa: F401
