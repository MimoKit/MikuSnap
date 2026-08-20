from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlparse

# 国内外常见查 IP / 泄漏检测站。自定义站点靠 URL 特征 + 打开后的页面内容识别。
BUILTIN_IP_CHECK_HOSTS: frozenset[str] = frozenset(
    {
        "ip138.com",
        "cip.cc",
        "ip.cn",
        "ipw.cn",
        "ipip.net",
        "ip.sb",
        "ip.skk.moe",
        "ip.im",
        "myip.la",
        "ipchaxun.com",
        "chaipip.com",
        "ipplus360.com",
        "ip.chinaz.com",
        "ip.tool.chinaz.com",
        "ip.qq.com",
        "ip.hao123.com",
        "ip.360.cn",
        "ip.tool.lu",
        "ip.zxinc.org",
        "ip.lddgo.net",
        "ip.yqie.com",
        "ip.bczs.net",
        "ip.nange.cn",
        "ip.p3terx.com",
        "ip.3322.net",
        "whoer.net",
        "ipinfo.io",
        "ipify.org",
        "api.ipify.org",
        "ip-api.com",
        "ipapi.co",
        "ipapi.com",
        "ipwho.is",
        "ipwhois.app",
        "ipwhois.io",
        "whatismyip.com",
        "whatismyipaddress.com",
        "whatsmyip.org",
        "whatsmyip.com",
        "icanhazip.com",
        "ifconfig.me",
        "ifconfig.co",
        "ifconfig.io",
        "ident.me",
        "ipecho.net",
        "ipleak.net",
        "dnsleaktest.com",
        "browserleaks.com",
        "wtfismyip.com",
        "checkip.amazonaws.com",
        "jsonip.com",
        "seeip.org",
        "myexternalip.com",
        "ipchicken.com",
        "iplocation.net",
        "ipvoid.com",
        "db-ip.com",
        "ip2location.com",
        "ipgeolocation.io",
        "ipdata.co",
        "trackip.net",
        "curlmyip.net",
        "showmyip.com",
        "findmyip.org",
        "getmyip.com",
        "myip.com",
        "myip.ms",
        "ip.42.pl",
        "l2.io",
    }
)

IP_HOST_LABELS: frozenset[str] = frozenset(
    {
        "ip",
        "ipv4",
        "ipv6",
        "myip",
        "ipinfo",
        "ipcheck",
        "checkip",
        "whatismyip",
        "whatsmyip",
        "icanhazip",
        "ifconfig",
        "iplookup",
        "ipquery",
        "showip",
        "getip",
        "ipecho",
        "ipify",
        "ipapi",
        "ipleak",
        "ipwhois",
        "ipwho",
        "ipdata",
        "ip138",
        "ipchaxun",
        "cip",
    }
)

IP_HOST_TOKENS: tuple[str, ...] = (
    "whatismyip",
    "whatsmyip",
    "icanhazip",
    "ifconfig",
    "ident.me",
    "iplocation",
    "ipchicken",
    "ipleak",
    "dnsleak",
    "browserleaks",
    "myexternalip",
    "curlmyip",
    "jsonip",
    "wtfismyip",
    "ipify",
    "ip-api",
    "ipapi.",
    "ipinfo",
    "whoer.net",
    "cip.cc",
    "ip138",
    "ipchaxun",
    "ipw.cn",
    "ipip.net",
)

IP_CHECK_PATHS: frozenset[str] = frozenset(
    {
        "/ip",
        "/ip.json",
        "/ip.txt",
        "/myip",
        "/my-ip",
        "/what-is-my-ip",
        "/whats-my-ip",
        "/cdn-cgi/trace",
        "/getip",
        "/get-ip",
        "/showip",
        "/checkip",
        "/ipchaxun",
    }
)

IP_PAGE_KEYWORDS: tuple[str, ...] = (
    "your ip",
    "what is my ip",
    "whats my ip",
    "what's my ip",
    "show my ip",
    "visitor ip",
    "my public ip",
    "我的ip",
    "您的ip",
    "你的ip",
    "本机ip",
    "公网ip",
    "出口ip",
    "ip查询",
    "ip地址查询",
    "查询ip",
    "ip address lookup",
)

IP_LEAK_SCOLD = (
    "发查 IP 网站想套机器人服务器地址是吧？当我傻呢。\n"
    "这种站一律不截，再发就当你脑子进水。\n"
    "链接：{url}"
)


@dataclass(frozen=True)
class IpCheckHit:
    detail: str


class IpCheckPageError(RuntimeError):
    def __init__(self, hit: IpCheckHit) -> None:
        super().__init__(hit.detail)
        self.hit = hit


def _hostname(url: str) -> str:
    host = urlparse(url.strip()).hostname
    if not isinstance(host, str):
        return ""
    return host.lower().removeprefix("www.")


def normalize_block_host(raw: str) -> str:
    text = raw.strip().lower()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    host = urlparse(text).hostname
    if not isinstance(host, str):
        return ""
    return host.lower().removeprefix("www.")


def host_matches(host: str, domains: list[str] | frozenset[str]) -> str:
    if not host:
        return ""
    needle = host.lower().removeprefix("www.")
    for domain in domains:
        cleaned = domain.lower().removeprefix("www.")
        if not cleaned:
            continue
        if needle == cleaned or needle.endswith(f".{cleaned}"):
            return cleaned
    return ""


def match_block_hosts(url: str, raw_hosts: list[str]) -> str:
    host = _hostname(url)
    cleaned = [normalize_block_host(item) for item in raw_hosts]
    return host_matches(host, [item for item in cleaned if item])


def _path_key(url: str) -> str:
    path = unquote(urlparse(url).path).lower().rstrip("/")
    return path if path else "/"


def detect_ip_check_url(url: str) -> IpCheckHit | None:
    """只看网址，不发请求。自定义站点若域名/路径很隐蔽，要靠打开后再识别。"""
    host = _hostname(url)
    if not host:
        return None

    builtin = host_matches(host, BUILTIN_IP_CHECK_HOSTS)
    if builtin:
        return IpCheckHit(detail=f"builtin_host={builtin}")

    labels = [part for part in host.split(".") if part]
    for label in labels:
        if label in IP_HOST_LABELS:
            return IpCheckHit(detail=f"host_label={label}")

    for token in IP_HOST_TOKENS:
        if token in host:
            return IpCheckHit(detail=f"host_token={token}")

    path = _path_key(url)
    if path in IP_CHECK_PATHS or path.startswith("/cdn-cgi/trace"):
        return IpCheckHit(detail=f"path={path}")
    return None


def _has_ip_keyword(blob: str) -> bool:
    return any(keyword in blob for keyword in IP_PAGE_KEYWORDS)


def detect_ip_check_page(title: str, text: str) -> IpCheckHit | None:
    """打开页面后看标题/正文：有人自己搭的查 IP 站也能拦，避免把图发进群。"""
    title_l = title.strip().lower()
    text_l = text.strip().lower()
    blob = f"{title_l}\n{text_l}"
    compact = "".join(text_l.split())

    if _has_ip_keyword(title_l):
        return IpCheckHit(detail="page_title_keyword")
    if _has_ip_keyword(blob):
        return IpCheckHit(detail="page_body_keyword")

    ipv4_only = _looks_like_plain_ip(compact)
    if ipv4_only:
        return IpCheckHit(detail="page_plain_ip")
    return None


def _looks_like_plain_ip(compact: str) -> bool:
    if not compact:
        return False
    if compact.count(".") == 3:
        parts = compact.split(".")
        if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
            return True
    if compact.count(":") >= 2 and all(ch in "0123456789abcdef:" for ch in compact):
        return True
    return False


def build_ip_leak_scold(url: str) -> str:
    return IP_LEAK_SCOLD.format(url=url)
