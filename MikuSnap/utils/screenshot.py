from __future__ import annotations

import asyncio
import ipaddress
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlunparse

import httpx
from gsuid_core.logger import logger
from gsuid_core.segment import MessageSegment

from .config import cfg_bool, cfg_float, cfg_int, cfg_list_str, cfg_str
from .resource.RESOURCE_PATH import SCREENSHOT_PATH

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover
    PlaywrightTimeoutError = TimeoutError  # type: ignore[assignment]
    async_playwright = None  # type: ignore[assignment]

URL_RE = re.compile(r"https?://[^\s<>'\"，。！？、（）()【】\[\]{}]+", re.IGNORECASE)
MANUAL_COMMANDS = ("网页截图", "webshot", "网页快照")

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
    return any(stripped.startswith(command.lower()) for command in MANUAL_COMMANDS)


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
        self._lock = asyncio.Semaphore(cfg_int("max_concurrency", 1, 1, 20))
        self._lock_size = cfg_int("max_concurrency", 1, 1, 20)

    def _refresh_lock(self) -> None:
        current = cfg_int("max_concurrency", 1, 1, 20)
        if current != self._lock_size:
            self._lock = asyncio.Semaphore(current)
            self._lock_size = current

    async def handle_url(self, url: str, force: bool) -> dict[str, Any]:
        if async_playwright is None:
            return self._skip_result(
                "缺少 playwright 依赖，无法截图",
                category="dependency_missing",
                detail="请安装依赖后执行：playwright install chromium",
            )

        extra_video_hosts = cfg_list_str("extra_video_hosts")
        if not force and _is_video_url(url, extra_video_hosts):
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

        if cfg_bool("block_private_hosts", True) and not await _is_public_host(url):
            return self._skip_result(
                "已跳过本机/内网/保留地址链接",
                category="private_host",
                detail=f"host={urlparse(url).hostname or ''}",
            )

        direct_check = await self._check_direct_link_by_content_type(url)
        if not force and direct_check:
            return self._skip_result(
                "直链已跳过",
                category="direct_content_type",
                detail=str(direct_check),
            )

        self._refresh_lock()
        async with self._lock:
            try:
                screenshot = await self._screenshot_page(url)
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

    async def _check_direct_link_by_content_type(self, url: str) -> dict[str, Any] | None:
        timeout = cfg_float("head_timeout", 8.0, 1.0, 60.0)
        headers = {"User-Agent": self._get_user_agent()}
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=timeout, headers=headers) as client:
                response = await client.head(url)
                self._log_debug(
                    "直链 HEAD 检查："
                    f"url={redact_url(url)} "
                    f"status={response.status_code} "
                    f"content_type={response.headers.get('content-type', '')}"
                )
                if response.is_redirect:
                    return None
                if response.status_code in {405, 403} or not response.headers.get("content-type"):
                    response = await client.get(url, headers={"Range": "bytes=0-0"})
                    self._log_debug(
                        "直链 GET Range 检查："
                        f"url={redact_url(url)} "
                        f"status={response.status_code} "
                        f"content_type={response.headers.get('content-type', '')}"
                    )
        except Exception as exc:
            self._log_debug(f"直链类型检查失败：url={redact_url(url)} error={redact_text(str(exc))}")
            return None

        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        content_disposition = response.headers.get("content-disposition", "").lower()
        if "attachment" in content_disposition:
            return {"content_type": content_type, "content_disposition": "attachment"}
        if any(content_type.startswith(prefix) for prefix in SKIP_CONTENT_TYPE_PREFIXES):
            return {"content_type": content_type or "unknown", "content_disposition": ""}
        return None

    async def _screenshot_page(self, url: str) -> dict[str, Any]:
        viewport_width = cfg_int("viewport_width", 1365, 320, 4096)
        viewport_height = cfg_int("viewport_height", 900, 320, 4096)
        load_timeout = int(cfg_float("load_timeout", 30.0, 1.0, 180.0) * 1000)
        screenshot_timeout = int(cfg_float("screenshot_timeout", 30.0, 1.0, 180.0) * 1000)
        user_agent = self._get_user_agent()

        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", urlparse(url).netloc)[:80] or "page"
        shot_dir = self.output_dir / f"{int(time.time() * 1000)}_{safe_name}"
        shot_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            self._log_debug(
                "开始截图："
                f"url={redact_url(url)} "
                f"viewport={viewport_width}x{viewport_height} "
                f"load_timeout={load_timeout}ms screenshot_timeout={screenshot_timeout}ms"
            )
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
                await page.wait_for_timeout(int(cfg_float("settle_delay", 1.5, 0.0, 30.0) * 1000))

                title = (await page.title()).strip() or urlparse(url).netloc or "网页"
                self._log_debug(f"页面加载完成：url={redact_url(url)} title={redact_text(title)}")
                paths = await self._capture_page_segments(
                    page=page,
                    shot_dir=shot_dir,
                    viewport_width=viewport_width,
                    viewport_height=viewport_height,
                    screenshot_timeout=screenshot_timeout,
                )
            finally:
                await context.close()
                await browser.close()

        return {"title": title, "paths": [str(path) for path in paths]}

    async def _capture_page_segments(
        self,
        page: Any,
        shot_dir: Path,
        viewport_width: int,
        viewport_height: int,
        screenshot_timeout: int,
    ) -> list[Path]:
        split_enabled = cfg_bool("split_long_page", True)
        max_segments = cfg_int("max_segments", 8, 1, 80)
        overlap = cfg_int("segment_overlap", 80, 0, 2000)
        segment_height = cfg_int("segment_height", viewport_height, 200, 10000)

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
        page_width = min(max(int(page_size.get("width") or viewport_width), 1), viewport_width)
        page_height = max(int(page_size.get("height") or viewport_height), 1)
        self._log_debug(
            "页面尺寸："
            f"width={page_width} height={page_height} "
            f"split={split_enabled} max_segments={max_segments} overlap={overlap}"
        )

        full_output = shot_dir / "page_full.png"
        await page.screenshot(path=str(full_output), full_page=True, timeout=screenshot_timeout)
        if not split_enabled or page_height <= viewport_height:
            return [full_output]

        try:
            from PIL import Image as PilImage
        except Exception as exc:
            self._log_debug(f"缺少 Pillow，无法本地切图，回退发送整页图：{redact_text(str(exc))}")
            return [full_output]

        try:
            PilImage.MAX_IMAGE_PIXELS = None
            with PilImage.open(full_output) as image:
                image_width, image_height = image.size
                self._log_debug(
                    "整页截图完成，开始本地切图："
                    f"image_width={image_width} image_height={image_height} segment_height={segment_height}"
                )

                if image_height <= segment_height:
                    return [full_output]

                step = max(1, segment_height - overlap)
                paths: list[Path] = []
                y = 0
                index = 1
                while y < image_height and len(paths) < max_segments:
                    bottom = min(y + segment_height, image_height)
                    if bottom <= y:
                        break

                    output = shot_dir / f"page_{index:02d}.png"
                    self._log_debug(f"切出分图：index={index} y={y} bottom={bottom} output={output.name}")
                    image.crop((0, y, image_width, bottom)).save(output, format="PNG")
                    paths.append(output)

                    if bottom >= image_height:
                        break
                    y += step
                    index += 1

                if y < image_height and len(paths) >= max_segments:
                    self._log_debug(
                        "分图达到上限，页面可能被截断："
                        f"max_segments={max_segments} last_y={y} image_height={image_height}"
                    )

                return paths or [full_output]
        except Exception as exc:
            self._log_debug(f"本地切图失败，回退发送整页图：{redact_text(str(exc))}")
            return [full_output]

    def _get_user_agent(self) -> str:
        configured = cfg_str("user_agent", "").strip()
        return configured or self._default_user_agent()

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

    @staticmethod
    def _format_template(template: str, **values: Any) -> str:
        try:
            return template.format(**values)
        except Exception:
            return str(values.get("ai_name") or "网页")

    def build_skip_reason_message(self, url: str, result: dict[str, Any]) -> str:
        template = cfg_str("skip_reason_template", "网页截图已跳过：{reason}\n链接：{url}")
        reason = redact_text(str(result.get("public_reason") or result.get("reason") or "未知原因"))
        redacted_url = redact_url(url)
        values = {
            "reason": reason,
            "url": redacted_url,
            "host": redact_text(urlparse(url).hostname or ""),
            "suffix": url_path_suffix(url) or "",
        }
        try:
            return template.format(**values)
        except Exception:
            return f"网页截图已跳过：{reason}\n链接：{redacted_url}"

    def build_message(self, result: dict[str, Any], url: str) -> Any:
        paths = [str(path) for path in result.get("paths", []) if path]
        title = self._clean_title(str(result.get("title") or urlparse(url).netloc or "网页"))
        ai_name = cfg_str("ai_name", "解析").strip() or "解析"
        forward_title_template = cfg_str("forward_title_template", "{ai_name} | 网页 {title}")
        first_node_template = cfg_str("first_node_template", "{ai_name} | 网页\n{title}")
        use_forward = cfg_bool("forward_enable", True) and len(paths) > 1

        title_text = self._format_template(
            forward_title_template,
            ai_name=ai_name,
            title=title,
            bot_name=title,
            url=url,
            page_count=len(paths),
        )
        first_node_text = self._format_template(
            first_node_template,
            ai_name=ai_name,
            title=title,
            bot_name=title,
            url=url,
            page_count=len(paths),
        )

        if not paths:
            return f"{first_node_text}\n截图失败：未生成图片"

        image_segments: list[Any] = []
        for path_text in paths:
            path = Path(path_text)
            if path.is_file():
                image_segments.append(MessageSegment.image(path))

        if not image_segments:
            return f"{first_node_text}\n截图失败：图片文件不存在"

        if use_forward:
            return MessageSegment.node([first_node_text, *image_segments])

        return [first_node_text, *image_segments] if len(image_segments) == 1 else [title_text, *image_segments]

    def log_skip(self, url: str, result: dict[str, Any]) -> None:
        if not cfg_bool("debug_skip_log", True):
            return
        logger.info(
            "[MikuSnap] 跳过链接："
            f"url={redact_url(url)} "
            f"reason={redact_text(str(result.get('reason') or '未知原因'))} "
            f"category={redact_text(str(result.get('category') or 'unknown'))} "
            f"detail={redact_text(str(result.get('detail') or ''))}"
        )

    def log_success(self, url: str, result: dict[str, Any]) -> None:
        if not cfg_bool("debug_success_log", True):
            return
        logger.info(
            "[MikuSnap] 截图完成："
            f"url={redact_url(url)} "
            f"title={redact_text(str(result.get('title') or ''))} "
            f"images={len(result.get('paths', []) or [])}"
        )

    def _log_debug(self, message: str) -> None:
        if cfg_bool("debug_detail_log", False):
            logger.info(f"[MikuSnap] {message}")
