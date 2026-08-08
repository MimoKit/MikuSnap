from __future__ import annotations

from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsDivider,
    GsFloatConfig,
    GsIntConfig,
    GsListStrConfig,
    GsStrConfig,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    "_DividerBasic": GsDivider("基础设置", ""),
    "enabled": GsBoolConfig(
        "启用 MikuSnap",
        "关闭后手动命令和自动解析都不再执行。",
        True,
    ),
    "auto_enable": GsBoolConfig(
        "自动解析网页链接",
        "开启后监听聊天中的 http/https 链接并自动截图。",
        True,
    ),
    "max_urls_per_message": GsIntConfig(
        "单条消息最多处理链接数",
        "避免一条消息包含大量链接导致刷屏。",
        2,
    ),
    "max_concurrency": GsIntConfig(
        "最大并发截图数",
        "同时运行的 Playwright 截图任务数量。",
        1,
    ),
    "send_skip_reason": GsBoolConfig(
        "发送跳过/失败原因",
        "自动解析时如果链接被跳过或截图失败，是否发送脱敏后的原因。",
        True,
    ),
    "skip_reason_template": GsStrConfig(
        "跳过原因模板",
        "可用 {reason}、{url}、{host}、{suffix}。",
        "网页截图已跳过：{reason}\n链接：{url}",
    ),
    "_DividerSend": GsDivider("发送样式", ""),
    "forward_enable": GsBoolConfig(
        "长网页合并转发",
        "多张分图时使用 MessageSegment.node 合并转发；部分平台可能不支持。",
        True,
    ),
    "ai_name": GsStrConfig(
        "解析显示名",
        "用于标题模板。",
        "解析",
    ),
    "forward_node_name": GsStrConfig(
        "合并转发节点昵称",
        "预留配置；GsCore 当前主要使用 node 内容发送。",
        "解析",
    ),
    "forward_title_template": GsStrConfig(
        "外层标题模板",
        "可用 {ai_name}、{title}、{url}、{page_count}、{bot_name}。",
        "{ai_name} | 网页 {title}",
    ),
    "first_node_template": GsStrConfig(
        "第一条文字模板",
        "可用 {ai_name}、{title}、{url}、{page_count}、{bot_name}。",
        "{ai_name} | 网页\n{title}",
    ),
    "_DividerCapture": GsDivider("截图参数", ""),
    "dark_mode": GsBoolConfig(
        "深色模式",
        "开启后浏览器以 prefers-color-scheme: dark 渲染网页，支持深色模式的网站会自动切换。",
        True,
    ),
    "split_long_page": GsBoolConfig(
        "长网页分图",
        "开启后先截整页，再用 Pillow 本地切成多张。",
        True,
    ),
    "segment_height": GsIntConfig(
        "每张分图高度",
        "建议接近浏览器视口高度。",
        900,
    ),
    "segment_overlap": GsIntConfig(
        "分图重叠高度",
        "避免内容刚好卡在切图边界。",
        80,
    ),
    "max_segments": GsIntConfig(
        "单网页最多分图数",
        "防止超长网页刷屏。",
        8,
    ),
    "viewport_width": GsIntConfig(
        "浏览器视口宽度",
        "Chromium 页面宽度。",
        1365,
    ),
    "viewport_height": GsIntConfig(
        "浏览器视口高度",
        "Chromium 页面高度。",
        900,
    ),
    "load_timeout": GsFloatConfig(
        "网页加载超时秒数",
        "等待 networkidle/domcontentloaded 的超时时间。",
        30.0,
    ),
    "screenshot_timeout": GsFloatConfig(
        "截图超时秒数",
        "Playwright screenshot 超时时间。",
        30.0,
    ),
    "head_timeout": GsFloatConfig(
        "直链检测超时秒数",
        "HEAD/Range 请求检测 Content-Type 的超时时间。",
        8.0,
    ),
    "settle_delay": GsFloatConfig(
        "页面稳定等待秒数",
        "页面加载完成后额外等待动态内容稳定。",
        1.5,
    ),
    "_DividerFilter": GsDivider("过滤规则", ""),
    "block_private_hosts": GsBoolConfig(
        "跳过内网/本机地址",
        "跳过 localhost、内网、保留地址等链接。",
        True,
    ),
    "extra_video_hosts": GsListStrConfig(
        "额外视频站域名",
        "一行一个域名，自动解析时会跳过。",
        [],
    ),
    "user_agent": GsStrConfig(
        "User-Agent",
        "留空使用默认桌面浏览器 UA。",
        "",
    ),
    "_DividerDebug": GsDivider("日志", ""),
    "debug_skip_log": GsBoolConfig(
        "记录跳过日志",
        "在控制台记录被跳过链接的脱敏摘要。",
        True,
    ),
    "debug_success_log": GsBoolConfig(
        "记录成功日志",
        "在控制台记录截图成功摘要。",
        True,
    ),
    "debug_detail_log": GsBoolConfig(
        "详细调试日志",
        "记录直链检测、页面尺寸、分图位置等信息。",
        False,
    ),
}
