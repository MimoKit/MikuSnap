from __future__ import annotations

import re
import time

import httpx
from gsuid_core.logger import logger

from .config import cfg_str
from .proxy_format import parse_proxy_pool_text

_CACHE_AT = 0.0
_CACHE_SERVER = ""
CACHE_TTL = 20.0
SECRET_RE = re.compile(
    r"(apikey|pwd|password|token|key)=([^&\s]+)",
    re.IGNORECASE,
)


def _redact_api(url: str) -> str:
    return SECRET_RE.sub(r"\1=***", url)


def _scheme() -> str:
    text = cfg_str("proxy_pool_scheme", "http").lower()
    if text in {"http", "https", "socks5", "socks5h"}:
        return text
    return "http"


async def fetch_proxy_pool_server() -> str:
    global _CACHE_AT, _CACHE_SERVER
    api = cfg_str("proxy_pool_api", "")
    if not api:
        return ""

    now = time.time()
    if _CACHE_SERVER and now - _CACHE_AT < CACHE_TTL:
        return _CACHE_SERVER

    logger.info(f"[MikuSnap] 提取代理池 IP：url={_redact_api(api)}")
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(api)
    except (httpx.HTTPError, OSError) as exc:
        logger.info(f"[MikuSnap] 代理池提取失败：error={exc}")
        return ""

    if response.status_code >= 400:
        logger.info(f"[MikuSnap] 代理池提取失败：status={response.status_code}")
        return ""

    server = parse_proxy_pool_text(response.text, _scheme())
    if not server:
        logger.info("[MikuSnap] 代理池返回无法解析为 ip:port")
        return ""

    hostport = server.rsplit("@", 1)[-1].removeprefix("http://").removeprefix("https://").removeprefix("socks5://").removeprefix("socks5h://")
    logger.info(f"[MikuSnap] 代理池已提取：proxy={hostport}")
    _CACHE_AT = now
    _CACHE_SERVER = server
    return server
