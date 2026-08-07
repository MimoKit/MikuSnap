from __future__ import annotations

from gsuid_core.data_store import get_res_path

MAIN_PATH = get_res_path() / "MikuSnap"
SCREENSHOT_PATH = MAIN_PATH / "screenshots"
CACHE_PATH = MAIN_PATH / "cache"

for path in (MAIN_PATH, SCREENSHOT_PATH, CACHE_PATH):
    path.mkdir(parents=True, exist_ok=True)
