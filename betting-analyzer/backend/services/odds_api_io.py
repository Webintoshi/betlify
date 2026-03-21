from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import httpx
from dotenv import load_dotenv

logger = logging.getLogger("odds_api_io")

BASE_URL = "https://api.odds-api.io/v3"

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent.parent / ".env")
load_dotenv(BASE_DIR.parent / ".env", override=True)


class OddsApiIo:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        bookmaker: Optional[str] = None,
        max_req_per_hour: Optional[int] = None,
        reserve_threshold: int = 15,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.api_key = (api_key or os.getenv("ODDS_API_IO_KEY") or os.getenv("THE_ODDS_API_KEY") or "").strip()
        self.bookmaker = (bookmaker or os.getenv("ODDS_API_BOOKMAKER") or "Betfair Exchange").strip()
        self.max_req_per_hour = max(1, int(max_req_per_hour or os.getenv("ODDS_API_MAX_REQ_PER_HOUR", "100") or 100))
        self.reserve_threshold = max(0, int(reserve_threshold))

        self.http_client = http_client or httpx.AsyncClient(timeout=20.0)
        self._rate_lock = asyncio.Lock()
        self._request_timestamps: deque[float] = deque()

        self.requests_limit: Optional[int] = None
        self.requests_remaining: Optional[int] = None
        self.requests_reset_at: Optional[str] = None

    @staticmethod
    def _safe_int(value: Any, fallback: int = 0) -> int:
        try:
            if value is None:
                return fallback
            return int(str(value).strip())
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _parse_iso(raw: str) -> Optional[datetime]:
        value = str(raw or "").strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _as_event_list(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            if all(key in payload for key in ("id", "home", "away")):
                return [payload]
        return []

    def _prune_request_window(self) -> None:
        now = monotonic()
        threshold = now - 3600.0
        while self._request_timestamps and self._request_timestamps[0] < threshold:
            self._request_timestamps.popleft()

    def _track_request(self) -> None:
        self._request_timestamps.append(monotonic())

    def _record_headers(self, headers: Mapping[str, str]) -> None:
        limit_raw = headers.get("X-Ratelimit-Limit") or headers.get("x-ratelimit-limit")
        remaining_raw = headers.get("X-Ratelimit-Remaining") or headers.get("x-ratelimit-remaining")
        reset_raw = headers.get("X-Ratelimit-Reset") or headers.get("x-ratelimit-reset")

        if limit_raw is not None:
            self.requests_limit = self._safe_int(limit_raw, fallback=self.requests_limit or self.max_req_per_hour)
        if remaining_raw is not None:
            self.requests_remaining = self._safe_int(remaining_raw, fallback=self.requests_remaining or 0)
        if reset_raw:
            self.requests_reset_at = str(reset_raw)

    async def _can_call(self, *, critical: bool) -> bool:
        async with self._rate_lock:
            self._prune_request_window()

            if not self.api_key:
                logger.warning("ODDS_API_IO_KEY tanimli degil.")
                return False

            if self.requests_remaining is not None and self.requests_remaining <= 0:
                logger.warning("Odds API istek limiti tukendi. reset=%s", self.requests_reset_at)
                return False

            if not critical and self.requests_remaining is not None and self.requests_remaining <= self.reserve_threshold:
                logger.warning(
                    "Odds API reserve guard aktif. remaining=%s reserve=%s",
                    self.requests_remaining,
                    self.reserve_threshold,
                )
                return False

            if len(self._request_timestamps) >= self.max_req_per_hour:
                if critical:
                    logger.warning(
                        "Odds API saatlik soft limit asildi ama kritik cagrida devam ediliyor. count=%s",
                        len(self._request_timestamps),
                    )
                    return True
                logger.warning("Odds API saatlik soft limit asildi. count=%s", len(self._request_timestamps))
                return False
            return True

    async def _request(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        critical: bool = False,
    ) -> Optional[Any]:
        if not await self._can_call(critical=critical):
            return None

        query: Dict[str, Any] = dict(params or {})
        query.setdefault("apiKey", self.api_key)

        try:
            response = await self.http_client.get(f"{BASE_URL}{path}", params=query)
        except httpx.TimeoutException:
            logger.error("Odds API timeout. path=%s", path)
            return None
        except Exception as exc:
            logger.error("Odds API request failed. path=%s error=%s", path, exc)
            return None

        self._track_request()
        self._record_headers(response.headers)

        if response.status_code == 429:
            logger.warning("Odds API 429. remaining=%s reset=%s", self.requests_remaining, self.requests_reset_at)
            return None

        if response.status_code >= 400:
            logger.warning("Odds API HTTP %s path=%s", response.status_code, path)
            return None

        try:
            return response.json()
        except ValueError:
            logger.warning("Odds API JSON parse failed. path=%s", path)
            return None

    def should_skip_non_critical(self) -> bool:
        return self.requests_remaining is not None and self.requests_remaining <= self.reserve_threshold

    def quota_state(self) -> Dict[str, Any]:
        reset_dt = self._parse_iso(self.requests_reset_at or "")
        return {
            "limit": self.requests_limit,
            "remaining": self.requests_remaining,
            "reset_at": self.requests_reset_at,
            "reset_at_iso": reset_dt.isoformat() if reset_dt else None,
            "reserve_threshold": self.reserve_threshold,
            "max_req_per_hour": self.max_req_per_hour,
            "bookmaker": self.bookmaker,
            "api_key_configured": bool(self.api_key),
        }

    async def get_selected_bookmakers(self, *, critical: bool = False) -> Optional[Dict[str, Any]]:
        payload = await self._request("/bookmakers/selected", critical=critical)
        if isinstance(payload, dict):
            return payload
        return None

    async def get_events(
        self,
        *,
        sport: str = "football",
        status: str = "pending,live",
        bookmaker: Optional[str] = None,
        from_iso: Optional[str] = None,
        to_iso: Optional[str] = None,
        league: Optional[str] = None,
        limit: int = 500,
        skip: int = 0,
        critical: bool = False,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "sport": sport,
            "status": status,
            "limit": max(1, min(1000, int(limit))),
            "skip": max(0, int(skip)),
        }
        bookmaker_value = (bookmaker or self.bookmaker).strip()
        if bookmaker_value:
            params["bookmaker"] = bookmaker_value
        if from_iso:
            params["from"] = from_iso
        if to_iso:
            params["to"] = to_iso
        if league:
            params["league"] = league

        payload = await self._request("/events", params=params, critical=critical)
        return self._as_event_list(payload)

    async def get_events_paginated(
        self,
        *,
        sport: str = "football",
        status: str = "pending,live",
        bookmaker: Optional[str] = None,
        from_iso: Optional[str] = None,
        to_iso: Optional[str] = None,
        league: Optional[str] = None,
        page_size: int = 500,
        max_pages: int = 10,
        critical: bool = False,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        normalized_size = max(1, min(1000, int(page_size)))
        for page_index in range(max(1, int(max_pages))):
            chunk = await self.get_events(
                sport=sport,
                status=status,
                bookmaker=bookmaker,
                from_iso=from_iso,
                to_iso=to_iso,
                league=league,
                limit=normalized_size,
                skip=page_index * normalized_size,
                critical=critical,
            )
            if not chunk:
                break
            results.extend(chunk)
            if len(chunk) < normalized_size:
                break
            if not critical and self.should_skip_non_critical():
                logger.warning("Odds API paginated events scan reserve nedeniyle erken kesildi.")
                break
        return results

    async def get_event_by_id(self, event_id: int, *, critical: bool = False) -> Optional[Dict[str, Any]]:
        if int(event_id or 0) <= 0:
            return None
        payload = await self._request(f"/events/{int(event_id)}", critical=critical)
        if isinstance(payload, dict):
            return payload
        return None

    async def get_odds_multi(
        self,
        event_ids: Sequence[int],
        *,
        bookmakers: Optional[str] = None,
        critical: bool = False,
    ) -> List[Dict[str, Any]]:
        cleaned = [str(int(value)) for value in event_ids if int(value or 0) > 0]
        if not cleaned:
            return []
        params = {
            "eventIds": ",".join(cleaned[:10]),
            "bookmakers": (bookmakers or self.bookmaker),
        }
        payload = await self._request("/odds/multi", params=params, critical=critical)
        return self._as_event_list(payload)

    async def get_odds_single(
        self,
        event_id: int,
        *,
        bookmakers: Optional[str] = None,
        critical: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if int(event_id or 0) <= 0:
            return None
        params = {
            "eventId": int(event_id),
            "bookmakers": (bookmakers or self.bookmaker),
        }
        payload = await self._request("/odds", params=params, critical=critical)
        if isinstance(payload, dict):
            return payload
        rows = self._as_event_list(payload)
        if rows:
            return rows[0]
        return None

    async def close(self) -> None:
        try:
            await self.http_client.aclose()
        except Exception:
            logger.exception("OddsApiIo HTTP client close failed.")


_default_client = OddsApiIo()


def get_client() -> OddsApiIo:
    return _default_client
