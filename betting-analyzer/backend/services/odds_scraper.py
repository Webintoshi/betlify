from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Dict, Optional, Tuple

from curl_cffi.requests import AsyncSession
from dotenv import load_dotenv
from supabase import Client, create_client
from proxy_pool import ProxyPool, mask_proxy

logger = logging.getLogger("odds_scraper")

BASE_URL = "https://www.sofascore.com/api/v1"
ODDS_ENDPOINT = "/event/{event_id}/odds/1/all"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
}

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent.parent / ".env")
load_dotenv(BASE_DIR.parent / ".env", override=True)

SOFASCORE_COOKIE = os.getenv("SOFASCORE_COOKIE", "").strip()
if SOFASCORE_COOKIE:
    HEADERS["Cookie"] = SOFASCORE_COOKIE


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = -1.0) -> float:
    try:
        if value is None:
            return fallback
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return fallback


def _fraction_to_decimal(value: Any, fallback: float = -1.0) -> float:
    text = str(value or "").strip()
    if not text:
        return fallback
    if "/" not in text:
        return _safe_float(text, fallback=fallback)
    numerator_text, denominator_text = text.split("/", 1)
    numerator = _safe_float(numerator_text, fallback=-1.0)
    denominator = _safe_float(denominator_text, fallback=-1.0)
    if denominator <= 0:
        return fallback
    return round((numerator / denominator) + 1.0, 4)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _extract_line(text: str) -> Optional[float]:
    match = re.search(r"([+-]?\d+(?:[.,]\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _line_to_key_suffix(line: float) -> str:
    if float(line).is_integer():
        return str(int(line))
    return str(line)


def _is_half_time_market(market_text: str) -> bool:
    normalized = _normalize_text(market_text)
    return any(token in normalized for token in ["1st half", "first half", "halftime", "half-time", "ilk yari", "iy"])


def _map_market_key(market_name: str, market_group: str, outcome_name: str) -> Optional[str]:
    market_text = _normalize_text(f"{market_group} {market_name}")
    outcome_text = _normalize_text(outcome_name)

    if "1x2" in market_text or "match winner" in market_text:
        is_half_time = _is_half_time_market(market_text)
        if outcome_text in {"1", "home"}:
            return "IY1" if is_half_time else "MS1"
        if outcome_text in {"x", "draw"}:
            return "IYX" if is_half_time else "MSX"
        if outcome_text in {"2", "away"}:
            return "IY2" if is_half_time else "MS2"
        return None

    if "both teams to score" in market_text or "btts" in market_text:
        if outcome_text in {"yes", "var"}:
            return "KG_VAR"
        if outcome_text in {"no", "yok"}:
            return "KG_YOK"
        return None

    if any(token in market_text for token in ["over/under", "total goals", "goals over/under"]):
        line = _extract_line(outcome_text) or _extract_line(market_text)
        if line is None:
            return None
        line = round(float(line), 1)
        if line not in {0.5, 1.5, 2.5, 3.5}:
            return None
        suffix = _line_to_key_suffix(line)
        is_over = "over" in outcome_text or outcome_text.startswith("o")
        is_under = "under" in outcome_text or outcome_text.startswith("u")
        if not is_over and not is_under:
            return None
        prefix = "IY" if _is_half_time_market(market_text) else "MS"
        return f"{prefix}_{'O' if is_over else 'U'}{suffix}"

    if "handicap" in market_text:
        line = _extract_line(outcome_text) or _extract_line(market_text)
        if line is None:
            return None
        line = round(abs(float(line)), 1)
        if line not in {1.0, 1.5}:
            return None
        if "-1.5" in outcome_text:
            return "HCP_-1.5"
        if "-1" in outcome_text:
            return "HCP_-1"
        if "+1.5" in outcome_text:
            return "HCP_+1.5"
        if "+1" in outcome_text:
            return "HCP_+1"
        return None

    return None


class OddsScraperService:
    def __init__(
        self,
        *,
        supabase_client: Optional[Client] = None,
    ) -> None:
        self.supabase = supabase_client or self._build_supabase_client()
        self._rate_lock = asyncio.Lock()
        self._last_request_ts = 0.0
        self._odds_table_available: Optional[bool] = None
        self._best_bet_column_available: Optional[bool] = None
        self.proxy_pool = ProxyPool.from_env()

    @staticmethod
    def _build_supabase_client() -> Optional[Client]:
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not supabase_url or not supabase_service_key or "BURAYA_" in supabase_service_key:
            return None
        try:
            return create_client(supabase_url, supabase_service_key)
        except Exception:
            logger.exception("Supabase client initialization failed.")
            return None

    async def _respect_rate_limit(self) -> None:
        async with self._rate_lock:
            now = monotonic()
            elapsed = now - self._last_request_ts
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            self._last_request_ts = monotonic()

    async def _fetch_event_odds_payload(self, event_id: int) -> Optional[Dict[str, Any]]:
        url = f"{BASE_URL}{ODDS_ENDPOINT.format(event_id=event_id)}"
        for attempt in range(1, 4):
            await self._respect_rate_limit()
            proxy = self.proxy_pool.next()
            proxy_masked = mask_proxy(proxy)
            try:
                async with AsyncSession(impersonate="chrome120") as session:
                    response = await session.get(url, headers=HEADERS, timeout=20, proxy=proxy)
            except Exception as exc:
                logger.warning(
                    "Sofascore odds request failed. event_id=%s attempt=%s proxy=%s err=%s",
                    event_id,
                    attempt,
                    proxy_masked,
                    exc,
                )
                if attempt < 3:
                    await asyncio.sleep(0.8 * attempt)
                continue

            if response.status_code == 429:
                logger.warning(
                    "Sofascore odds 429. event_id=%s attempt=%s proxy=%s",
                    event_id,
                    attempt,
                    proxy_masked,
                )
                await asyncio.sleep(60)
                continue

            if response.status_code == 200:
                try:
                    payload = response.json()
                    if isinstance(payload, dict):
                        return payload
                except Exception:
                    logger.warning("Sofascore odds JSON parse failed. event_id=%s attempt=%s", event_id, attempt)
            else:
                logger.warning(
                    "Sofascore odds HTTP %s event_id=%s attempt=%s proxy=%s",
                    response.status_code,
                    event_id,
                    attempt,
                    proxy_masked,
                )
            if attempt < 3:
                await asyncio.sleep(0.8 * attempt)
        return None

    def _resolve_match(self, match_id_or_event_id: str) -> Optional[Dict[str, Any]]:
        if self.supabase is None:
            return None
        normalized = str(match_id_or_event_id or "").strip()
        if not normalized:
            return None

        select_columns = "id,sofascore_id,status,match_date"
        try:
            by_internal = (
                self.supabase.table("matches")
                .select(select_columns)
                .eq("id", normalized)
                .limit(1)
                .execute()
            )
            if by_internal.data:
                return by_internal.data[0]
        except Exception:
            logger.exception("Match lookup by id failed. match_id=%s", normalized)

        if normalized.isdigit():
            try:
                by_sofascore = (
                    self.supabase.table("matches")
                    .select(select_columns)
                    .eq("sofascore_id", int(normalized))
                    .limit(1)
                    .execute()
                )
                if by_sofascore.data:
                    return by_sofascore.data[0]
            except Exception:
                logger.exception("Match lookup by sofascore_id failed. event_id=%s", normalized)
        return None

    @staticmethod
    def _extract_odd(outcome: Dict[str, Any]) -> float:
        odd = _safe_float(outcome.get("odds"), fallback=-1.0)
        if odd > 0:
            return odd
        odd = _safe_float(outcome.get("decimalValue"), fallback=-1.0)
        if odd > 0:
            return odd
        odd = _fraction_to_decimal(outcome.get("fractionalValue"), fallback=-1.0)
        if odd > 0:
            return odd
        return _fraction_to_decimal(outcome.get("initialFractionalValue"), fallback=-1.0)

    def _parse_markets(self, payload: Dict[str, Any]) -> Dict[str, float]:
        result: Dict[str, float] = {}
        markets = payload.get("markets", [])
        if not isinstance(markets, list):
            return result

        for market in markets:
            if not isinstance(market, dict):
                continue
            market_name = str(market.get("marketName") or market.get("name") or "")
            market_group = str(market.get("marketGroup") or market.get("group") or "")
            choices = market.get("choices") if isinstance(market.get("choices"), list) else market.get("outcomes", [])
            if not isinstance(choices, list):
                continue
            for outcome in choices:
                if not isinstance(outcome, dict):
                    continue
                outcome_name = str(outcome.get("name") or outcome.get("choice") or "")
                market_key = _map_market_key(market_name, market_group, outcome_name)
                if not market_key:
                    continue
                odd = self._extract_odd(outcome)
                if odd <= 0:
                    continue
                # Keep the freshest value encountered for each market key.
                result[market_key] = odd
        return result

    def _odds_table_exists(self) -> bool:
        if self.supabase is None:
            return False
        if self._odds_table_available is not None:
            return self._odds_table_available
        try:
            self.supabase.table("odds").select("id").limit(1).execute()
            self._odds_table_available = True
        except Exception:
            self._odds_table_available = False
            logger.warning("odds table not found; odds snapshot writes are skipped.")
        return self._odds_table_available

    def _best_bet_column_exists(self) -> bool:
        if self.supabase is None:
            return False
        if self._best_bet_column_available is not None:
            return self._best_bet_column_available
        try:
            self.supabase.table("matches").select("best_bet").limit(1).execute()
            self._best_bet_column_available = True
        except Exception:
            self._best_bet_column_available = False
            logger.warning("matches.best_bet column not found; best bet updates are skipped.")
        return self._best_bet_column_available

    def _upsert_odds_history(self, *, match_id: str, market: str, odd: float, is_finished: bool) -> None:
        if self.supabase is None:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            existing = (
                self.supabase.table("odds_history")
                .select("id,opening_odd,current_odd")
                .eq("match_id", match_id)
                .eq("bookmaker", "sofascore")
                .eq("market_type", market)
                .limit(1)
                .execute()
            )
            rows = existing.data or []
            if rows:
                row = rows[0]
                opening = _safe_float(row.get("opening_odd") or row.get("current_odd"), fallback=odd)
                payload: Dict[str, Any] = {
                    "opening_odd": opening,
                    "current_odd": odd,
                    "recorded_at": now_iso,
                }
                if is_finished:
                    payload["closing_odd"] = odd
                self.supabase.table("odds_history").update(payload).eq("id", row["id"]).execute()
            else:
                self.supabase.table("odds_history").insert(
                    {
                        "match_id": match_id,
                        "market_type": market,
                        "bookmaker": "sofascore",
                        "opening_odd": odd,
                        "current_odd": odd,
                        "closing_odd": odd if is_finished else None,
                        "recorded_at": now_iso,
                    }
                ).execute()
        except Exception:
            logger.exception("odds_history upsert failed. match_id=%s market=%s", match_id, market)

    def _upsert_odds_snapshot(self, *, match_id: str, market: str, odd: float, ev: Optional[float]) -> None:
        if self.supabase is None or not self._odds_table_exists():
            return
        payload = {
            "match_id": match_id,
            "market": market,
            "odd": round(float(odd), 4),
            "ev": None if ev is None else round(float(ev), 6),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.supabase.table("odds").upsert(payload, on_conflict="match_id,market").execute()
        except Exception:
            logger.exception("odds table upsert failed. match_id=%s market=%s", match_id, market)

    async def get_odds_for_match(self, match_id_or_event_id: str) -> Dict[str, float]:
        match = self._resolve_match(match_id_or_event_id)
        if not match:
            return {}
        match_id = str(match.get("id") or "")
        event_id = _safe_int(match.get("sofascore_id"))
        if not match_id or event_id <= 0:
            return {}

        payload = await self._fetch_event_odds_payload(event_id)
        if payload is None:
            return {}
        market_odds = self._parse_markets(payload)
        if not market_odds:
            return {}

        is_finished = str(match.get("status", "")).lower() == "finished"
        for market, odd in market_odds.items():
            self._upsert_odds_history(match_id=match_id, market=market, odd=odd, is_finished=is_finished)
            self._upsert_odds_snapshot(match_id=match_id, market=market, odd=odd, ev=None)
        return market_odds

    def save_ev_rows(self, *, match_id: str, ev_result: Dict[str, Any]) -> None:
        if self.supabase is None:
            return
        all_markets = ev_result.get("all_markets", [])
        if isinstance(all_markets, list):
            for row in all_markets:
                if not isinstance(row, dict):
                    continue
                market = str(row.get("market_type") or "")
                odd = _safe_float(row.get("odd"), fallback=-1.0)
                if not market or odd <= 0:
                    continue
                ev_value = _safe_float(row.get("ev"), fallback=None)  # type: ignore[arg-type]
                self._upsert_odds_snapshot(match_id=match_id, market=market, odd=odd, ev=ev_value)

        best_market = ev_result.get("best_market", {})
        if not isinstance(best_market, dict):
            return
        market_name = str(best_market.get("market_type") or "")
        if market_name and self._best_bet_column_exists():
            try:
                self.supabase.table("matches").update({"best_bet": market_name}).eq("id", match_id).execute()
            except Exception:
                logger.exception("matches.best_bet update failed. match_id=%s", match_id)

    async def refresh_todays_matches(self, *, timezone_name: str = "Europe/Istanbul") -> Dict[str, Any]:
        if self.supabase is None:
            return {"processed_matches": 0, "updated_markets": 0}

        from zoneinfo import ZoneInfo

        tz = ZoneInfo(timezone_name)
        today = datetime.now(tz).date().isoformat()
        tomorrow = (datetime.now(tz).date() + timedelta(days=1)).isoformat()
        try:
            result = (
                self.supabase.table("matches")
                .select("id,status,match_date")
                .gte("match_date", f"{today}T00:00:00")
                .lte("match_date", f"{tomorrow}T23:59:59")
                .in_("status", ["scheduled", "live"])
                .order("match_date")
                .execute()
            )
            rows = result.data or []
        except Exception:
            logger.exception("Today matches read failed for odds refresh.")
            return {"processed_matches": 0, "updated_markets": 0}

        processed = 0
        markets_updated = 0
        for row in rows:
            match_id = str(row.get("id") or "")
            if not match_id:
                continue
            odds = await self.get_odds_for_match(match_id)
            if odds:
                processed += 1
                markets_updated += len(odds)
        logger.info("Odds refresh completed. processed_matches=%s updated_markets=%s", processed, markets_updated)
        return {"processed_matches": processed, "updated_markets": markets_updated}

    async def close(self) -> None:
        return None


_default_service = OddsScraperService()


def get_service() -> OddsScraperService:
    return _default_service
