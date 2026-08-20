from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Literal, Mapping
from urllib.parse import unquote, urlparse

import httpx
from gsuid_core.logger import logger

from .config import cfg_float, cfg_str
from .github_proxy import github_http_proxy, is_github_fetch_url, resolve_github_url
from .screenshot import redact_text, redact_url

GITHUB_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._-]{0,99}$")
REPO_QUERY_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})"
    r"/(?P<repo>[A-Za-z0-9._][A-Za-z0-9._-]{0,99})$"
)
RESERVED_PATHS = frozenset(
    {
        "about",
        "account",
        "apps",
        "auth",
        "blog",
        "codespaces",
        "collections",
        "contact",
        "copilot",
        "customer-stories",
        "enterprise",
        "events",
        "explore",
        "features",
        "gist",
        "github-copilot",
        "issues",
        "login",
        "logout",
        "marketplace",
        "new",
        "notifications",
        "open-source",
        "organizations",
        "orgs",
        "personal",
        "premium-support",
        "pricing",
        "pulls",
        "readme",
        "resources",
        "search",
        "security",
        "sessions",
        "settings",
        "signup",
        "site",
        "solutions",
        "sponsors",
        "team",
        "topics",
        "trending",
        "watchers",
    }
)

GitHubKind = Literal["repo", "user"]


@dataclass(frozen=True)
class GitHubTarget:
    kind: GitHubKind
    owner: str
    repo: str
    source_url: str


@dataclass(frozen=True)
class GitHubRepoInfo:
    kind: Literal["repo"]
    owner: str
    name: str
    full_name: str
    description: str
    html_url: str
    avatar_url: str
    stars: int
    forks: int
    watchers: int
    open_issues: int
    language: str
    license_name: str
    topics: list[str]
    updated_at: str
    pushed_at: str
    created_at: str
    homepage: str
    archived: bool
    is_fork: bool
    forked_from: str
    default_branch: str
    size_kb: int


@dataclass(frozen=True)
class GitHubUserInfo:
    kind: Literal["user"]
    login: str
    name: str
    bio: str
    html_url: str
    avatar_url: str
    company: str
    location: str
    blog: str
    public_repos: int
    followers: int
    following: int
    created_at: str
    user_type: str


GitHubCardInfo = GitHubRepoInfo | GitHubUserInfo
_JSON_CACHE: dict[str, tuple[float, Mapping[str, object]]] = {}


def _as_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, dict) else None


def _as_str(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _as_bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _as_str(item)
        if text and text not in seen:
            items.append(text)
            seen.add(text)
    return items


def _mapping_str(data: Mapping[str, object], key: str) -> str:
    return _as_str(data[key]) if key in data else ""


def _mapping_int(data: Mapping[str, object], key: str) -> int:
    return _as_int(data[key]) if key in data else 0


def _mapping_bool(data: Mapping[str, object], key: str) -> bool:
    return _as_bool(data[key]) if key in data else False


def _clean_owner(owner: str) -> str:
    text = owner.strip()
    return text if GITHUB_OWNER_RE.fullmatch(text) else ""


def _clean_repo(repo: str) -> str:
    text = repo.strip().removesuffix(".git")
    if text in {".", ".."}:
        return ""
    return text if GITHUB_REPO_RE.fullmatch(text) else ""


def parse_github_target(url: str) -> GitHubTarget | None:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host not in {"github.com", "www.github.com"}:
        return None

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if not parts:
        return None

    owner = _clean_owner(parts[0])
    if not owner or owner.lower() in RESERVED_PATHS:
        return None

    if len(parts) == 1:
        return GitHubTarget(kind="user", owner=owner, repo="", source_url=url)

    repo = _clean_repo(parts[1])
    if not repo or repo.lower() in RESERVED_PATHS:
        return None
    return GitHubTarget(kind="repo", owner=owner, repo=repo, source_url=url)


def parse_github_query(text: str) -> GitHubTarget | None:
    raw = text.strip().strip("`\"'")
    if not raw:
        return None

    from .screenshot import extract_urls

    for url in extract_urls(raw):
        target = parse_github_target(url)
        if target is not None:
            return target

    cleaned = re.sub(r"^https?://(?:www\.)?github\.com/", "", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:www\.)?github\.com/", "", cleaned, flags=re.IGNORECASE)
    matched = REPO_QUERY_RE.fullmatch(cleaned)
    if matched is None:
        owner = _clean_owner(raw)
        if owner and owner.lower() not in RESERVED_PATHS:
            return GitHubTarget(
                kind="user",
                owner=owner,
                repo="",
                source_url=f"https://github.com/{owner}",
            )
        return None

    owner = _clean_owner(matched.group("owner"))
    repo = _clean_repo(matched.group("repo"))
    if not owner or not repo:
        return None
    return GitHubTarget(
        kind="repo",
        owner=owner,
        repo=repo,
        source_url=f"https://github.com/{owner}/{repo}",
    )


def _read_cache(key: str, ttl: float) -> Mapping[str, object] | None:
    if ttl <= 0 or key not in _JSON_CACHE:
        return None
    ts, data = _JSON_CACHE[key]
    if time.time() - ts > ttl:
        del _JSON_CACHE[key]
        return None
    return data


def _write_cache(key: str, data: Mapping[str, object]) -> None:
    _JSON_CACHE[key] = (time.time(), data)


def _request_headers(json_api: bool) -> dict[str, str]:
    headers = {
        "User-Agent": "MikuSnap-GitHubCard",
    }
    if json_api:
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    else:
        headers["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
    token = cfg_str("github_token", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def github_get(url: str, json_api: bool = True) -> httpx.Response | None:
    if not is_github_fetch_url(url):
        return None

    timeout = cfg_float("github_timeout", 15.0, 3.0, 60.0)
    final_url = resolve_github_url(url)
    http_proxy = github_http_proxy()
    logger.info(
        "[MikuSnap] GitHub 请求："
        f"url={redact_url(url)} via={redact_url(final_url)} "
        f"http_proxy={'on' if http_proxy else 'off'}"
    )
    headers = _request_headers(json_api)
    try:
        if http_proxy:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers=headers,
                proxy=http_proxy,
            ) as client:
                return await client.get(final_url)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            return await client.get(final_url)
    except (httpx.HTTPError, OSError, ImportError, RuntimeError) as exc:
        logger.info(
            "[MikuSnap] GitHub 请求失败："
            f"url={redact_url(url)} error={redact_text(str(exc))}"
        )
        return None


async def github_get_json(url: str) -> Mapping[str, object] | None:
    cache_key = url
    ttl = cfg_float("github_cache_ttl", 600.0, 0.0, 86400.0)
    cached = _read_cache(cache_key, ttl)
    if cached is not None:
        return cached

    response = await github_get(url)
    if response is None:
        return None
    if response.status_code != 200:
        logger.info(
            "[MikuSnap] GitHub API 非 200："
            f"url={redact_url(url)} status={response.status_code} "
            f"body={redact_text(response.text)}"
        )
        return None

    try:
        payload = response.json()
    except ValueError:
        logger.info(f"[MikuSnap] GitHub API 返回非 JSON：url={redact_url(url)}")
        return None
    mapping = _as_mapping(payload)
    if mapping is None:
        return None
    if ttl > 0:
        _write_cache(cache_key, mapping)
    return mapping


async def github_get_bytes(url: str) -> bytes | None:
    response = await github_get(url, json_api=False)
    if response is None or response.status_code != 200:
        return None
    content = response.content
    return content if content else None


def _parse_repo(data: Mapping[str, object], source_url: str) -> GitHubRepoInfo | None:
    owner_map = _as_mapping(data["owner"]) if "owner" in data else None
    license_map = _as_mapping(data["license"]) if "license" in data else None
    parent_map = _as_mapping(data["parent"]) if "parent" in data else None

    owner = _mapping_str(owner_map, "login") if owner_map is not None else ""
    name = _mapping_str(data, "name")
    full_name = _mapping_str(data, "full_name") or (f"{owner}/{name}" if owner and name else "")
    html_url = _mapping_str(data, "html_url") or source_url
    if not owner or not name or not full_name:
        return None

    avatar = _mapping_str(owner_map, "avatar_url") if owner_map is not None else ""
    license_name = ""
    if license_map is not None:
        license_name = _mapping_str(license_map, "spdx_id") or _mapping_str(license_map, "name")
        if license_name == "NOASSERTION":
            license_name = ""

    topics = _as_str_list(data["topics"]) if "topics" in data else []
    forked_from = _mapping_str(parent_map, "full_name") if parent_map is not None else ""

    return GitHubRepoInfo(
        kind="repo",
        owner=owner,
        name=name,
        full_name=full_name,
        description=_mapping_str(data, "description"),
        html_url=html_url,
        avatar_url=avatar,
        stars=_mapping_int(data, "stargazers_count"),
        forks=_mapping_int(data, "forks_count"),
        watchers=_mapping_int(data, "subscribers_count"),
        open_issues=_mapping_int(data, "open_issues_count"),
        language=_mapping_str(data, "language"),
        license_name=license_name,
        topics=topics[:12],
        updated_at=_mapping_str(data, "updated_at"),
        pushed_at=_mapping_str(data, "pushed_at"),
        created_at=_mapping_str(data, "created_at"),
        homepage=_mapping_str(data, "homepage"),
        archived=_mapping_bool(data, "archived"),
        is_fork=_mapping_bool(data, "fork"),
        forked_from=forked_from,
        default_branch=_mapping_str(data, "default_branch") or "main",
        size_kb=_mapping_int(data, "size"),
    )


def _parse_user(data: Mapping[str, object], source_url: str) -> GitHubUserInfo | None:
    login = _mapping_str(data, "login")
    html_url = _mapping_str(data, "html_url") or source_url
    if not login:
        return None
    return GitHubUserInfo(
        kind="user",
        login=login,
        name=_mapping_str(data, "name") or login,
        bio=_mapping_str(data, "bio"),
        html_url=html_url,
        avatar_url=_mapping_str(data, "avatar_url"),
        company=_mapping_str(data, "company"),
        location=_mapping_str(data, "location"),
        blog=_mapping_str(data, "blog"),
        public_repos=_mapping_int(data, "public_repos"),
        followers=_mapping_int(data, "followers"),
        following=_mapping_int(data, "following"),
        created_at=_mapping_str(data, "created_at"),
        user_type=_mapping_str(data, "type") or "User",
    )


async def fetch_github_card(target: GitHubTarget) -> GitHubCardInfo | None:
    if target.kind == "repo":
        data = await github_get_json(f"https://api.github.com/repos/{target.owner}/{target.repo}")
        if data is None:
            return None
        return _parse_repo(data, target.source_url)

    data = await github_get_json(f"https://api.github.com/users/{target.owner}")
    if data is None:
        return None
    return _parse_user(data, target.source_url)
