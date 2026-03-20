from __future__ import annotations

import os
from typing import List, Optional
from urllib.parse import urlparse


def normalize_proxy(raw: str) -> Optional[str]:
    text = str(raw or "").strip()
    if not text:
        return None

    if "://" in text:
        parsed = urlparse(text)
        if not parsed.scheme or not parsed.hostname or not parsed.port:
            return None
        return text

    # host:port:user:pass
    parts = text.split(":")
    if len(parts) == 4:
        host, port, username, password = parts
        if host and port and username and password:
            return f"http://{username}:{password}@{host}:{port}"
        return None

    # user:pass@host:port
    if "@" in text:
        return f"http://{text}"

    return None


def mask_proxy(proxy_url: Optional[str]) -> Optional[str]:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    if not parsed.hostname or not parsed.port:
        return proxy_url
    scheme = parsed.scheme or "http"
    if parsed.username:
        return f"{scheme}://***:***@{parsed.hostname}:{parsed.port}"
    return f"{scheme}://{parsed.hostname}:{parsed.port}"


class ProxyPool:
    def __init__(self, proxies: List[str]) -> None:
        self._proxies = proxies
        self._cursor = 0

    @property
    def size(self) -> int:
        return len(self._proxies)

    @property
    def enabled(self) -> bool:
        return self.size > 0

    def next(self) -> Optional[str]:
        if not self._proxies:
            return None
        proxy = self._proxies[self._cursor % len(self._proxies)]
        self._cursor += 1
        return proxy

    @classmethod
    def from_env(
        cls,
        *,
        list_env: str = "SOFASCORE_PROXIES",
        single_env: str = "SOFASCORE_PROXY",
    ) -> "ProxyPool":
        values: List[str] = []
        raw_list = os.getenv(list_env, "")
        raw_single = os.getenv(single_env, "")

        if raw_list:
            normalized = raw_list.replace("\n", ",").replace(";", ",")
            for entry in normalized.split(","):
                proxy = normalize_proxy(entry)
                if proxy:
                    values.append(proxy)

        if raw_single:
            proxy = normalize_proxy(raw_single)
            if proxy:
                values.append(proxy)

        # Keep order but drop duplicates
        deduped: List[str] = []
        seen = set()
        for proxy in values:
            if proxy in seen:
                continue
            seen.add(proxy)
            deduped.append(proxy)

        return cls(deduped)
