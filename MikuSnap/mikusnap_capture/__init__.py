from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.config import cfg_bool, cfg_int
from ..utils.screenshot import (
    MANUAL_COMMANDS,
    ScreenshotService,
    extract_urls,
    looks_like_manual_command,
    normalize_url,
    redact_url,
)

manual_sv = SV("MikuSnap手动截图", priority=5, area="ALL")
auto_sv = SV("MikuSnap自动解析", priority=20, area="ALL")
service = ScreenshotService()


def _string_attr(obj: object, name: str) -> str:
    if not hasattr(obj, name):
        return ""
    value = getattr(obj, name)
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return ""


def _text_from_message_item(item: object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        item_type = item["type"] if "type" in item else ""
        data = item["data"] if "data" in item and isinstance(item["data"], dict) else {}
        text = data["text"] if item_type == "text" and "text" in data else ""
        return text if isinstance(text, str) else ""
    item_type = _string_attr(item, "type")
    data = getattr(item, "data") if hasattr(item, "data") else None
    if item_type == "text" and isinstance(data, dict) and "text" in data:
        text = data["text"]
        return text if isinstance(text, str) else ""
    return ""


def _message_to_text(message: object) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, Iterable):
        return "".join(_text_from_message_item(item) for item in message)
    return ""


def _event_text(ev: Event) -> str:
    raw_text = _string_attr(ev, "raw_text").strip()
    if raw_text:
        return raw_text
    content = getattr(ev, "content") if hasattr(ev, "content") else None
    content_text = _message_to_text(content).strip()
    if content_text:
        return content_text
    message = getattr(ev, "message") if hasattr(ev, "message") else None
    message_text = _message_to_text(message).strip()
    if message_text:
        return message_text
    command = _string_attr(ev, "command").strip()
    text = _string_attr(ev, "text").strip()
    return f"{command} {text}".strip()


async def _send_result(bot: Bot, url: str, result: dict[str, Any]) -> None:
    if result["ok"]:
        service.log_success(url, result)
        await bot.send(service.build_message(result, url))
        return
    service.log_skip(url, result)
    await bot.send(service.build_skip_reason_message(url, result))


@manual_sv.on_command(MANUAL_COMMANDS, block=True, prefix=False)
async def screenshot_command(bot: Bot, ev: Event) -> None:
    """手动截图网页：网页截图 https://example.com"""
    if not cfg_bool("enabled", True):
        return

    url_text = _string_attr(ev, "text").strip()
    urls = extract_urls(url_text)
    normalized_url = normalize_url(urls[0] if urls else url_text)
    if not normalized_url:
        await bot.send("请提供有效的 http/https 网页链接，例如：网页截图 https://example.com")
        return

    logger.info(f"[MikuSnap] 手动截图：url={redact_url(normalized_url)}")
    result = await service.handle_url(normalized_url, force=True)
    await _send_result(bot, normalized_url, result)


@auto_sv.on_message(block=False, prefix=False)
async def auto_screenshot(bot: Bot, ev: Event) -> None:
    """自动解析消息中的网页链接并发送截图。"""
    if not cfg_bool("enabled", True) or not cfg_bool("auto_enable", True):
        return

    message = _event_text(ev)
    if not message or looks_like_manual_command(message):
        return

    urls = extract_urls(message)
    if not urls:
        return

    logger.info(f"[MikuSnap] 收到网页链接：count={len(urls)} urls={', '.join(redact_url(url) for url in urls)}")
    max_urls = cfg_int("max_urls_per_message", 2, 1, 20)
    for url in urls[:max_urls]:
        result = await service.handle_url(url, force=False)
        if result["ok"]:
            service.log_success(url, result)
            await bot.send(service.build_message(result, url))
            continue
        service.log_skip(url, result)
        if cfg_bool("send_skip_reason", True):
            await bot.send(service.build_skip_reason_message(url, result))
