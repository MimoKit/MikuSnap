from __future__ import annotations

import unittest
from pathlib import Path
from sys import path

path.insert(0, str(Path(__file__).parents[1] / "MikuSnap" / "utils"))

from proxy_format import parse_proxy_pool_text  # noqa: E402


class ProxyPoolParseTest(unittest.TestCase):
    def test_plain_ip_port(self) -> None:
        self.assertEqual(
            parse_proxy_pool_text("115.213.253.250:15001"),
            "http://115.213.253.250:15001",
        )

    def test_ip_port_with_auth(self) -> None:
        self.assertEqual(
            parse_proxy_pool_text("10.0.0.8:8000:alice:secret", "http"),
            "http://alice:secret@10.0.0.8:8000",
        )

    def test_json_payload(self) -> None:
        self.assertEqual(
            parse_proxy_pool_text('{"ip":"8.8.8.8","port":8080}'),
            "http://8.8.8.8:8080",
        )

    def test_socks_scheme(self) -> None:
        self.assertEqual(
            parse_proxy_pool_text("1.2.3.4:1080", "socks5"),
            "socks5://1.2.3.4:1080",
        )

    def test_error_text_without_ip(self) -> None:
        self.assertEqual(parse_proxy_pool_text("错误：余额不足"), "")
        self.assertEqual(parse_proxy_pool_text(""), "")


if __name__ == "__main__":
    unittest.main()
