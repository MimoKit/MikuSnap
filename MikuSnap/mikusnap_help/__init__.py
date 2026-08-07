from __future__ import annotations

from PIL import Image

from gsuid_core.bot import Bot
from gsuid_core.help.utils import register_help
from gsuid_core.models import Event
from gsuid_core.sv import SV, get_plugin_available_prefix

from .get_help import ICON, get_help

sv_help = SV("MikuSnap 帮助", pm=6, area="ALL")


@sv_help.on_command(("网页截图帮助", "截图帮助"), block=True)
async def send_help_img(bot: Bot, ev: Event):
    await bot.send(await get_help())


register_help(
    "MikuSnap",
    f"{get_plugin_available_prefix('MikuSnap')}帮助",
    Image.open(ICON),
)
