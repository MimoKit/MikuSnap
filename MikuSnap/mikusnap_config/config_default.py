from __future__ import annotations

from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsBoolConfig,
    GsDivider,
    GsFloatConfig,
    GsListStrConfig,
    GsStrConfig,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    "dark_mode": GsBoolConfig(
        "深色模式",
        "开启后网页截图以 prefers-color-scheme: dark 渲染，GitHub 信息卡片同步使用深色主题。",
        True,
    ),
    "_DividerGithub": GsDivider("GitHub 解析", ""),
    "github_card_enable": GsBoolConfig(
        "解析 GitHub 为信息卡片",
        "遇到 github.com 仓库/用户链接时，不再整页截图，改为绘制仓库信息卡片（Star、Fork、语言、主题等）。",
        True,
    ),
    "github_web_proxy": GsStrConfig(
        "GitHub 网页代理",
        "遇到 GitHub 链接时用该加速地址去解析。支持 gh-proxy 前缀（如 https://gh-proxy.com）或镜像站（如 https://kkgithub.com）。留空则直连。",
        "",
        options=[
            "https://gh-proxy.com",
            "https://hk.gh-proxy.com",
            "https://edgeone.gh-proxy.com",
            "https://gh.llkk.cc",
            "https://kkgithub.com",
        ],
    ),
    "github_http_proxy": GsStrConfig(
        "GitHub HTTP/SOCKS 代理（VPN）",
        "本地 Clash / VPN 代理，仅用于 GitHub 网页、API 与头像。例如 http://127.0.0.1:7890 或 socks5://127.0.0.1:7890。留空则不走本地代理。",
        "",
    ),
    "github_token": GsStrConfig(
        "GitHub Token（可选）",
        "填写后提高 API 限额，避免匿名请求被限流。只需 repo 公开信息，可不授权私有仓库。",
        "",
        secret=True,
    ),
    "github_timeout": GsFloatConfig(
        "GitHub 请求超时秒数",
        "拉取仓库 API / 头像的超时时间。",
        15.0,
        min_value=3.0,
        max_value=60.0,
    ),
    "github_cache_ttl": GsFloatConfig(
        "GitHub 结果缓存秒数",
        "同一仓库在缓存期内不重复请求 API。0 表示不缓存。",
        600.0,
        min_value=0.0,
        max_value=86400.0,
    ),
    "_DividerFilter": GsDivider("过滤规则", ""),
    "block_hosts": GsListStrConfig(
        "额外屏蔽网站",
        "一行一个域名或完整链接。自动/手动截图都会跳过。内置已覆盖常见国内外查 IP 站。",
        [],
    ),
    "screenshot_http_proxy": GsStrConfig(
        "截图出口代理（伪装 IP）",
        "固定 HTTP/SOCKS 代理，代理池提取失败时作为兜底。例如 http://127.0.0.1:7890。",
        "",
    ),
    "proxy_pool_api": GsStrConfig(
        "IP 代理池提取 API",
        "每次截图前请求该地址，解析返回的 ip:port，用代理池 IP 访问网页。密钥写在 URL 参数里。稻米/蚂蚁示例：http://host:7771/dmgetip.asp?apikey=***&pwd=***&getnum=1&httptype=1&geshi=1&operate=all",
        "",
        secret=True,
    ),
    "proxy_pool_scheme": GsStrConfig(
        "代理池协议",
        "把提取到的 ip:port 拼成 Playwright 代理。httptype=1 选 http，SOCKS 选 socks5。",
        "http",
        options=["http", "https", "socks5"],
    ),
}
