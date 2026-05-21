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
    "自动识别聊天网页链接，跳过视频/直链后按段截图并合并转发。",
    "1.1.0",
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
            self._log_success(normalized_url, result)
            yield event.chain_result(self._build_message_chain(result, normalized_url))
        else:
            self._log_skip(normalized_url, result)
            yield event.plain_result(self._build_skip_reason_message(normalized_url, result))
        event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_screenshot(self, event: AstrMessageEvent):
        """自动解析消息里的网页链接并发送网页截图。"""
        if not bool(_get_config_value(self.config, "auto_enable", True)):
            return

        urls = self._extract_urls(event.message_str)
        if not urls:
            return

        self._log_debug(
            "收到消息链接："
            f"count={len(urls)} "
            f"urls={', '.join(_redact_url(url) for url in urls)}"
        )

        max_urls = int(_get_config_value(self.config, "max_urls_per_message", 2))
        handled = False
        skip_notified = False
        for url in urls[:max_urls]:
            result = await self._handle_url(url, force=False)
            if not result["ok"]:
                self._log_skip(url, result)
                if bool(_get_config_value(self.config, "send_skip_reason", True)):
                    yield event.plain_result(self._build_skip_reason_message(url, result))
                    skip_notified = True
                continue
            handled = True
            self._log_success(url, result)
            yield event.chain_result(self._build_message_chain(result, url))

        if (handled or skip_notified) and bool(_get_config_value(self.config, "stop_event_after_send", False)):
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

    def _build_skip_reason_message(self, url: str, result: dict[str, Any]) -> str:
        template = str(
            _get_config_value(
                self.config,
                "skip_reason_template",
                "网页截图已跳过：{reason}\n链接：{url}",
            )
        )
        reason = _redact_text(str(result.get("public_reason") or result.get("reason") or "未知原因"))
        redacted_url = _redact_url(url)
        values = {
            "reason": reason,
            "url": redacted_url,
            "host": _redact_text(urlparse(url).hostname or ""),
            "suffix": _url_path_suffix(url) or "",
        }
        try:
            return template.format(**values)
        except Exception:
            return f"网页截图已跳过：{reason}\n链接：{redacted_url}"

    def _log_skip(self, url: str, result: dict[str, Any]) -> None:
        if not bool(_get_config_value(self.config, "debug_skip_log", True)):
            return
        logger.info(
            "[web_screenshot] 跳过链接："
            f"url={_redact_url(url)} "
            f"reason={_redact_text(str(result.get('reason') or '未知原因'))} "
            f"category={_redact_text(str(result.get('category') or 'unknown'))} "
            f"detail={_redact_text(str(result.get('detail') or ''))}"
        )

    def _log_success(self, url: str, result: dict[str, Any]) -> None:
        if not bool(_get_config_value(self.config, "debug_success_log", True)):
            return
        logger.info(
            "[web_screenshot] 截图完成："
            f"url={_redact_url(url)} "
            f"title={_redact_text(str(result.get('title') or ''))} "
            f"images={len(result.get('paths', []) or [])}"
        )

    def _log_debug(self, message: str) -> None:
        if bool(_get_config_value(self.config, "debug_detail_log", False)):
            logger.info(f"[web_screenshot] {message}")

    def _build_message_chain(self, result: dict[str, Any], url: str) -> list[Any]:
        paths = [str(path) for path in result.get("paths", []) if path]
        title = self._clean_title(str(result.get("title") or urlparse(url).netloc or "网页"))
        ai_name = (
            str(_get_config_value(self.config, "ai_name", _get_config_value(self.config, "resolver_name", "小维解析"))).strip()
            or "小维解析"
        )
        node_name = str(_get_config_value(self.config, "forward_node_name", ai_name)).strip() or ai_name
        forward_title_template = str(
            _get_config_value(self.config, "forward_title_template", "{ai_name} | 网页 {title}")
        )
        first_node_template = str(
            _get_config_value(self.config, "first_node_template", "{ai_name} | 网页\n{title}")
        )
        node_uin = str(_get_config_value(self.config, "forward_node_uin", "10000")).strip() or "10000"
        use_forward = bool(_get_config_value(self.config, "forward_enable", True)) and len(paths) > 1

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
            return [Comp.Plain(f"{first_node_text}\n截图失败：未生成图片")]

        if use_forward:
            nodes = [Comp.Node(uin=node_uin, name=node_name, content=[Comp.Plain(first_node_text)])]
            for path in paths:
                nodes.append(Comp.Node(uin=node_uin, name=node_name, content=[Comp.Image.fromFileSystem(path)]))
            return [Comp.Plain(title_text), Comp.Nodes(nodes)]

        chain: list[Any] = [Comp.Plain(first_node_text)]
        for path in paths:
            chain.append(Comp.Image.fromFileSystem(path))
        chain.append(Comp.Plain(f"\n{url}"))
        return chain

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

    async def _handle_url(self, url: str, force: bool) -> dict[str, Any]:
        if async_playwright is None:
            return self._skip_result(
                "缺少 playwright 依赖，无法截图",
                category="dependency_missing",
                detail="请在插件环境安装 requirements.txt 后执行：playwright install chromium",
            )

        extra_video_hosts = list(_get_config_value(self.config, "extra_video_hosts", []))
        if not force and _is_video_url(url, extra_video_hosts):
            return self._skip_result(
                "视频链接已跳过",
                category="video_url",
                detail=f"host={urlparse(url).hostname or ''} suffix={_url_path_suffix(url) or ''}",
            )
        if not force and _is_direct_link_by_extension(url):
            return self._skip_result(
                "直链已跳过",
                category="direct_extension",
                detail=f"suffix={_url_path_suffix(url) or ''}",
            )

        if bool(_get_config_value(self.config, "block_private_hosts", True)) and not await _is_public_host(url):
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

        async with self._lock:
            try:
                screenshot = await self._screenshot_page(url)
            except PlaywrightTimeoutError:
                return self._skip_result("网页加载或截图超时", category="timeout")
            except Exception as exc:
                logger.error(f"[web_screenshot] screenshot failed: {_redact_url(url)} {_redact_text(str(exc))}")
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
        timeout = float(_get_config_value(self.config, "head_timeout", 8.0))
        headers = {"User-Agent": self._get_user_agent()}
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=timeout, headers=headers) as client:
                response = await client.head(url)
                self._log_debug(
                    "直链 HEAD 检查："
                    f"url={_redact_url(url)} "
                    f"status={response.status_code} "
                    f"content_type={response.headers.get('content-type', '')}"
                )
                if response.is_redirect:
                    return None
                if response.status_code in {405, 403} or not response.headers.get("content-type"):
                    response = await client.get(url, headers={"Range": "bytes=0-0"})
                    self._log_debug(
                        "直链 GET Range 检查："
                        f"url={_redact_url(url)} "
                        f"status={response.status_code} "
                        f"content_type={response.headers.get('content-type', '')}"
                    )
        except Exception as exc:
            self._log_debug(f"直链类型检查失败：url={_redact_url(url)} error={_redact_text(str(exc))}")
            return None

        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        content_disposition = response.headers.get("content-disposition", "").lower()
        if "attachment" in content_disposition:
            return {"content_type": content_type, "content_disposition": "attachment"}
        if any(content_type.startswith(prefix) for prefix in SKIP_CONTENT_TYPE_PREFIXES):
            return {"content_type": content_type or "unknown", "content_disposition": ""}
        return None

    async def _screenshot_page(self, url: str) -> dict[str, Any]:
        viewport_width = int(_get_config_value(self.config, "viewport_width", 1365))
        viewport_height = int(_get_config_value(self.config, "viewport_height", 900))
        load_timeout = int(float(_get_config_value(self.config, "load_timeout", 30.0)) * 1000)
        screenshot_timeout = int(float(_get_config_value(self.config, "screenshot_timeout", 30.0)) * 1000)
        user_agent = self._get_user_agent()

        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", urlparse(url).netloc)[:80] or "page"
        shot_dir = self.output_dir / f"{int(time.time() * 1000)}_{safe_name}"
        shot_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            self._log_debug(
                "开始截图："
                f"url={_redact_url(url)} "
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
                await page.wait_for_timeout(int(float(_get_config_value(self.config, "settle_delay", 1.5)) * 1000))

                title = (await page.title()).strip() or urlparse(url).netloc or "网页"
                self._log_debug(f"页面加载完成：url={_redact_url(url)} title={_redact_text(title)}")
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
        split_enabled = bool(_get_config_value(self.config, "split_long_page", True))
        max_segments = max(1, int(_get_config_value(self.config, "max_segments", 8)))
        overlap = max(0, int(_get_config_value(self.config, "segment_overlap", 80)))

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

        if not split_enabled or page_height <= viewport_height:
            output = shot_dir / "page_full.png"
            await page.screenshot(path=str(output), full_page=True, timeout=screenshot_timeout)
            return [output]

        segment_height = max(200, int(_get_config_value(self.config, "segment_height", viewport_height)))
        step = max(1, segment_height - overlap)
        paths: list[Path] = []
        y = 0
        index = 1
        while y < page_height and len(paths) < max_segments:
            height = min(segment_height, page_height - y)
            if height <= 0:
                break
            output = shot_dir / f"page_{index:02d}.png"
            self._log_debug(f"截取分图：index={index} y={y} height={height} output={output.name}")
            await page.screenshot(
                path=str(output),
                clip={"x": 0, "y": y, "width": page_width, "height": height},
                timeout=screenshot_timeout,
            )
            paths.append(output)
            if y + height >= page_height:
                break
            y += step
            index += 1

        return paths

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


def _redact_url(url: str) -> str:
    """返回可展示/可记录的脱敏链接：保留协议、域名和路径，移除账号、查询参数和片段。"""
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


def _redact_text(text: str, limit: int = 160) -> str:
    text = re.sub(r"(token|access_token|refresh_token|key|secret|password|passwd|pwd|cookie)=([^&\s]+)", r"\1=***", text, flags=re.IGNORECASE)
    text = re.sub(r"https?://[^\s<>'\"，。！？、（）()【】\[\]{}]+", lambda m: _redact_url(m.group(0)), text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("..." if len(text) > limit else "")
