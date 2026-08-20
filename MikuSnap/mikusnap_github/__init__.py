from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.config import cfg_bool
from ..utils.github_api import GitHubTarget, fetch_github_card, parse_github_query, parse_github_target
from ..utils.screenshot import redact_text, redact_url
from .draw_card import render_github_card

github_sv = SV("MikuSnap GitHub解析", priority=4, area="ALL")


async def send_github_card(bot: Bot, target: GitHubTarget) -> bool:
    info = await fetch_github_card(target)
    if info is None:
        logger.info(
            "[MikuSnap] GitHub 卡片解析失败："
            f"url={redact_url(target.source_url)} owner={target.owner} repo={target.repo}"
        )
        return False
    image = await render_github_card(info)
    await bot.send(image)
    logger.info(
        "[MikuSnap] GitHub 卡片已发送："
        f"url={redact_url(target.source_url)} kind={info.kind}"
    )
    return True


async def try_handle_github_url(bot: Bot, url: str) -> bool:
    if not cfg_bool("github_card_enable", True):
        return False
    target = parse_github_target(url)
    if target is None:
        return False
    return await send_github_card(bot, target)


@github_sv.on_command(
    ("仓库卡片", "github", "GitHub", "github卡片"),
    block=True,
    prefix=False,
    to_ai="""解析 GitHub 仓库或用户主页，生成信息卡片图片。
当用户发送 GitHub 链接、询问某个 GitHub 仓库的 Star/简介/语言，或说「帮我看看这个仓库」时调用。

Args:
    text: GitHub 仓库链接、用户主页链接，或 owner/repo。
          例如 "https://github.com/KroMiose/nekro-agent"
          例如 "KroMiose/nekro-agent"
          例如 "https://github.com/KroMiose"
""",
)
async def github_card_command(bot: Bot, ev: Event) -> None:
    text = ev.text.strip() if isinstance(ev.text, str) else ""
    if not text:
        await bot.send("请发送 GitHub 链接或 owner/repo，例如：仓库卡片 KroMiose/nekro-agent")
        return

    target = parse_github_query(text)
    if target is None:
        logger.info(f"[MikuSnap] GitHub 命令参数无效：text={redact_text(text)}")
        await bot.send("没认出 GitHub 仓库或用户，请发送完整链接或 owner/repo")
        return

    logger.info(f"[MikuSnap] 手动 GitHub 解析：url={redact_url(target.source_url)}")
    ok = await send_github_card(bot, target)
    if not ok:
        await bot.send("GitHub 解析失败，请检查代理配置或稍后重试")
