from __future__ import annotations

import asyncio
import ipaddress
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlunparse

import httpx
from PIL import Image
from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment

from .config import cfg_list_str, dark_mode_enabled, screenshot_http_proxy
from .github_proxy import github_http_proxy, is_github_fetch_url, resolve_github_url
from .image_quality import is_blank_image
from .ip_guard import (
    IpCheckPageError,
    build_ip_leak_scold,
    detect_ip_check_page,
    detect_ip_check_url,
    match_block_hosts,
)
from .proxy_pool import fetch_proxy_pool_server
from .resource.RESOURCE_PATH import SCREENSHOT_PATH

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    async_playwright = None  # type: ignore[assignment]

URL_RE = re.compile(r"https?://[^\s<>'\"，。！？、（）()【】\[\]{}]+", re.IGNORECASE)
MANUAL_COMMANDS = ("网页截图", "webshot", "网页快照")
GITHUB_COMMANDS = ("仓库卡片", "github卡片")
VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 900
LOAD_TIMEOUT_MS = 30_000
SCREENSHOT_TIMEOUT_MS = 30_000
HEAD_TIMEOUT_SECONDS = 8.0
SETTLE_DELAY_MS = 1_500
MAX_SEGMENTS = 8
SEGMENT_HEIGHT = 900
SEGMENT_OVERLAP = 80
MAX_CONCURRENCY = 1
AI_NAME = "解析"
SKIP_REASON_TEMPLATE = "网页截图已跳过：{reason}\n链接：{url}"

DARK_MODE_INIT_SCRIPT = """
() => {
    const keys = ['theme', 'color-theme', 'colorTheme', 'color-mode', 'colorMode'];
    for (const key of keys) {
        try {
            localStorage.setItem(key, 'dark');
        } catch (_) {
            // Some origins disable localStorage. Media emulation still applies.
        }
    }
}
"""

DARK_MODE_APPLY_SCRIPT = """
() => {
    const root = document.documentElement;
    root.style.colorScheme = 'dark';
    root.classList.add('dark', 'dark-mode');
    root.setAttribute('data-theme', 'dark');
    root.setAttribute('data-color-mode', 'dark');
}
"""

LAZY_LOAD_SCRIPT = """
async () => {
    const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const step = Math.max(Math.floor(window.innerHeight * 0.8), 400);
    for (let round = 0; round < 3; round += 1) {
        const height = Math.min(
            Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight || 0),
            window.innerHeight * 12
        );
        for (let y = 0; y < height; y += step) {
            window.scrollTo(0, y);
            await delay(80);
        }
        await delay(200);
    }
    window.scrollTo(0, 0);
    await delay(300);
}
"""

WEBRTC_BLOCK_SCRIPT = """
() => {
    try {
        Object.defineProperty(window, 'RTCPeerConnection', { configurable: false, writable: false, value: undefined });
        Object.defineProperty(window, 'webkitRTCPeerConnection', { configurable: false, writable: false, value: undefined });
        Object.defineProperty(window, 'mozRTCPeerConnection', { configurable: false, writable: false, value: undefined });
    } catch (_) {
        window.RTCPeerConnection = undefined;
        window.webkitRTCPeerConnection = undefined;
    }
}
"""

PAGE_SAMPLE_SCRIPT = """
() => ({
    title: document.title || '',
    text: document.body ? String(document.body.innerText || '').slice(0, 4000) : ''
})
"""

VIDEO_HOST_KEYWORDS = (
    "bilibili.com",
    "b23.tv",
    "b23.wtf",
    "bili2233.cn",
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


class BlankScreenshotError(RuntimeError):
    pass


def normalize_url(raw_url: str) -> str | None:
    url = raw_url.strip().rstrip(".,;:!?，。；：！？、")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.params, parsed.query, ""))


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in URL_RE.finditer(text or ""):
        url = normalize_url(match.group(0))
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def looks_like_manual_command(text: str) -> bool:
    stripped = text.strip().lower()
    if any(stripped.startswith(command.lower()) for command in MANUAL_COMMANDS):
        return True
    if stripped.startswith("github ") or stripped.startswith("github\t"):
        return True
    return any(stripped.startswith(command.lower()) for command in GITHUB_COMMANDS)


def url_path_suffix(url: str) -> str:
    path = unquote(urlparse(url).path).lower()
    return Path(path).suffix


def _is_video_url(url: str, extra_hosts: list[str]) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    suffix = url_path_suffix(url)
    if suffix in VIDEO_EXTENSIONS:
        return True
    keywords = tuple(h.lower() for h in extra_hosts if h.strip()) + VIDEO_HOST_KEYWORDS
    return any(host == key or host.endswith(f".{key}") for key in keywords)


def _is_direct_link_by_extension(url: str) -> bool:
    return url_path_suffix(url) in DIRECT_LINK_EXTENSIONS


def _is_blocked_ip(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text)
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_reserved,
            ip.is_multicast,
            ip.is_unspecified,
        )
    )


async def _is_public_host(url: str) -> bool:
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        return not _is_blocked_ip(host)
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
            if _is_blocked_ip(ip_text):
                return False
        except ValueError:
            return False
    return True


def redact_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return "[无效链接]"

    host = parsed.hostname or ""
    if not host:
        return "[无效链接]"
    if len(host) > 80:
        host = f"{host[:40]}...{host[-30:]}"

    try:
        port_value = parsed.port
    except ValueError:
        port_value = None
    port = f":{port_value}" if port_value else ""
    path = parsed.path or "/"
    if len(path) > 80:
        path = f"{path[:45]}...{path[-25:]}"

    return urlunparse((parsed.scheme, f"{host}{port}", path, "", "", ""))


def redact_text(text: str, limit: int = 160) -> str:
    text = re.sub(
        r"(token|access_token|refresh_token|key|secret|password|passwd|pwd|cookie)=([^&\s]+)",
        r"\1=***",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"https?://[^\s<>'\"，。！？、（）()【】\[\]{}]+", lambda m: redact_url(m.group(0)), text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("..." if len(text) > limit else "")


class ScreenshotService:
    def __init__(self) -> None:
        self.output_dir = SCREENSHOT_PATH
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Semaphore(MAX_CONCURRENCY)

    async def handle_url(self, url: str, force: bool) -> dict[str, Any]:
        if async_playwright is None:
            return self._skip_result(
                "缺少 playwright 依赖，无法截图",
                category="dependency_missing",
                detail="请安装依赖后执行：playwright install chromium",
            )

        ip_hit = detect_ip_check_url(url)
        if ip_hit is not None:
            return self._skip_result(
                "检测到查 IP 网站，已拦截以免泄漏服务器地址",
                category="ip_check",
                detail=ip_hit.detail,
            )
        blocked = match_block_hosts(url, cfg_list_str("block_hosts"))
        if blocked:
            return self._skip_result(
                "该网站已在屏蔽列表中",
                category="block_host",
                detail=blocked,
            )

        if not force and _is_video_url(url, []):
            return self._skip_result(
                "视频链接已跳过",
                category="video_url",
                detail=f"host={urlparse(url).hostname or ''} suffix={url_path_suffix(url) or ''}",
            )
        if not force and _is_direct_link_by_extension(url):
            return self._skip_result(
                "直链已跳过",
                category="direct_extension",
                detail=f"suffix={url_path_suffix(url) or ''}",
            )

        if not await _is_public_host(url):
            return self._skip_result(
                "已跳过本机/内网/保留地址链接",
                category="private_host",
                detail=f"host={urlparse(url).hostname or ''}",
            )

        exit_proxy = await self._resolve_exit_proxy(url)
        direct_check = await self._check_direct_link_by_content_type(url, exit_proxy)
        if not force and direct_check:
            return self._skip_result(
                "直链已跳过",
                category="direct_content_type",
                detail=str(direct_check),
            )

        async with self._lock:
            try:
                screenshot = await self._screenshot_page(url, exit_proxy)
            except BlankScreenshotError:
                logger.warning(f"[MikuSnap] 页面截图为空：url={redact_url(url)}")
                return self._skip_result("页面未渲染出有效内容", category="blank_screenshot")
            except IpCheckPageError as exc:
                return self._skip_result(
                    "检测到查 IP 网站，已拦截以免泄漏服务器地址",
                    category="ip_check",
                    detail=exc.hit.detail,
                )
            except PlaywrightTimeoutError:
                return self._skip_result("网页加载或截图超时", category="timeout")
            except Exception as exc:
                logger.error(f"[MikuSnap] screenshot failed: {redact_url(url)} {redact_text(str(exc))}")
                return self._skip_result("网页截图失败", category="screenshot_error", detail=str(exc))
        return {"ok": True, **screenshot}

    @staticmethod
    def _skip_result(reason: str, *, category: str, detail: str = "") -> dict[str, Any]:
        return {
            "ok": False,
            "reason": reason,
            "public_reason": reason,
            "category": category,
            "detail": detail,
        }

    @staticmethod
    async def _resolve_exit_proxy(url: str) -> str:
        if is_github_fetch_url(url):
            github = github_http_proxy()
            if github:
                return github
        pooled = await fetch_proxy_pool_server()
        if pooled:
            return pooled
        return screenshot_http_proxy()

    async def _check_direct_link_by_content_type(self, url: str, exit_proxy: str) -> dict[str, Any] | None:
        if is_github_fetch_url(url):
            return None
        timeout = HEAD_TIMEOUT_SECONDS
        headers = {"User-Agent": self._default_user_agent()}
        client_kwargs: dict[str, object] = {
            "follow_redirects": False,
            "timeout": timeout,
            "headers": headers,
        }
        if exit_proxy:
            client_kwargs["proxy"] = exit_proxy
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.head(url)
                logger.debug(
                    "直链 HEAD 检查："
                    f"url={redact_url(url)} "
                    f"status={response.status_code} "
                    f"content_type={response.headers.get('content-type', '')}"
                )
                if response.is_redirect:
                    return None
                if response.status_code in {405, 403} or not response.headers.get("content-type"):
                    response = await client.get(url, headers={"Range": "bytes=0-0"})
                    logger.debug(
                        "直链 GET Range 检查："
                        f"url={redact_url(url)} "
                        f"status={response.status_code} "
                        f"content_type={response.headers.get('content-type', '')}"
                    )
        except Exception as exc:
            logger.debug(f"[MikuSnap] 直链类型检查失败：url={redact_url(url)} error={redact_text(str(exc))}")
            return None

        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        content_disposition = response.headers.get("content-disposition", "").lower()
        if "attachment" in content_disposition:
            return {"content_type": content_type, "content_disposition": "attachment"}
        if any(content_type.startswith(prefix) for prefix in SKIP_CONTENT_TYPE_PREFIXES):
            return {"content_type": content_type or "unknown", "content_disposition": ""}
        return None

    async def _screenshot_page(self, url: str, exit_proxy: str) -> dict[str, Any]:
        color_scheme = "dark" if dark_mode_enabled() else "light"
        nav_url = resolve_github_url(url) if is_github_fetch_url(url) else url
        http_proxy = exit_proxy

        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", urlparse(url).netloc)[:80] or "page"
        shot_dir = self.output_dir / f"{int(time.time() * 1000)}_{safe_name}"
        shot_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            logger.debug(
                "开始截图："
                f"url={redact_url(url)} "
                f"nav={redact_url(nav_url)} "
                f"viewport={VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT} "
                f"color_scheme={color_scheme} "
                f"http_proxy={'on' if http_proxy else 'off'}"
            )
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-webrtc"],
            )
            context_kwargs: dict[str, object] = {
                "viewport": {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                "user_agent": self._default_user_agent(),
                "ignore_https_errors": True,
                "color_scheme": color_scheme,
            }
            if http_proxy:
                context_kwargs["proxy"] = {"server": http_proxy}
            context = await browser.new_context(**context_kwargs)
            try:
                await context.add_init_script(WEBRTC_BLOCK_SCRIPT)
                page = await context.new_page()
                await page.emulate_media(color_scheme=color_scheme)
                if color_scheme == "dark":
                    await page.add_init_script(DARK_MODE_INIT_SCRIPT)
                await page.goto(nav_url, wait_until="domcontentloaded", timeout=LOAD_TIMEOUT_MS)
                if color_scheme == "dark":
                    await page.evaluate(DARK_MODE_APPLY_SCRIPT)
                sample = await page.evaluate(PAGE_SAMPLE_SCRIPT)
                sample_title = ""
                sample_text = ""
                if isinstance(sample, dict):
                    raw_title = sample["title"] if "title" in sample else ""
                    raw_text = sample["text"] if "text" in sample else ""
                    sample_title = raw_title if isinstance(raw_title, str) else ""
                    sample_text = raw_text if isinstance(raw_text, str) else ""
                page_hit = detect_ip_check_page(sample_title, sample_text)
                if page_hit is not None:
                    raise IpCheckPageError(page_hit)
                await page.evaluate(LAZY_LOAD_SCRIPT)
                await page.wait_for_timeout(SETTLE_DELAY_MS)

                title = (await page.title()).strip() or urlparse(url).netloc or "网页"
                logger.debug(f"[MikuSnap] 页面加载完成：url={redact_url(url)} title={redact_text(title)}")
                paths = await self._capture_page_segments(
                    page=page,
                    shot_dir=shot_dir,
                )
            finally:
                await context.close()
                await browser.close()

        return {"title": title, "paths": [str(path) for path in paths]}

    async def _capture_page_segments(
        self,
        page: Any,
        shot_dir: Path,
    ) -> list[Path]:
        page_size = await page.evaluate(
            """
            () => ({
                width: Math.max(
                    document.documentElement.scrollWidth,
                    document.body ? document.body.scrollWidth : 0,
                    window.innerWidth
                ),
                height: Math.max(
                    document.documentElement.scrollHeight,
                    document.body ? document.body.scrollHeight : 0,
                    window.innerHeight
                )
            })
            """
        )
        page_width = min(max(int(page_size.get("width") or VIEWPORT_WIDTH), 1), VIEWPORT_WIDTH)
        page_height = max(int(page_size.get("height") or VIEWPORT_HEIGHT), 1)
        logger.debug(
            "页面尺寸："
            f"width={page_width} height={page_height} "
            f"max_segments={MAX_SEGMENTS} overlap={SEGMENT_OVERLAP}"
        )

        full_output = shot_dir / "page_full.png"
        await page.screenshot(path=str(full_output), full_page=True, timeout=SCREENSHOT_TIMEOUT_MS)
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(full_output) as image:
            if is_blank_image(image):
                full_output.unlink()
                shot_dir.rmdir()
                raise BlankScreenshotError

            if page_height <= VIEWPORT_HEIGHT:
                return [full_output]

            try:
                image_width, image_height = image.size
                logger.debug(
                    "整页截图完成，开始本地切图："
                    f"image_width={image_width} image_height={image_height} segment_height={SEGMENT_HEIGHT}"
                )

                if image_height <= SEGMENT_HEIGHT:
                    return [full_output]

                step = max(1, SEGMENT_HEIGHT - SEGMENT_OVERLAP)
                paths: list[Path] = []
                y = 0
                index = 1
                while y < image_height and len(paths) < MAX_SEGMENTS:
                    bottom = min(y + SEGMENT_HEIGHT, image_height)
                    if bottom <= y:
                        break

                    output = shot_dir / f"page_{index:02d}.png"
                    segment = image.crop((0, y, image_width, bottom))
                    if is_blank_image(segment):
                        logger.info(f"[MikuSnap] 丢弃空白分图：index={index} y={y} bottom={bottom}")
                        y += step
                        index += 1
                        continue
                    segment.save(output, format="PNG")
                    paths.append(output)

                    if bottom >= image_height:
                        break
                    y += step
                    index += 1

                if y < image_height and len(paths) >= MAX_SEGMENTS:
                    logger.debug(
                        "分图达到上限，页面可能被截断："
                        f"max_segments={MAX_SEGMENTS} last_y={y} image_height={image_height}"
                    )

                return paths or [full_output]
            except OSError as exc:
                logger.warning(f"[MikuSnap] 本地切图失败，回退发送整页图：{redact_text(str(exc))}")
                return [full_output]

    @staticmethod
    def _default_user_agent() -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

    @staticmethod
    def _clean_title(title: str) -> str:
        title = re.sub(r"\s+", " ", title).strip()
        return title[:80] or "网页"

    def build_skip_reason_message(self, url: str, result: dict[str, Any]) -> str:
        redacted_url = redact_url(url)
        category = result["category"] if "category" in result else ""
        if category == "ip_check":
            return build_ip_leak_scold(redacted_url)
        reason = redact_text(str(result["public_reason"] if "public_reason" in result else result["reason"] if "reason" in result else "未知原因"))
        return SKIP_REASON_TEMPLATE.format(
            reason=reason,
            url=redacted_url,
        )

    def build_message(self, result: dict[str, Any], url: str) -> Any:
        paths = [str(path) for path in result.get("paths", []) if path]
        title = self._clean_title(str(result.get("title") or urlparse(url).netloc or "网页"))
        first_node_text = f"{AI_NAME} | 网页\n{title}"

        if not paths:
            return f"{first_node_text}\n截图失败：未生成图片"

        image_segments: list[Any] = []
        for path_text in paths:
            path = Path(path_text)
            if path.is_file():
                image_segments.append(MessageSegment.image(path))

        if not image_segments:
            return f"{first_node_text}\n截图失败：图片文件不存在"

        if len(image_segments) > 1:
            return MessageSegment.node([first_node_text, *image_segments])

        return [first_node_text, *image_segments]

    def log_skip(self, url: str, result: dict[str, Any]) -> None:
        logger.info(
            "[MikuSnap] 跳过链接："
            f"url={redact_url(url)} "
            f"reason={redact_text(str(result.get('reason') or '未知原因'))} "
            f"category={redact_text(str(result.get('category') or 'unknown'))} "
            f"detail={redact_text(str(result.get('detail') or ''))}"
        )

    def log_success(self, url: str, result: dict[str, Any]) -> None:
        logger.info(
            "[MikuSnap] 截图完成："
            f"url={redact_url(url)} "
            f"title={redact_text(str(result.get('title') or ''))} "
            f"images={len(result.get('paths', []) or [])}"
        )
