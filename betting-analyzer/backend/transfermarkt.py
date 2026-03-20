from __future__ import annotations

import asyncio
import html
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from curl_cffi.requests import AsyncSession
from dotenv import load_dotenv
from supabase import Client, create_client

logger = logging.getLogger("transfermarkt")

BASE_URL = "https://www.transfermarkt.com.tr"
SEARCH_URL = f"{BASE_URL}/schnellsuche/ergebnis/schnellsuche"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9",
}
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env", override=True)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


class TransfermarktService:
    def __init__(self, *, supabase_client: Optional[Client] = None) -> None:
        self.supabase = supabase_client or self._build_supabase_client()

    @staticmethod
    def _build_supabase_client() -> Optional[Client]:
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not supabase_url or not supabase_service_key or "BURAYA_" in supabase_service_key:
            return None
        try:
            return create_client(supabase_url, supabase_service_key)
        except Exception:
            logger.warning("Supabase client could not be initialized for Transfermarkt.")
            return None

    def _cache_key(self, team_name: str) -> str:
        return f"transfermarkt:market_value:{team_name.strip().lower()}"

    def _get_cached(self, cache_key: str) -> Optional[float]:
        if self.supabase is None:
            return None
        try:
            result = (
                self.supabase.table("api_cache")
                .select("payload,expires_at")
                .eq("cache_key", cache_key)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if not rows:
                return None
            row = rows[0]
            expires_at = row.get("expires_at")
            if not expires_at:
                return None
            expire_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expire_dt <= datetime.now(timezone.utc):
                return None
            payload = row.get("payload")
            if isinstance(payload, dict):
                return _safe_float(payload.get("market_value_million"), fallback=0.0)
            return None
        except Exception:
            return None

    def _set_cache(self, cache_key: str, value_million: float) -> None:
        if self.supabase is None:
            return
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=CACHE_TTL_SECONDS)
            payload = {
                "cache_key": cache_key,
                "payload": {"market_value_million": value_million},
                "expires_at": expires_at.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.supabase.table("api_cache").upsert(payload, on_conflict="cache_key").execute()
        except Exception:
            return

    async def _fetch_html(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        try:
            async with AsyncSession(impersonate="chrome120") as session:
                response = await session.get(url, params=params, headers=HEADERS, timeout=20)
        except Exception as exc:
            logger.error("Transfermarkt request failed: %s", exc)
            return None

        if response.status_code >= 400:
            logger.warning("Transfermarkt HTTP %s for %s", response.status_code, url)
            return None
        return response.text

    @staticmethod
    def _normalize_number(raw: str) -> float:
        text = raw.strip().replace(" ", "")
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")
        return _safe_float(text, fallback=0.0)

    def _parse_market_value_million(self, text: str) -> Optional[float]:
        cleaned = html.unescape(text).replace("\xa0", " ").lower()
        match = re.search(
            r"([0-9]+(?:[.,][0-9]+)?)\s*(bn|m|k|mil\.?|mio\.?|milyar|milyon|bin|mn|billion|million|thousand)",
            cleaned,
        )
        if not match:
            return None

        number = self._normalize_number(match.group(1))
        unit = match.group(2)
        if number <= 0:
            return None

        if unit in {"bn", "billion", "milyar"}:
            return round(number * 1000.0, 2)
        if unit in {"m", "million", "milyon", "mn", "mil.", "mil", "mio.", "mio"}:
            return round(number, 2)
        if unit in {"k", "thousand", "bin"}:
            return round(number / 1000.0, 4)
        return None

    @staticmethod
    def _club_results_section(search_html: str) -> str:
        marker = 'id="club-grid"'
        start = search_html.find(marker)
        if start < 0:
            return search_html
        tbody_end = search_html.find("</tbody>", start)
        if tbody_end < 0:
            end = search_html.find("</table>", start)
            if end < 0:
                return search_html[start:]
            return search_html[start : end + len("</table>")]
        end = search_html.find("</table>", tbody_end)
        if end < 0:
            return search_html[start:]
        return search_html[start : end + len("</table>")]

    @staticmethod
    def _extract_first_team_path(search_html: str) -> Optional[str]:
        section = TransfermarktService._club_results_section(search_html)
        patterns = [
            r'href="(/[^"]*/startseite/verein/\d+[^"]*)"',
            r'href="(/[^"]*/verein/\d+[^"]*)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, section)
            if match:
                return html.unescape(match.group(1))
        return None

    def _extract_market_value_from_search(self, search_html: str) -> Optional[float]:
        section = self._club_results_section(search_html)
        link_match = re.search(r'href="(/[^"]*/startseite/verein/\d+[^"]*)"', section, flags=re.IGNORECASE)
        if not link_match:
            return None
        start_idx = link_match.start()
        snippet = section[start_idx : start_idx + 20000]
        right_cells = re.findall(r'<td class="rechts">([^<]+)</td>', snippet, flags=re.IGNORECASE)
        for cell in right_cells:
            parsed = self._parse_market_value_million(cell)
            if parsed is not None and parsed > 0:
                return parsed

        raw_values = re.findall(
            r"([0-9\.,]+\s*(?:bn|m|k|mil\.?|mio\.?|milyar|milyon|bin|mn|billion|million|thousand)\s*€?)",
            snippet,
            flags=re.IGNORECASE,
        )
        raw_values += re.findall(
            r"(€\s*[0-9\.,]+\s*(?:bn|m|k|mil\.?|mio\.?|milyar|milyon|bin|mn|billion|million|thousand)?)",
            snippet,
            flags=re.IGNORECASE,
        )
        for raw in raw_values:
            parsed = self._parse_market_value_million(raw)
            if parsed is not None and parsed > 0:
                return parsed
        return None

    def _extract_market_value_from_team_page(self, team_html: str) -> Optional[float]:
        patterns = [
            r"Kadro değeri[:\s]*</[^>]+>\s*<[^>]+>([^<]+)</",
            r"Kadro degeri[:\s]*</[^>]+>\s*<[^>]+>([^<]+)</",
            r"Squad value[:\s]*</[^>]+>\s*<[^>]+>([^<]+)</",
        ]
        for pattern in patterns:
            match = re.search(pattern, team_html, flags=re.IGNORECASE)
            if not match:
                continue
            parsed = self._parse_market_value_million(match.group(1))
            if parsed is not None and parsed > 0:
                return parsed

        raw_values = re.findall(
            r"([0-9\.,]+\s*(?:bn|m|k|mil\.?|mio\.?|milyar|milyon|bin|mn|billion|million|thousand)\s*€?)",
            team_html,
            flags=re.IGNORECASE,
        )
        raw_values += re.findall(
            r"(€\s*[0-9\.,]+\s*(?:bn|m|k|mil\.?|mio\.?|milyar|milyon|bin|mn|billion|million|thousand)?)",
            team_html,
            flags=re.IGNORECASE,
        )
        for raw in raw_values:
            parsed = self._parse_market_value_million(raw)
            if parsed is not None and parsed > 0:
                return parsed
        return None

    async def get_team_market_value(self, team_name: str) -> Optional[float]:
        clean_name = team_name.strip()
        if not clean_name:
            return None

        cache_key = self._cache_key(clean_name)
        cached = self._get_cached(cache_key)
        if cached is not None and cached > 0:
            return cached

        params = {"query": clean_name}
        search_html = await self._fetch_html(SEARCH_URL, params=params)
        if not search_html:
            return None

        value_million = self._extract_market_value_from_search(search_html)
        path = self._extract_first_team_path(search_html)
        if path:
            await asyncio.sleep(1)
            team_page_html = await self._fetch_html(f"{BASE_URL}{path}")
            if team_page_html:
                page_value = self._extract_market_value_from_team_page(team_page_html)
                if page_value is not None and page_value > 0 and (
                    value_million is None or page_value > (value_million * 0.1)
                ):
                    value_million = page_value

        if value_million is None or value_million <= 0:
            logger.warning("Transfermarkt market value parse failed for %s", clean_name)
            return None

        self._set_cache(cache_key, value_million)
        return value_million

    async def update_team_market_value(self, team_id: str, team_name: str) -> Optional[float]:
        value_million = await self.get_team_market_value(team_name)
        if value_million is None or self.supabase is None:
            return value_million
        try:
            self.supabase.table("teams").update({"market_value": value_million}).eq("id", team_id).execute()
            return value_million
        except Exception:
            logger.exception("teams.market_value update failed. team_id=%s", team_id)
            return None

    async def close(self) -> None:
        return


_default_service = TransfermarktService()


def get_service() -> TransfermarktService:
    return _default_service


async def get_team_market_value(team_name: str) -> Optional[float]:
    return await _default_service.get_team_market_value(team_name)
