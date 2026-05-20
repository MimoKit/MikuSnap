from __future__ import annotations

import asyncio
import ipaddress
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlunparse

import httpx
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover - 让插件能给出更友好的依赖提示
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    async_playwright = None  # type: ignore[assignment]


URL_RE = re.compile(r"https?://[^\s<>'\"，。！？、（）()【】\[\]{}]+", re.IGNORECASE)
VIDEO_HOST_KEYWORDS = (
    "bilibili.com",
    "youtube.com",
    "youtu.be",
    "douyin.com",
    "iesdouyin.com",
    "tiktok.com",
    "kuaishou.com",
    "v.kuaishou.com",
    "ixigua.com",
    "xigua.com",
    "acfun.cn",
    "v.qq.com",
    "youku.com",
    "iqiyi.com",
    "mgtv.com",
    "huya.com",
    "douyu.com",
    "twitch.tv",
)
VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mov",
    ".avi",
    ".flv",
    ".mkv",
    ".webm",
    ".wmv",
    ".mpeg",
    ".mpg",
    ".m3u8",
    ".ts",
}
DIRECT_LINK_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".ico",
    ".heic",
    ".pdf",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".exe",
    ".msi",
    ".apk",
    ".ipa",
    ".dmg",
    ".iso",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".txt",
    ".csv",
    ".json",
    ".xml",
    ".mp3",
    ".wav",
    ".flac",
    ".aac",
    ".ogg",
    ".opus",
    *VIDEO_EXTENSIONS,
}
SKIP_CONTENT_TYPE_PREFIXES = (
    "image/",
    "video/",
    "audio/",
    "application/pdf",
    "application/zip",
    "application/x-rar",
    "application/x-7z",
    "application/octet-stream",
)


def _get_config_value(config: AstrBotConfig | None, key: str, default: Any) -> Any:
    if config is None:
        return default
    try:
        return config.get(key, default)
    except Exception:
        return default


def _normalize_url(raw_url: str) -> str | None:
    url = raw_url.strip().rstrip(".,;:!?，。；：！？、")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.params, parsed.query, ""))


def _url_path_suffix(url: str) -> str:
    path = unquote(urlparse(url).path).lower()
    return Path(path).suffix


def _is_video_url(url: str, extra_hosts: list[str]) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    suffix = _url_path_suffix(url)
    if suffix in VIDEO_EXTENSIONS:
        return True
    keywords = tuple(h.lower() for h in extra_hosts if h.strip()) + VIDEO_HOST_KEYWORDS
    return any(host == key or host.endswith(f".{key}") for key in keywords)


def _is_direct_link_by_extension(url: str) -> bool:
    return _url_path_suffix(url) in DIRECT_LINK_EXTENSIONS


async def _is_public_host(url: str) -> bool:
    """跳过本机、内网、保留地址，避免机器人被消息链接诱导访问内网。"""
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
    except ValueError:
        pass

    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None)
    except Exception:
        return False

    for info in infos:
        ip_text = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


@register(
    "astrbot_plugin_web_screenshot",
    "Copilot",
    "自动识别聊天网页链接，跳过视频/直链后截图整页并发送。",
    "1.0.0",
)
class WebScreenshotPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config
        self.output_dir = Path("data") / "plugins_data" / "astrbot_plugin_web_screenshot" / "screenshots"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Semaphore(int(_get_config_value(config, "max_concurrency", 1)))

    @filter.command("网页截图", alias={"webshot", "网页快照"})
    async def screenshot_command(self, event: AstrMessageEvent, url: str):
        """手动截图网页：/网页截图 https://example.com"""
        normalized_url = _normalize_url(url)
        if not normalized_url:
            yield event.plain_result("请提供有效的 http/https 网页链接。")
            return

        result = await self._handle_url(normalized_url, force=True)
        if result["ok"]:
            yield event.chain_result([Comp.Image.fromFileSystem(result["path"]), Comp.Plain(f"\n{normalized_url}")])
        else:
            yield event.plain_result(result["reason"])
        event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_screenshot(self, event: AstrMessageEvent):
        """自动解析消息里的网页链接并发送整页截图。"""
        if not bool(_get_config_value(self.config, "auto_enable", True)):
            return

        urls = self._extract_urls(event.message_str)
        if not urls:
            return

        max_urls = int(_get_config_value(self.config, "max_urls_per_message", 2))
        handled = False
        for url in urls[:max_urls]:
            result = await self._handle_url(url, force=False)
            if not result["ok"]:
                if bool(_get_config_value(self.config, "debug_skip_log", False)):
                    logger.info(f"[web_screenshot] skip {url}: {result['reason']}")
                continue
            handled = True
            yield event.chain_result([Comp.Image.fromFileSystem(result["path"]), Comp.Plain(f"\n{url}")])

        if handled and bool(_get_config_value(self.config, "stop_event_after_send", False)):
            event.stop_event()

    def _extract_urls(self, text: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for match in URL_RE.finditer(text or ""):
            url = _normalize_url(match.group(0))
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    async def _handle_url(self, url: str, force: bool) -> dict[str, Any]:
        if async_playwright is None:
            return {
                "ok": False,
                "reason": "缺少 playwright 依赖，请在插件环境安装 requirements.txt 后执行：playwright install chromium",
            }

        extra_video_hosts = list(_get_config_value(self.config, "extra_video_hosts", []))
        if not force and _is_video_url(url, extra_video_hosts):
            return {"ok": False, "reason": "视频链接已跳过"}
        if not force and _is_direct_link_by_extension(url):
            return {"ok": False, "reason": "直链已跳过"}

        if bool(_get_config_value(self.config, "block_private_hosts", True)) and not await _is_public_host(url):
            return {"ok": False, "reason": "已跳过本机/内网/保留地址链接"}

        direct_check = await self._check_direct_link_by_content_type(url)
        if not force and direct_check:
            return {"ok": False, "reason": "直链已跳过"}

        async with self._lock:
            try:
                path = await self._screenshot_page(url)
            except PlaywrightTimeoutError:
                return {"ok": False, "reason": "网页加载或截图超时"}
            except Exception as exc:
                logger.error(f"[web_screenshot] screenshot failed: {url} {exc}")
                return {"ok": False, "reason": f"网页截图失败：{exc}"}
        return {"ok": True, "path": str(path)}

    async def _check_direct_link_by_content_type(self, url: str) -> bool:
        timeout = float(_get_config_value(self.config, "head_timeout", 8.0))
        headers = {"User-Agent": self._get_user_agent()}
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=timeout, headers=headers) as client:
                response = await client.head(url)
                if response.is_redirect:
                    return False
                if response.status_code in {405, 403} or not response.headers.get("content-type"):
                    response = await client.get(url, headers={"Range": "bytes=0-0"})
        except Exception:
            return False

        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        content_disposition = response.headers.get("content-disposition", "").lower()
        if "attachment" in content_disposition:
            return True
        return any(content_type.startswith(prefix) for prefix in SKIP_CONTENT_TYPE_PREFIXES)

    async def _screenshot_page(self, url: str) -> Path:
        viewport_width = int(_get_config_value(self.config, "viewport_width", 1365))
        viewport_height = int(_get_config_value(self.config, "viewport_height", 900))
        load_timeout = int(float(_get_config_value(self.config, "load_timeout", 30.0)) * 1000)
        screenshot_timeout = int(float(_get_config_value(self.config, "screenshot_timeout", 30.0)) * 1000)
        user_agent = self._get_user_agent()

        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", urlparse(url).netloc)[:80] or "page"
        output = self.output_dir / f"{int(time.time() * 1000)}_{safe_name}.png"

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            context = await browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                user_agent=user_agent,
                ignore_https_errors=True,
            )
            try:
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="networkidle", timeout=load_timeout)
                except PlaywrightTimeoutError:
                    await page.goto(url, wait_until="domcontentloaded", timeout=load_timeout)
                await page.wait_for_timeout(int(float(_get_config_value(self.config, "settle_delay", 1.5)) * 1000))
                await page.screenshot(path=str(output), full_page=True, timeout=screenshot_timeout)
            finally:
                await context.close()
                await browser.close()

        return output

    def _get_user_agent(self) -> str:
        configured = str(_get_config_value(self.config, "user_agent", "")).strip()
        return configured or self._default_user_agent()

    @staticmethod
    def _default_user_agent() -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

    async def terminate(self):
        """插件卸载/停用时调用。"""
        return None
