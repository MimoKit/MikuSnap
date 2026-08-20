from __future__ import annotations

import unittest
from pathlib import Path
from sys import path

path.insert(0, str(Path(__file__).parents[1] / "MikuSnap" / "utils"))

from ip_guard import (  # noqa: E402
    detect_ip_check_page,
    detect_ip_check_url,
    match_block_hosts,
)


class IpCheckUrlTest(unittest.TestCase):
    def test_known_hosts_are_blocked(self) -> None:
        self.assertIsNotNone(detect_ip_check_url("https://ipinfo.io"))
        self.assertIsNotNone(detect_ip_check_url("https://www.ip138.com/"))
        self.assertIsNotNone(detect_ip_check_url("https://cip.cc"))
        self.assertIsNotNone(detect_ip_check_url("https://ifconfig.me"))
        self.assertIsNotNone(detect_ip_check_url("https://ip.qq.com"))

    def test_path_based_ip_endpoints_are_blocked(self) -> None:
        self.assertIsNotNone(detect_ip_check_url("https://httpbin.org/ip"))
        self.assertIsNotNone(detect_ip_check_url("https://cloudflare.com/cdn-cgi/trace"))

    def test_normal_sites_are_allowed(self) -> None:
        self.assertIsNone(detect_ip_check_url("https://github.com/Genshin-bots/gsuid_core"))
        self.assertIsNone(detect_ip_check_url("https://example.com/blog"))
        self.assertIsNone(detect_ip_check_url("https://wikipedia.org/wiki/IP_address"))
        self.assertIsNone(detect_ip_check_url("https://httpbin.org/get"))

    def test_host_label_heuristic(self) -> None:
        self.assertIsNotNone(detect_ip_check_url("https://myip.example.net"))
        self.assertIsNotNone(detect_ip_check_url("https://ipv4.evil.dev"))


class IpCheckPageTest(unittest.TestCase):
    def test_custom_ip_page_by_title(self) -> None:
        hit = detect_ip_check_page("你的IP地址", "欢迎")
        self.assertIsNotNone(hit)

    def test_plain_ip_body(self) -> None:
        hit = detect_ip_check_page("", "1.2.3.4")
        self.assertIsNotNone(hit)

    def test_normal_article_is_allowed(self) -> None:
        hit = detect_ip_check_page("Python 教程", "如何配置网络和 DNS。")
        self.assertIsNone(hit)


class ExtraBlockHostTest(unittest.TestCase):
    def test_console_block_list(self) -> None:
        self.assertEqual(
            match_block_hosts("https://foo.evil.test/a", ["evil.test"]),
            "evil.test",
        )
        self.assertEqual(match_block_hosts("https://example.com", ["evil.test"]), "")


if __name__ == "__main__":
    unittest.main()
