from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from supabase import Client, create_client

logger = logging.getLogger(__name__)

THE_ODDS_BASE_URL = "https://api.the-odds-api.com/v4"

ODDS_API_SPORT_KEYS = {
    203: "soccer_turkey_super_league",
    2: "soccer_uefa_champs_league",
    3: "soccer_uefa_europa_league",
    39: "soccer_epl",
    140: "soccer_spain_la_liga",
    135: "soccer_italy_serie_a",
    78: "soccer_germany_bundesliga",
    61: "soccer_france_ligue_one",
    88: "soccer_netherlands_eredivisie",
    94: "soccer_portugal_primeira_liga",
}

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env", override=True)


class OddsTrackerService:
    def __init__(
        self,
        *,
        supabase_client: Optional[Client] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.api_key = os.getenv("THE_ODDS_API_KEY", "")
        self.supabase = supabase_client or self._build_supabase_client()
        self.http_client = http_client or httpx.AsyncClient(timeout=10.0)
        self.requests_remaining: Optional[int] = None
        self.low_quota_day: Optional[str] = None

    @staticmethod
    def _build_supabase_client() -> Optional[Client]:
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not supabase_url or not supabase_service_key or "BURAYA_" in supabase_service_key:
            return None
        try:
            return create_client(supabase_url, supabase_service_key)
        except Exception:
            logger.warning("Supabase client initialization failed.")
            return None

    @staticmethod
    def _safe_int(value: Any, fallback: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _safe_float(value: Any, fallback: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _should_skip_due_quota(self) -> bool:
        today = datetime.now(timezone.utc).date().isoformat()
        if self.requests_remaining is not None and self.requests_remaining < 20 and self.low_quota_day == today:
            return True
        return False

    def _update_quota(self, headers: httpx.Headers) -> None:
        remaining_raw = headers.get("x-requests-remaining")
        if remaining_raw is not None:
            self.requests_remaining = self._safe_int(remaining_raw, fallback=self.requests_remaining or 0)
            logger.info("The Odds API kalan istek: %s", self.requests_remaining)
            if self.requests_remaining < 20:
                self.low_quota_day = datetime.now(timezone.utc).date().isoformat()

    def _cache_key(self, sport_key: str) -> str:
        return f"the_odds:/sports/{sport_key}/odds"

    def _get_cached_payload(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
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
            return payload if isinstance(payload, list) else None
        except Exception:
            return None

    def _set_cached_payload(self, cache_key: str, payload: List[Dict[str, Any]], ttl_seconds: int) -> None:
        if self.supabase is None:
            return
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            row = {
                "cache_key": cache_key,
                "payload": payload,
                "expires_at": expires_at.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.supabase.table("api_cache").upsert(row, on_conflict="cache_key").execute()
        except Exception:
            return

    async def get_current_odds(self, league_id: int) -> Optional[List[Dict[str, Any]]]:
        if not self.api_key:
            logger.warning("THE_ODDS_API_KEY tanimli degil.")
            return None
        sport_key = ODDS_API_SPORT_KEYS.get(league_id)
        if not sport_key:
            return None
        if self._should_skip_due_quota():
            logger.warning("Kalan API istegi az (%s), oran guncellemesi atlandi", self.requests_remaining)
            return None

        cache_key = self._cache_key(sport_key)
        cached = self._get_cached_payload(cache_key)
        if cached is not None:
            return cached

        url = f"{THE_ODDS_BASE_URL}/sports/{sport_key}/odds"
        params = {
            "apiKey": os.getenv("THE_ODDS_API_KEY"),
            "regions": "eu",
            "markets": "h2h,totals,btts",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        try:
            response = await self.http_client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.error("Timeout: %s", url)
            return None
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP %s: %s", exc.response.status_code, url)
            return None
        except Exception as exc:
            logger.error("Beklenmeyen hata: %s", exc)
            return None

        self._update_quota(response.headers)
        await asyncio.sleep(1)
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, list):
            return None
        self._set_cached_payload(cache_key, payload, ttl_seconds=1200)
        return payload

    def _existing_odd_row(self, match_id: str, bookmaker: str, market_type: str) -> Optional[Dict[str, Any]]:
        if self.supabase is None:
            return None
        try:
            result = (
                self.supabase.table("odds_history")
                .select("id,opening_odd,current_odd,closing_odd")
                .eq("match_id", match_id)
                .eq("bookmaker", bookmaker)
                .eq("market_type", market_type)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    async def calculate_line_movement(self, match_id: str) -> Dict[str, Any]:
        if self.supabase is None:
            return {"match_id": match_id, "movement": {}, "sharp_money_side": "none"}
        try:
            result = (
                self.supabase.table("odds_history")
                .select("market_type,bookmaker,opening_odd,current_odd")
                .eq("match_id", match_id)
                .execute()
            )
        except Exception:
            logger.exception("Line movement icin odds_history okunamadi. match_id=%s", match_id)
            return {"match_id": match_id, "movement": {}, "sharp_money_side": "none"}

        rows = result.data or []
        by_key: Dict[str, Dict[str, float]] = {}
        home_opening: Optional[float] = None
        away_opening: Optional[float] = None
        home_movement: Optional[float] = None

        for row in rows:
            market_type = str(row.get("market_type", "unknown"))
            bookmaker = str(row.get("bookmaker", "unknown"))
            opening = self._safe_float(row.get("opening_odd"), 0.0)
            current = self._safe_float(row.get("current_odd"), 0.0)
            if opening <= 0 or current <= 0:
                continue
            movement_pct = ((current - opening) / opening) * 100.0
            sharp_flag = abs(movement_pct) > 5.0
            key = f"{market_type}|{bookmaker}"
            by_key[key] = {
                "opening_odd": round(opening, 4),
                "current_odd": round(current, 4),
                "movement_pct": round(movement_pct, 4),
                "sharp_move": sharp_flag,
            }

            market_lower = market_type.lower()
            if any(token in market_lower for token in [":1", ":home", "ms1"]):
                home_opening = opening if home_opening is None else home_opening
                home_movement = movement_pct if home_movement is None else min(home_movement, movement_pct)
            if any(token in market_lower for token in [":2", ":away", "ms2"]):
                away_opening = opening if away_opening is None else away_opening

        public_side = "away" if (away_opening is not None and home_opening is not None and away_opening < home_opening) else "home"
        sharp_home = bool(home_movement is not None and home_movement < -5.0 and public_side == "away")
        sharp_side = "home" if sharp_home else "none"

        signal_payload = {
            "match_id": match_id,
            "movement": by_key,
            "public_side": public_side,
            "sharp_money_side": sharp_side,
        }

        try:
            prediction_payload = {
                "match_id": match_id,
                "market_type": "LINE_MOVEMENT",
                "predicted_outcome": "SHARP_HOME" if sharp_home else "NO_CLEAR_SHARP",
                "confidence_score": 70.0 if sharp_home else 50.0,
                "ev_percentage": 0.0,
                "recommended": sharp_home,
            }
            existing = (
                self.supabase.table("predictions")
                .select("id")
                .eq("match_id", match_id)
                .eq("market_type", "LINE_MOVEMENT")
                .limit(1)
                .execute()
            )
            if existing.data:
                self.supabase.table("predictions").update(prediction_payload).eq("id", existing.data[0]["id"]).execute()
            else:
                self.supabase.table("predictions").insert(prediction_payload).execute()
        except Exception:
            logger.exception("Line movement prediction kaydi basarisiz. match_id=%s", match_id)

        return signal_payload

    async def close(self) -> None:
        try:
            await self.http_client.aclose()
        except Exception:
            logger.exception("OddsTrackerService HTTP client close failed.")


_default_tracker = OddsTrackerService()


def get_service() -> OddsTrackerService:
    return _default_tracker


async def get_current_odds(league_id: int) -> Optional[List[Dict[str, Any]]]:
    return await _default_tracker.get_current_odds(league_id)


async def calculate_line_movement(match_id: str) -> Dict[str, Any]:
    return await _default_tracker.calculate_line_movement(match_id)
