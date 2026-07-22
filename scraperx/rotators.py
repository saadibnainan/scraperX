"""Proxy and User-Agent rotation.

Both rotators are round-robin and thread-safe enough for the sequential engine.
`ProxyRotator.next()` yields a Playwright-shaped proxy dict (or ``None``);
`UserAgentRotator.next()` yields a UA string.
"""

from __future__ import annotations

import itertools
import threading
from typing import Dict, List, Optional
from urllib.parse import urlparse

# A small, modern desktop UA pool used when the user supplies none and
# fake-useragent is unavailable.
_BUILTIN_USER_AGENTS: List[str] = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15",
]


def _parse_proxy(raw: str, username: str = "", password: str = "") -> Optional[Dict[str, str]]:
    """Turn a proxy URL (optionally with embedded creds) into a Playwright dict.

    Playwright wants ``{"server": "scheme://host:port", "username": ..., "password": ...}``
    with credentials kept out of the server field.
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    # urlparse needs a scheme to populate hostname/port correctly.
    if "://" not in raw:
        raw = "http://" + raw

    parsed = urlparse(raw)
    if not parsed.hostname:
        return None

    if parsed.port:
        server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    else:
        server = f"{parsed.scheme}://{parsed.hostname}"

    proxy: Dict[str, str] = {"server": server}
    user = username or parsed.username
    pw = password or parsed.password
    if user:
        proxy["username"] = user
    if pw:
        proxy["password"] = pw
    return proxy


class ProxyRotator:
    """Round-robin over a proxy pool. Yields Playwright proxy dicts or None."""

    def __init__(self, proxies: Optional[List[Dict[str, str]]] = None):
        self._proxies = proxies or []
        self._lock = threading.Lock()
        self._cycle = itertools.cycle(self._proxies) if self._proxies else None

    @classmethod
    def from_config(cls, config) -> "ProxyRotator":
        proxies: List[Dict[str, str]] = []
        if config.proxy_list:
            for entry in config.proxy_list:
                p = _parse_proxy(entry)
                if p:
                    proxies.append(p)
        elif config.proxy_url:
            p = _parse_proxy(config.proxy_url, config.proxy_username, config.proxy_password)
            if p:
                proxies.append(p)
        return cls(proxies)

    @property
    def enabled(self) -> bool:
        return bool(self._proxies)

    def next(self) -> Optional[Dict[str, str]]:
        if not self._cycle:
            return None
        with self._lock:
            return next(self._cycle)


class UserAgentRotator:
    """Round-robin over a User-Agent pool.

    Priority: user-supplied list → fake-useragent (if importable) → built-in list.
    """

    def __init__(self, user_agents: Optional[List[str]] = None):
        self._agents = [ua for ua in (user_agents or []) if ua] or list(_BUILTIN_USER_AGENTS)
        self._lock = threading.Lock()
        self._cycle = itertools.cycle(self._agents)

    @classmethod
    def from_config(cls, config) -> "UserAgentRotator":
        if config.user_agents:
            return cls(config.user_agents)

        # Try fake-useragent for a fresh, realistic pool; fall back gracefully.
        agents: List[str] = []
        try:
            from fake_useragent import UserAgent

            ua = UserAgent()
            seen = set()
            for _ in range(12):
                candidate = ua.random
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    agents.append(candidate)
        except Exception:
            agents = []

        return cls(agents or list(_BUILTIN_USER_AGENTS))

    def next(self) -> str:
        with self._lock:
            return next(self._cycle)
