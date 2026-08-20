from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from gsuid_core.logger import logger
from gsuid_core.pool import to_thread
from gsuid_core.utils.fonts.fonts import core_font
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import crop_center_img

from ..utils.config import cfg_bool
from ..utils.github_api import GitHubCardInfo, github_get_bytes

CARD_WIDTH = 900
MARGIN = 28
PAD = 44
AVATAR_SIZE = 168
RADIUS = 26
ISO_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

LANGUAGE_COLORS: dict[str, str] = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "Java": "#b07219",
    "C": "#555555",
    "C++": "#f34b7d",
    "C#": "#178600",
    "PHP": "#4F5D95",
    "Ruby": "#701516",
    "Swift": "#F05138",
    "Kotlin": "#A97BFF",
    "Dart": "#00B4AB",
    "Vue": "#41b883",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Shell": "#89e051",
    "Dockerfile": "#384d54",
    "Lua": "#000080",
    "Scala": "#c22d40",
    "Elixir": "#6e4a7e",
    "Zig": "#ec915c",
    "PowerShell": "#012456",
    "Jupyter Notebook": "#DA5B0B",
    "Svelte": "#ff3e00",
    "Astro": "#ff5a03",
    "Markdown": "#083fa1",
    "JSON": "#292929",
    "YAML": "#cb171e",
}


@dataclass(frozen=True)
class CardTheme:
    canvas: tuple[int, int, int]
    card: tuple[int, int, int]
    border: tuple[int, int, int]
    title: tuple[int, int, int]
    desc: tuple[int, int, int]
    muted: tuple[int, int, int]
    accent: tuple[int, int, int]
    star: tuple[int, int, int]
    pill_bg: tuple[int, int, int]
    pill_fg: tuple[int, int, int]
    shadow: tuple[int, int, int, int]
    danger: tuple[int, int, int]
    ok: tuple[int, int, int]


LIGHT_THEME = CardTheme(
    canvas=(238, 241, 245),
    card=(255, 255, 255),
    border=(216, 222, 228),
    title=(31, 35, 40),
    desc=(88, 96, 105),
    muted=(110, 119, 129),
    accent=(9, 105, 218),
    star=(156, 110, 12),
    pill_bg=(240, 246, 252),
    pill_fg=(9, 105, 218),
    shadow=(15, 23, 42, 42),
    danger=(207, 34, 46),
    ok=(26, 127, 55),
)
DARK_THEME = CardTheme(
    canvas=(13, 17, 23),
    card=(22, 27, 34),
    border=(48, 54, 61),
    title=(230, 237, 243),
    desc=(139, 148, 158),
    muted=(110, 118, 129),
    accent=(88, 166, 255),
    star=(227, 179, 65),
    pill_bg=(33, 38, 45),
    pill_fg=(165, 216, 255),
    shadow=(0, 0, 0, 90),
    danger=(248, 81, 73),
    ok=(63, 185, 80),
)


def _hex_rgb(color: str) -> tuple[int, int, int]:
    text = color.lstrip("#")
    if len(text) != 6:
        return (88, 166, 255)
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def _text_w(font: ImageFont.FreeTypeFont, text: str) -> int:
    return int(font.getlength(text))


def _text_h(font: ImageFont.FreeTypeFont) -> int:
    bbox = font.getbbox("Ag")
    return int(bbox[3] - bbox[1])


def _round_corners(im: Image.Image, radius: int) -> Image.Image:
    im = im.convert("RGBA")
    width, height = im.size
    scale = 4
    mask = Image.new("L", (width * scale, height * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1),
        radius=radius * scale,
        fill=255,
    )
    mask = mask.resize((width, height), Image.Resampling.LANCZOS)
    im.putalpha(mask)
    return im


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int) -> list[str]:
    if not text or max_lines <= 0:
        return []
    lines: list[str] = []
    current = ""
    for char in text.replace("\n", " "):
        trial = current + char
        if _text_w(font, trial) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = char
        if len(lines) >= max_lines:
            current = ""
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines:
        rest_exists = bool(current) or len("".join(lines)) < len(text.replace("\n", " "))
        if rest_exists:
            last = lines[-1]
            while last and _text_w(font, last + "…") > max_width:
                last = last[:-1]
            lines[-1] = f"{last}…" if last else "…"
    return lines


def _format_count(value: int) -> str:
    if value < 1000:
        return str(value)
    if value < 1_000_000:
        text = f"{value / 1000:.1f}".rstrip("0").rstrip(".")
        return f"{text}k"
    text = f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".")
    return f"{text}M"


def _relative_time(iso: str) -> str:
    if not iso or ISO_PREFIX_RE.match(iso) is None:
        return ""
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    seconds = int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    if seconds < 86400 * 30:
        return f"{seconds // 86400} 天前"
    if seconds < 86400 * 365:
        return f"{seconds // (86400 * 30)} 个月前"
    return f"{seconds // (86400 * 365)} 年前"


def _star_points(cx: float, cy: float, outer: float, inner: float) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for index in range(10):
        radius = outer if index % 2 == 0 else inner
        angle = math.radians(-90 + index * 36)
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def _draw_star(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color: tuple[int, int, int]) -> None:
    cx = x + size / 2
    cy = y + size / 2
    draw.polygon(_star_points(cx, cy, size / 2, size / 4.6), fill=color)


def _draw_fork(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color: tuple[int, int, int]) -> None:
    r = max(2, size // 7)
    draw.ellipse((x + 2, y + 2, x + 2 + r * 2, y + 2 + r * 2), outline=color, width=2)
    draw.ellipse((x + 2, y + size - 2 - r * 2, x + 2 + r * 2, y + size - 2), outline=color, width=2)
    draw.ellipse((x + size - 2 - r * 2, y + size // 2 - r, x + size - 2, y + size // 2 + r), outline=color, width=2)
    draw.line((x + 2 + r, y + 2 + r * 2, x + 2 + r, y + size - 2 - r * 2), fill=color, width=2)
    draw.line((x + 2 + r, y + size // 2, x + size - 2 - r * 2, y + size // 2), fill=color, width=2)


def _draw_eye(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color: tuple[int, int, int]) -> None:
    draw.arc((x + 1, y + size // 4, x + size - 1, y + size * 3 // 4), 0, 360, fill=color, width=2)
    r = max(2, size // 6)
    draw.ellipse(
        (x + size // 2 - r, y + size // 2 - r, x + size // 2 + r, y + size // 2 + r),
        fill=color,
    )


def _draw_issue(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color: tuple[int, int, int]) -> None:
    draw.ellipse((x + 1, y + 1, x + size - 1, y + size - 1), outline=color, width=2)
    dot = max(2, size // 6)
    draw.ellipse(
        (x + size // 2 - dot, y + size // 2 - dot, x + size // 2 + dot, y + size // 2 + dot),
        fill=color,
    )


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    fg: tuple[int, int, int],
    bg: tuple[int, int, int],
    font: ImageFont.FreeTypeFont,
    dot: tuple[int, int, int] | None = None,
) -> int:
    pad_x = 12
    height = 30
    extra = 16 if dot is not None else 0
    width = _text_w(font, text) + pad_x * 2 + extra
    draw.rounded_rectangle((x, y, x + width, y + height), radius=15, fill=bg)
    text_x = x + pad_x + extra
    if dot is not None:
        draw.ellipse((x + 10, y + 10, x + 20, y + 20), fill=dot)
    draw.text((text_x, y + height // 2), text, font=font, fill=fg, anchor="lm")
    return width


def _placeholder_avatar(letter: str, theme: CardTheme) -> Image.Image:
    img = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (*theme.accent, 255))
    draw = ImageDraw.Draw(img)
    font = core_font(72)
    draw.text(
        (AVATAR_SIZE // 2, AVATAR_SIZE // 2),
        (letter[:1] or "?").upper(),
        font=font,
        fill=theme.card,
        anchor="mm",
    )
    return _round_corners(img, 28)


async def _load_avatar(url: str, theme: CardTheme, letter: str) -> Image.Image:
    if url:
        data = await github_get_bytes(url)
        if data:
            try:
                avatar = Image.open(BytesIO(data)).convert("RGBA")
            except OSError:
                return _placeholder_avatar(letter, theme)
            avatar = crop_center_img(avatar, AVATAR_SIZE, AVATAR_SIZE)
            return _round_corners(avatar, 28)
    return _placeholder_avatar(letter, theme)


def _draw_stat(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    kind: str,
    value: str,
    label: str,
    theme: CardTheme,
    value_font: ImageFont.FreeTypeFont,
    label_font: ImageFont.FreeTypeFont,
) -> int:
    icon = 22
    if kind == "star":
        _draw_star(draw, x, y + 4, icon, theme.star)
    elif kind == "fork":
        _draw_fork(draw, x, y + 4, icon, theme.muted)
    elif kind == "watch":
        _draw_eye(draw, x, y + 4, icon, theme.muted)
    else:
        _draw_issue(draw, x, y + 4, icon, theme.muted)
    tx = x + icon + 8
    draw.text((tx, y + 14), value, font=value_font, fill=theme.title, anchor="lm")
    lx = tx + _text_w(value_font, value) + 6
    draw.text((lx, y + 14), label, font=label_font, fill=theme.muted, anchor="lm")
    return lx + _text_w(label_font, label) - x + 28


def draw_github_card(info: GitHubCardInfo, avatar: Image.Image, dark: bool) -> Image.Image:
    theme = DARK_THEME if dark else LIGHT_THEME
    title_font = core_font(48)
    owner_font = core_font(32)
    desc_font = core_font(24)
    meta_font = core_font(20)
    small_font = core_font(18)
    footer_font = core_font(18)
    value_font = core_font(26)

    inner_w = CARD_WIDTH - MARGIN * 2
    text_w = inner_w - PAD * 2 - AVATAR_SIZE - 28
    y = MARGIN + PAD

    if info.kind == "repo":
        owner_line = f"{info.owner} /"
        repo_lines = _wrap_text(info.name, title_font, text_w, 2)
        desc_lines = _wrap_text(info.description, desc_font, inner_w - PAD * 2, 4)
        badges: list[tuple[str, tuple[int, int, int], tuple[int, int, int], tuple[int, int, int] | None]] = [
            ("Public", theme.ok, theme.pill_bg, None),
        ]
        if info.language:
            badges.append(
                (
                    info.language,
                    theme.title,
                    theme.pill_bg,
                    _hex_rgb(LANGUAGE_COLORS[info.language] if info.language in LANGUAGE_COLORS else "#8b949e"),
                )
            )
        if info.license_name:
            badges.append((info.license_name, theme.muted, theme.pill_bg, None))
        if info.archived:
            badges.append(("Archived", theme.danger, theme.pill_bg, None))
        if info.is_fork:
            badges.append(("Fork", theme.muted, theme.pill_bg, None))
        stats = [
            ("star", _format_count(info.stars), "Star"),
            ("fork", _format_count(info.forks), "Fork"),
            ("watch", _format_count(info.watchers), "Watch"),
            ("issue", _format_count(info.open_issues), "Issues"),
        ]
        topics = info.topics[:10]
        footer = info.html_url.replace("https://", "")
        updated = _relative_time(info.pushed_at or info.updated_at)
        extra_line = ""
        if info.forked_from:
            extra_line = f"Forked from {info.forked_from}"
        elif info.homepage:
            extra_line = info.homepage
    else:
        owner_line = info.user_type
        repo_lines = _wrap_text(info.name or info.login, title_font, text_w, 2)
        desc_lines = _wrap_text(info.bio, desc_font, inner_w - PAD * 2, 4)
        badges = [(info.login, theme.accent, theme.pill_bg, None)]
        if info.company:
            badges.append((info.company, theme.muted, theme.pill_bg, None))
        if info.location:
            badges.append((info.location, theme.muted, theme.pill_bg, None))
        stats = [
            ("star", _format_count(info.followers), "Followers"),
            ("watch", _format_count(info.following), "Following"),
            ("fork", _format_count(info.public_repos), "Repos"),
        ]
        topics = []
        footer = info.html_url.replace("https://", "")
        updated = _relative_time(info.created_at)
        extra_line = info.blog

    title_h = _text_h(owner_font) + 8 + len(repo_lines) * (_text_h(title_font) + 6)
    badge_h = 36 if badges else 0
    header_bottom = PAD + title_h + 16 + badge_h
    body_start = max(header_bottom, PAD + AVATAR_SIZE + 24)
    desc_h = len(desc_lines) * (_text_h(desc_font) + 8) if desc_lines else 0
    extra_h = 28 if extra_line else 0
    stats_h = 40
    topic_rows = 0
    if topics:
        row_w = 0
        topic_rows = 1
        for topic in topics:
            tw = _text_w(small_font, topic) + 28
            if row_w and row_w + tw > inner_w - PAD * 2:
                topic_rows += 1
                row_w = 0
            row_w += tw + 8
    topics_h = topic_rows * 38 if topic_rows else 0
    footer_h = 34
    content_h = (
        (body_start - PAD)
        + extra_h
        + (18 if desc_h else 0)
        + desc_h
        + 22
        + stats_h
        + (16 if topics_h else 0)
        + topics_h
        + 20
        + footer_h
    )
    card_h = max(content_h + PAD * 2 + 24, PAD * 2 + AVATAR_SIZE + 48)
    canvas_h = card_h + MARGIN * 2
    canvas = Image.new("RGBA", (CARD_WIDTH, canvas_h), (*theme.canvas, 255))

    shadow = Image.new("RGBA", (CARD_WIDTH, canvas_h), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (MARGIN + 6, MARGIN + 10, CARD_WIDTH - MARGIN + 6, canvas_h - MARGIN + 10),
        radius=RADIUS,
        fill=theme.shadow,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    canvas = Image.alpha_composite(canvas, shadow)

    card = Image.new("RGBA", (inner_w, card_h), (*theme.card, 255))
    card = _round_corners(card, RADIUS)
    border = Image.new("RGBA", (inner_w, card_h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        (1, 1, inner_w - 2, card_h - 2),
        radius=RADIUS,
        outline=theme.border,
        width=2,
    )
    card = Image.alpha_composite(card, border)
    draw = ImageDraw.Draw(card)

    x = PAD
    y = PAD
    draw.text((x, y), owner_line, font=owner_font, fill=theme.muted)
    y += _text_h(owner_font) + 10
    for line in repo_lines:
        draw.text((x, y), line, font=title_font, fill=theme.title)
        y += _text_h(title_font) + 4

    y += 12
    bx = x
    for text, fg, bg, dot in badges:
        used = _draw_badge(draw, bx, y, text, fg, bg, meta_font, dot)
        bx += used + 8
        if bx > text_w + PAD:
            break
    y += badge_h + 8
    y = max(y, PAD + AVATAR_SIZE + 24)

    if extra_line:
        extra_lines = _wrap_text(extra_line, meta_font, inner_w - PAD * 2, 1)
        if extra_lines:
            draw.text((x, y), extra_lines[0], font=meta_font, fill=theme.accent)
            y += extra_h

    if desc_lines:
        y += 6
        for line in desc_lines:
            draw.text((x, y), line, font=desc_font, fill=theme.desc)
            y += _text_h(desc_font) + 8

    y += 14
    sx = x
    for kind, value, label in stats:
        used = _draw_stat(draw, sx, y, kind, value, label, theme, value_font, small_font)
        sx += used

    y += stats_h
    if topics:
        y += 8
        tx = x
        row_y = y
        max_topic_w = inner_w - PAD * 2
        for topic in topics:
            tw = _text_w(small_font, topic) + 24
            if tx != x and tx + tw > x + max_topic_w:
                tx = x
                row_y += 38
            draw.rounded_rectangle((tx, row_y, tx + tw, row_y + 30), radius=15, fill=theme.pill_bg)
            draw.text((tx + 12, row_y + 15), topic, font=small_font, fill=theme.pill_fg, anchor="lm")
            tx += tw + 8
        y = row_y + 38

    y = card_h - PAD - 8
    foot = footer
    if updated:
        foot = f"{footer}  ·  更新于 {updated}" if info.kind == "repo" else f"{footer}  ·  加入于 {updated}"
    draw.text((x, y), foot, font=footer_font, fill=theme.muted, anchor="ld")

    avatar_x = inner_w - PAD - AVATAR_SIZE
    avatar_y = PAD
    ring = Image.new("RGBA", (AVATAR_SIZE + 8, AVATAR_SIZE + 8), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle(
        (0, 0, AVATAR_SIZE + 7, AVATAR_SIZE + 7),
        radius=32,
        outline=theme.border,
        width=3,
    )
    card.alpha_composite(ring, (avatar_x - 4, avatar_y - 4))
    card.alpha_composite(avatar, (avatar_x, avatar_y))

    canvas.alpha_composite(card, (MARGIN, MARGIN))
    return canvas.convert("RGB")


@to_thread
def _draw_github_card_sync(info: GitHubCardInfo, avatar: Image.Image, dark: bool) -> Image.Image:
    return draw_github_card(info, avatar, dark)


def _ai_return_github(info: GitHubCardInfo) -> None:
    try:
        from gsuid_core.ai_core.trigger_bridge import ai_return

        if info.kind == "repo":
            topics = "、".join(info.topics[:8]) if info.topics else "无"
            ai_return(
                f"GitHub 仓库 {info.full_name}\n"
                f"{info.description or '（无简介）'}\n"
                f"Star {info.stars}  Fork {info.forks}  Watch {info.watchers}  "
                f"Issues {info.open_issues}\n"
                f"语言 {info.language or '未知'}  协议 {info.license_name or '无'}  "
                f"分支 {info.default_branch}\n"
                f"主题：{topics}\n"
                f"{info.html_url}"
            )
            return
        ai_return(
            f"GitHub {info.user_type} {info.login}\n"
            f"名称：{info.name}\n"
            f"{info.bio or '（无简介）'}\n"
            f"仓库 {info.public_repos}  关注者 {info.followers}  正在关注 {info.following}\n"
            f"{info.html_url}"
        )
    except Exception as exc:
        logger.warning(f"[MikuSnap] ai_return GitHub 数据提取失败: {exc}")


async def render_github_card(info: GitHubCardInfo) -> bytes:
    _ai_return_github(info)
    dark = cfg_bool("dark_mode", True)
    letter = info.owner if info.kind == "repo" else info.login
    theme = DARK_THEME if dark else LIGHT_THEME
    avatar = await _load_avatar(info.avatar_url, theme, letter)
    image = await _draw_github_card_sync(info, avatar, dark)
    return await convert_img(image)
