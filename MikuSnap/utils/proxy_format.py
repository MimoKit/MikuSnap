from __future__ import annotations

import re
from urllib.parse import urlparse

IP_PORT_RE = re.compile(
    r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3}):(?P<port>\d{2,5})"
    r"(?::(?P<user>[^:\s]+):(?P<password>[^\s]+))?"
)
JSON_IP_RE = re.compile(
    r'"ip"\s*:\s*"(?P<ip>(?:\d{1,3}\.){3}\d{1,3})"\s*,\s*"port"\s*:\s*"?(?P<port>\d{2,5})"?',
    re.IGNORECASE,
)


def parse_proxy_pool_text(text: str, scheme: str = "http") -> str:
    blob = text.strip()
    if not blob:
        return ""
    proto = scheme.lower() if scheme.lower() in {"http", "https", "socks5", "socks5h"} else "http"
    matched = IP_PORT_RE.search(blob)
    if matched is None:
        json_match = JSON_IP_RE.search(blob)
        if json_match is None:
            return ""
        host = json_match.group("ip")
        port = json_match.group("port")
        user = ""
        password = ""
    else:
        host = matched.group("ip")
        port = matched.group("port")
        user = matched.group("user") or ""
        password = matched.group("password") or ""

    octets = [int(part) for part in host.split(".")]
    if any(part > 255 for part in octets):
        return ""
    port_num = int(port)
    if port_num < 1 or port_num > 65535:
        return ""

    if user and password:
        server = f"{proto}://{user}:{password}@{host}:{port_num}"
    else:
        server = f"{proto}://{host}:{port_num}"
    parsed = urlparse(server)
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.netloc:
        return ""
    return server
