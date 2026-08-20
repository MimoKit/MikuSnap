from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from .config import cfg_str

GITHUB_WEB_HOSTS = frozenset(
    {
        "github.com",
        "www.github.com",
        "gist.github.com",
        "api.github.com",
    }
)
GITHUB_ASSET_SUFFIXES = (
    "githubusercontent.com",
    "githubassets.com",
)
PREFIX_PROXY_MARKERS = (
    "gh-proxy",
    "ghproxy",
    "gh.llkk",
    "gitclone",
    "moeyy",
    "mirror.gh",
)


def _hostname(url: str) -> str:
    host = urlparse(url).hostname
    return host.lower() if isinstance(host, str) else ""


def is_github_fetch_url(url: str) -> bool:
    """是否为 GitHub 网页 / API / 静态资源，需要走代理解析。"""
    host = _hostname(url)
    if not host:
        return False
    if host in GITHUB_WEB_HOSTS:
        return True
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in GITHUB_ASSET_SUFFIXES)


def normalize_web_proxy(raw: str) -> str:
    text = raw.strip().rstrip("/")
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if any(ch.isspace() for ch in text) or "@" in text or "#" in text:
        return ""
    return text


def _is_prefix_proxy(proxy: str) -> bool:
    host = _hostname(proxy)
    blob = f"{host} {proxy.lower()}"
    return any(marker in blob for marker in PREFIX_PROXY_MARKERS)


def _replace_github_host(host: str, proxy_host: str) -> str:
    if host in {"github.com", "www.github.com"}:
        return proxy_host
    if host == "api.github.com":
        return proxy_host if proxy_host.startswith("api.") else f"api.{proxy_host}"
    if host == "gist.github.com":
        return proxy_host if proxy_host.startswith("gist.") else f"gist.{proxy_host}"
    if host == "raw.githubusercontent.com":
        return f"raw.{proxy_host}"
    if host == "avatars.githubusercontent.com":
        return f"avatars.{proxy_host}"
    if host.endswith(".githubusercontent.com"):
        prefix = host[: -len(".githubusercontent.com")]
        return f"{prefix}.{proxy_host}"
    if host.endswith(".githubassets.com"):
        prefix = host[: -len(".githubassets.com")]
        return f"{prefix}.{proxy_host}" if prefix else proxy_host
    return host


def apply_github_web_proxy(url: str, proxy: str) -> str:
    """把 GitHub URL 改写成网页加速地址。

    - gh-proxy 风格：`https://gh-proxy.com` + `/` + 原始 URL
    - 镜像站风格：把 `github.com` 等主机名替换成镜像域名（如 kkgithub.com）
    """
    prefix = normalize_web_proxy(proxy)
    if not prefix or not is_github_fetch_url(url):
        return url

    if _is_prefix_proxy(prefix):
        return f"{prefix}/{url}"

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    proxy_host = _hostname(prefix)
    if not host or not proxy_host:
        return f"{prefix}/{url}"

    new_host = _replace_github_host(host, proxy_host)
    userinfo = parsed.netloc.rsplit("@", 1)[0] + "@" if "@" in parsed.netloc else ""
    port = f":{parsed.port}" if parsed.port else ""
    scheme = urlparse(prefix).scheme or parsed.scheme
    return urlunparse(
        (
            scheme,
            f"{userinfo}{new_host}{port}",
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def github_http_proxy() -> str:
    text = cfg_str("github_http_proxy", "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.netloc:
        return ""
    return text


def github_web_proxy() -> str:
    return normalize_web_proxy(cfg_str("github_web_proxy", ""))


def resolve_github_url(url: str) -> str:
    """GitHub 链接最终请求地址：网页代理改写后的 URL。"""
    return apply_github_web_proxy(url, github_web_proxy())
