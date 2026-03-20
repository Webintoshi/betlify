from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple
from uuid import NAMESPACE_URL, uuid5

from curl_cffi.requests import AsyncSession
from dotenv import load_dotenv
from supabase import Client, create_client

from config import SOFASCORE_TOURNAMENT_ID_SET, SOFASCORE_TOURNAMENT_IDS

logger = logging.getLogger("sofascore")

BASE_URL = "https://api.sofascore.com/api/v1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env", override=True)

SOFASCORE_COOKIE = os.getenv("SOFASCORE_COOKIE", "").strip()
if SOFASCORE_COOKIE:
    HEADERS["Cookie"] = SOFASCORE_COOKIE


def stable_uuid(resource_prefix: str, external_id: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"{resource_prefix}-{external_id}"))


def map_sofascore_status(raw_status: str) -> str:
    value = (raw_status or "").lower()
    if value in {"finished", "ended", "after penalties"}:
        return "finished"
    if value in {"inprogress", "live"}:
        return "live"
    return "scheduled"


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return fallback


def _fractional_to_decimal(value: Any, fallback: float = -1.0) -> float:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    if "/" not in text:
        return _safe_float(text, fallback=fallback)
    left, right = text.split("/", 1)
    numerator = _safe_float(left, fallback=-1.0)
    denominator = _safe_float(right, fallback=-1.0)
    if denominator <= 0:
        return fallback
    return round((numerator / denominator) + 1.0, 4)


def _normalize_name(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


class SofaScoreService:
    def __init__(
        self,
        *,
        supabase_client: Optional[Client] = None,
    ) -> None:
        self.supabase = supabase_client or self._build_supabase_client()
        self._last_request_ts: Optional[float] = None
        self._endpoint_last_call_ts: Dict[str, float] = {}
        self._column_exists_cache: Dict[str, bool] = {}

    @staticmethod
    def _build_supabase_client() -> Optional[Client]:
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not supabase_url or not supabase_service_key or "BURAYA_" in supabase_service_key:
            return None
        try:
            return create_client(supabase_url, supabase_service_key)
        except Exception:
            logger.warning("Supabase client could not be initialized.")
            return None

    def _cache_key(self, endpoint: str, params: Optional[Dict[str, Any]]) -> str:
        normalized = sorted((params or {}).items())
        return f"sofascore:{endpoint}:{normalized}"

    def _has_column(self, table_name: str, column_name: str) -> bool:
        cache_key = f"{table_name}.{column_name}"
        if cache_key in self._column_exists_cache:
            return self._column_exists_cache[cache_key]
        if self.supabase is None:
            self._column_exists_cache[cache_key] = False
            return False

        exists = True
        try:
            self.supabase.table(table_name).select(column_name).limit(1).execute()
        except Exception as exc:
            message = str(exc).lower()
            if "does not exist" in message or "could not find the" in message:
                exists = False
                logger.warning("Column missing, fallback active: %s", cache_key)
        self._column_exists_cache[cache_key] = exists
        return exists

    def _get_cached_payload(self, cache_key: str) -> Optional[Any]:
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
            return row.get("payload")
        except Exception:
            return None

    def _set_cached_payload(self, cache_key: str, payload: Any, ttl_seconds: int) -> None:
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

    async def _enforce_request_spacing(self, endpoint_key: str) -> bool:
        now = monotonic()
        last_endpoint = self._endpoint_last_call_ts.get(endpoint_key)
        if last_endpoint is not None and (now - last_endpoint) < 600:
            logger.info("Ayni endpoint 10 dk icinde tekrar cagirilmadi: %s", endpoint_key)
            return False

        if self._last_request_ts is not None:
            elapsed = now - self._last_request_ts
            if elapsed < 2.0:
                await asyncio.sleep(2.0 - elapsed)

        self._last_request_ts = monotonic()
        self._endpoint_last_call_ts[endpoint_key] = self._last_request_ts
        return True

    async def _fetch(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        await asyncio.sleep(2)
        try:
            async with AsyncSession(impersonate="chrome120") as session:
                response = await session.get(
                    url,
                    params=params,
                    headers=HEADERS,
                    timeout=15,
                )
        except Exception as exc:
            logger.error("Sofascore request failed: %s", exc)
            return None

        if response.status_code == 429:
            logger.warning("Sofascore 429 - 60s bekleniyor")
            await asyncio.sleep(60)
            try:
                async with AsyncSession(impersonate="chrome120") as session:
                    response = await session.get(
                        url,
                        params=params,
                        headers=HEADERS,
                        timeout=15,
                    )
            except Exception as exc:
                logger.error("Sofascore retry failed: %s", exc)
                return None

        if response.status_code == 403:
            logger.error("Sofascore 403: %s", url)
            return None

        if response.status_code >= 400:
            logger.error("HTTP %s: %s", response.status_code, url)
            return None

        try:
            return response.json()
        except Exception:
            logger.error("Sofascore JSON parse hatasi: %s", url)
            return None

    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        ttl_seconds: int = 600,
    ) -> Optional[Any]:
        cache_key = self._cache_key(endpoint, params)
        cached = self._get_cached_payload(cache_key)
        if cached is not None:
            return cached

        endpoint_key = f"{endpoint}?{sorted((params or {}).items())}"
        if not await self._enforce_request_spacing(endpoint_key):
            return None

        url = f"{BASE_URL}{endpoint}"
        payload = await self._fetch(url, params=params)
        if payload is None:
            return None

        self._set_cached_payload(cache_key, payload, ttl_seconds)
        return payload

    def _resolve_internal_match(self, sofascore_event_id: int) -> Optional[Dict[str, Any]]:
        if self.supabase is None:
            return None
        column_available = self._has_column("matches", "sofascore_id")
        fallback_match_id = stable_uuid("sofascore-event", sofascore_event_id)
        try:
            query = self.supabase.table("matches").select("id,status,home_team_id,away_team_id").limit(1)
            if column_available:
                result = query.eq("sofascore_id", sofascore_event_id).execute()
            else:
                result = query.eq("id", fallback_match_id).execute()
            rows = result.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    def _resolve_match_by_id(self, match_id: str) -> Optional[Dict[str, Any]]:
        if self.supabase is None:
            return None
        select_columns = "id,status,home_team_id,away_team_id,match_date,league"
        if self._has_column("matches", "sofascore_id"):
            select_columns += ",sofascore_id"
        try:
            result = self.supabase.table("matches").select(select_columns).eq("id", match_id).limit(1).execute()
            rows = result.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    def _resolve_match_teams(self, match_row: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if self.supabase is None:
            return None, None
        has_sofascore_column = self._has_column("teams", "sofascore_id")
        select_columns = "id,name,country,league"
        if has_sofascore_column:
            select_columns += ",sofascore_id"
        try:
            result = (
                self.supabase.table("teams")
                .select(select_columns)
                .in_("id", [match_row.get("home_team_id"), match_row.get("away_team_id")])
                .execute()
            )
            rows = result.data or []
            by_id = {row.get("id"): row for row in rows if row.get("id")}
            return by_id.get(match_row.get("home_team_id")), by_id.get(match_row.get("away_team_id"))
        except Exception:
            return None, None

    def _latest_match_for_team(self, team_uuid: str) -> Optional[str]:
        if self.supabase is None:
            return None
        try:
            result = (
                self.supabase.table("matches")
                .select("id")
                .or_(f"home_team_id.eq.{team_uuid},away_team_id.eq.{team_uuid}")
                .order("match_date", desc=True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0].get("id") if rows else None
        except Exception:
            return None

    @staticmethod
    def _event_goals(event: Dict[str, Any]) -> Tuple[int, int]:
        home_score = event.get("homeScore", {}) if isinstance(event.get("homeScore"), dict) else {}
        away_score = event.get("awayScore", {}) if isinstance(event.get("awayScore"), dict) else {}
        home_goals = _safe_int(
            home_score.get("current")
            if home_score.get("current") is not None
            else home_score.get("normaltime"),
            fallback=0,
        )
        away_goals = _safe_int(
            away_score.get("current")
            if away_score.get("current") is not None
            else away_score.get("normaltime"),
            fallback=0,
        )
        return home_goals, away_goals

    @staticmethod
    def _event_team_side(event: Dict[str, Any], sofascore_team_id: int) -> Optional[str]:
        home = event.get("homeTeam", {}) if isinstance(event.get("homeTeam"), dict) else {}
        away = event.get("awayTeam", {}) if isinstance(event.get("awayTeam"), dict) else {}
        home_id = _safe_int(home.get("id"))
        away_id = _safe_int(away.get("id"))
        if sofascore_team_id == home_id:
            return "home"
        if sofascore_team_id == away_id:
            return "away"
        return None

    @staticmethod
    def _result_points(team_goals: int, opp_goals: int) -> float:
        if team_goals > opp_goals:
            return 1.0
        if team_goals == opp_goals:
            return 0.5
        return 0.0

    def _ensure_match_from_event(self, event: Dict[str, Any]) -> Optional[str]:
        if self.supabase is None or not isinstance(event, dict):
            return None
        event_id = _safe_int(event.get("id"))
        if event_id <= 0:
            return None

        existing = self._resolve_internal_match(event_id)
        if existing and existing.get("id"):
            return str(existing["id"])

        tournament = event.get("tournament", {}) if isinstance(event.get("tournament"), dict) else {}
        unique_tournament = tournament.get("uniqueTournament", {}) if isinstance(tournament.get("uniqueTournament"), dict) else {}
        league_name = str(unique_tournament.get("name") or tournament.get("name") or "Unknown")
        country_name = str(tournament.get("category", {}).get("name", "Unknown")) if isinstance(tournament.get("category"), dict) else "Unknown"

        home_team = event.get("homeTeam", {}) if isinstance(event.get("homeTeam"), dict) else {}
        away_team = event.get("awayTeam", {}) if isinstance(event.get("awayTeam"), dict) else {}
        home_uuid = self._ensure_team(home_team, league_name, country_name)
        away_uuid = self._ensure_team(away_team, league_name, country_name)
        if not home_uuid or not away_uuid:
            return None

        start_ts = _safe_int(event.get("startTimestamp"))
        match_date = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat() if start_ts > 0 else datetime.now(timezone.utc).isoformat()
        status = map_sofascore_status(str(event.get("status", {}).get("type", "scheduled")))
        season = str(event.get("season", {}).get("year", ""))
        home_goals, away_goals = self._event_goals(event)
        home_period1 = _safe_int(event.get("homeScore", {}).get("period1") if isinstance(event.get("homeScore"), dict) else 0)
        away_period1 = _safe_int(event.get("awayScore", {}).get("period1") if isinstance(event.get("awayScore"), dict) else 0)

        match_record = {
            "id": stable_uuid("sofascore-event", event_id),
            "home_team_id": home_uuid,
            "away_team_id": away_uuid,
            "league": league_name,
            "match_date": match_date,
            "status": status,
            "season": season,
        }
        if self._has_column("matches", "ht_home"):
            match_record["ht_home"] = home_period1
        if self._has_column("matches", "ht_away"):
            match_record["ht_away"] = away_period1
        if self._has_column("matches", "ft_home"):
            match_record["ft_home"] = home_goals
        if self._has_column("matches", "ft_away"):
            match_record["ft_away"] = away_goals
        if self._has_column("matches", "sofascore_id"):
            match_record["sofascore_id"] = event_id

        try:
            if self._has_column("matches", "sofascore_id"):
                self.supabase.table("matches").upsert(match_record, on_conflict="sofascore_id").execute()
            else:
                self.supabase.table("matches").upsert(match_record, on_conflict="id").execute()
            return str(match_record["id"])
        except Exception:
            logger.exception("Failed to ensure match for event_id=%s", event_id)
            return None

    def _ensure_team(self, team_payload: Dict[str, Any], league_name: str, country_name: str) -> Optional[str]:
        if self.supabase is None:
            return None
        sofascore_team_id = _safe_int(team_payload.get("id"))
        if sofascore_team_id <= 0:
            return None

        team_uuid = stable_uuid("sofascore-team", sofascore_team_id)
        has_sofascore_column = self._has_column("teams", "sofascore_id")
        record = {
            "id": team_uuid,
            "name": team_payload.get("name", f"Team {sofascore_team_id}"),
            "league": league_name or "Unknown",
            "country": country_name or "Unknown",
            "market_value": 0,
        }
        if has_sofascore_column:
            record["sofascore_id"] = sofascore_team_id
        try:
            if has_sofascore_column:
                self.supabase.table("teams").upsert(record, on_conflict="sofascore_id").execute()
            else:
                self.supabase.table("teams").upsert(record, on_conflict="id").execute()
            return team_uuid
        except Exception:
            try:
                self.supabase.table("teams").upsert(record, on_conflict="id").execute()
                return team_uuid
            except Exception:
                logger.exception("Team save failed. sofascore_team_id=%s", sofascore_team_id)
                return None

    async def get_scheduled_events(self, date: str) -> Optional[List[Dict[str, Any]]]:
        payload = await self._request(f"/sport/football/scheduled-events/{date}", ttl_seconds=600)
        if payload is None:
            return None

        events = payload.get("events", []) if isinstance(payload, dict) else []
        if not isinstance(events, list):
            return []
        saved_events: List[Dict[str, Any]] = []
        has_match_sofascore_column = self._has_column("matches", "sofascore_id")

        for event in events:
            if not isinstance(event, dict):
                continue
            tournament = event.get("tournament", {}) if isinstance(event.get("tournament"), dict) else {}
            unique_tournament = tournament.get("uniqueTournament", {}) if isinstance(tournament.get("uniqueTournament"), dict) else {}
            tournament_id = _safe_int(unique_tournament.get("id"))
            if tournament_id not in SOFASCORE_TOURNAMENT_ID_SET:
                continue

            event_id = _safe_int(event.get("id"))
            if event_id <= 0:
                continue

            home_team = event.get("homeTeam", {}) if isinstance(event.get("homeTeam"), dict) else {}
            away_team = event.get("awayTeam", {}) if isinstance(event.get("awayTeam"), dict) else {}
            league_name = SOFASCORE_TOURNAMENT_IDS.get(tournament_id, unique_tournament.get("name", "Unknown"))
            country = str(tournament.get("category", {}).get("name", "Unknown")) if isinstance(tournament.get("category"), dict) else "Unknown"

            home_uuid = self._ensure_team(home_team, league_name, country)
            away_uuid = self._ensure_team(away_team, league_name, country)
            if not home_uuid or not away_uuid:
                continue

            start_ts = _safe_int(event.get("startTimestamp"))
            match_date = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat() if start_ts > 0 else None
            status = map_sofascore_status(str(event.get("status", {}).get("type", "notstarted")))

            match_record = {
                "id": stable_uuid("sofascore-event", event_id),
                "home_team_id": home_uuid,
                "away_team_id": away_uuid,
                "league": league_name,
                "match_date": match_date,
                "status": status,
                "season": str(event.get("season", {}).get("year", "")),
            }
            if has_match_sofascore_column:
                match_record["sofascore_id"] = event_id
            try:
                if has_match_sofascore_column:
                    self.supabase.table("matches").upsert(match_record, on_conflict="sofascore_id").execute()
                else:
                    self.supabase.table("matches").upsert(match_record, on_conflict="id").execute()
                saved_events.append(event)
            except Exception:
                try:
                    self.supabase.table("matches").upsert(match_record, on_conflict="id").execute()
                    saved_events.append(event)
                except Exception:
                    logger.exception("Match save failed. sofascore_event_id=%s", event_id)

        logger.info("%s icin %s mac cekildi", date, len(saved_events))
        return saved_events

    def _extract_stat_values(self, payload: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        extracted: Dict[str, Dict[str, float]] = {}

        def crawl(node: Any) -> None:
            if isinstance(node, dict):
                label = str(node.get("name") or node.get("key") or "").strip().lower()
                home_val = node.get("home") if "home" in node else node.get("homeValue")
                away_val = node.get("away") if "away" in node else node.get("awayValue")
                if label and home_val is not None and away_val is not None:
                    extracted[label] = {
                        "home": _safe_float(home_val),
                        "away": _safe_float(away_val),
                    }
                for value in node.values():
                    crawl(value)
            elif isinstance(node, list):
                for item in node:
                    crawl(item)

        crawl(payload)
        return extracted

    async def get_event_statistics(self, event_id: int) -> Optional[Dict[str, Any]]:
        payload = await self._request(f"/event/{event_id}/statistics", ttl_seconds=600)
        if payload is None:
            return None
        match = self._resolve_internal_match(event_id)
        if match is None or self.supabase is None:
            return payload

        stats = self._extract_stat_values(payload if isinstance(payload, dict) else {})
        home_possession = stats.get("ball possession", {}).get("home", 0.0)
        away_possession = stats.get("ball possession", {}).get("away", 0.0)
        home_shots = stats.get("total shots", {}).get("home", 0.0)
        away_shots = stats.get("total shots", {}).get("away", 0.0)
        home_sot = stats.get("shots on target", {}).get("home", 0.0)
        away_sot = stats.get("shots on target", {}).get("away", 0.0)
        home_xg = stats.get("expected goals", {}).get("home", 0.0)
        away_xg = stats.get("expected goals", {}).get("away", 0.0)

        records = [
            {
                "team_id": match["home_team_id"],
                "match_id": match["id"],
                "goals_scored": 0,
                "goals_conceded": 0,
                "xg_for": home_xg,
                "xg_against": away_xg,
                "shots": int(round(home_shots)),
                "shots_on_target": int(round(home_sot)),
                "possession": home_possession,
                "form_last6": 0.0,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "team_id": match["away_team_id"],
                "match_id": match["id"],
                "goals_scored": 0,
                "goals_conceded": 0,
                "xg_for": away_xg,
                "xg_against": home_xg,
                "shots": int(round(away_shots)),
                "shots_on_target": int(round(away_sot)),
                "possession": away_possession,
                "form_last6": 0.0,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        for row in records:
            try:
                self.supabase.table("team_stats").upsert(row, on_conflict="team_id,match_id").execute()
            except Exception:
                logger.exception("event statistics save failed. event_id=%s", event_id)
        logger.info("event_id=%s istatistikler guncellendi", event_id)
        return payload

    def _upsert_odds_row(
        self,
        *,
        match_id: str,
        market_type: str,
        bookmaker: str,
        odd_value: float,
        is_finished: bool,
    ) -> None:
        if self.supabase is None:
            return
        try:
            existing = (
                self.supabase.table("odds_history")
                .select("id,opening_odd,current_odd")
                .eq("match_id", match_id)
                .eq("bookmaker", bookmaker)
                .eq("market_type", market_type)
                .limit(1)
                .execute()
            )
            rows = existing.data or []
            now_iso = datetime.now(timezone.utc).isoformat()
            if rows:
                row = rows[0]
                opening = _safe_float(row.get("opening_odd") or row.get("current_odd"), fallback=odd_value)
                payload = {"opening_odd": opening, "current_odd": odd_value, "recorded_at": now_iso}
                if is_finished:
                    payload["closing_odd"] = odd_value
                self.supabase.table("odds_history").update(payload).eq("id", row["id"]).execute()
            else:
                payload = {
                    "match_id": match_id,
                    "market_type": market_type,
                    "bookmaker": bookmaker,
                    "opening_odd": odd_value,
                    "current_odd": odd_value,
                    "closing_odd": odd_value if is_finished else None,
                    "recorded_at": now_iso,
                }
                self.supabase.table("odds_history").insert(payload).execute()
        except Exception:
            logger.exception("odds_history save failed. match_id=%s market=%s", match_id, market_type)

    async def get_event_odds(self, event_id: int) -> Optional[Dict[str, Any]]:
        payload = await self._request(f"/event/{event_id}/odds/1/all", ttl_seconds=600)
        if payload is None:
            return None
        match = self._resolve_internal_match(event_id)
        if match is None:
            return payload

        is_finished = str(match.get("status", "")).lower() == "finished"
        markets = payload.get("markets", []) if isinstance(payload, dict) else []
        if isinstance(markets, list):
            for market in markets:
                if not isinstance(market, dict):
                    continue
                market_name = str(market.get("marketName") or market.get("name") or "Unknown")
                outcomes = market.get("choices") if isinstance(market.get("choices"), list) else market.get("outcomes", [])
                for outcome in outcomes if isinstance(outcomes, list) else []:
                    if not isinstance(outcome, dict):
                        continue
                    odd = _safe_float(outcome.get("odds"), fallback=-1.0)
                    if odd <= 0:
                        odd = _safe_float(outcome.get("decimalValue"), fallback=-1.0)
                    if odd <= 0:
                        odd = _fractional_to_decimal(outcome.get("fractionalValue"), fallback=-1.0)
                    if odd <= 0:
                        odd = _fractional_to_decimal(outcome.get("initialFractionalValue"), fallback=-1.0)
                    if odd <= 0:
                        continue
                    outcome_name = str(outcome.get("name") or outcome.get("choice") or "Unknown").strip()
                    market_group = str(market.get("marketGroup") or "").strip().upper()
                    if market_group == "1X2":
                        normalized = {"1": "Home", "X": "Draw", "2": "Away"}.get(outcome_name.upper(), outcome_name)
                        market_type = f"1X2:{normalized}"
                    else:
                        market_type = f"{market_name}:{outcome_name}"
                    self._upsert_odds_row(
                        match_id=str(match["id"]),
                        market_type=market_type,
                        bookmaker="sofascore",
                        odd_value=odd,
                        is_finished=is_finished,
                    )
        return payload

    async def get_team_performance(self, team_id: int) -> Optional[Dict[str, Any]]:
        payload = await self._request(f"/team/{team_id}/performance", ttl_seconds=1800)
        if payload is None:
            return None
        if self.supabase is None:
            return payload

        try:
            if self._has_column("teams", "sofascore_id"):
                team_result = (
                    self.supabase.table("teams")
                    .select("id")
                    .eq("sofascore_id", team_id)
                    .limit(1)
                    .execute()
                )
                rows = team_result.data or []
                if not rows:
                    return payload
                team_uuid = rows[0]["id"]
            else:
                team_uuid = stable_uuid("sofascore-team", team_id)
            match_id = self._latest_match_for_team(team_uuid)
            if not match_id:
                return payload

            performance = payload.get("performance", {}) if isinstance(payload, dict) else {}
            form_score = _safe_float(performance.get("value"), fallback=0.0)
            form_last6 = max(0.0, min(1.0, form_score / 100.0)) if form_score > 1 else form_score

            row = {
                "team_id": team_uuid,
                "match_id": match_id,
                "goals_scored": 0,
                "goals_conceded": 0,
                "xg_for": 0.0,
                "xg_against": 0.0,
                "shots": 0,
                "shots_on_target": 0,
                "possession": 0.0,
                "form_last6": form_last6,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.supabase.table("team_stats").upsert(row, on_conflict="team_id,match_id").execute()
        except Exception:
            logger.exception("team performance save failed. team_id=%s", team_id)
        return payload

    @staticmethod
    def _name_matches(left: str, right: str) -> bool:
        l_norm = _normalize_name(left)
        r_norm = _normalize_name(right)
        if not l_norm or not r_norm:
            return False
        return l_norm == r_norm or l_norm in r_norm or r_norm in l_norm

    async def _resolve_sofascore_team_ids_for_match(self, match_id: str) -> Optional[Dict[str, int]]:
        match_row = self._resolve_match_by_id(match_id)
        if not match_row:
            return None
        home_row, away_row = self._resolve_match_teams(match_row)
        if not home_row or not away_row:
            return None

        has_team_sofascore = self._has_column("teams", "sofascore_id")
        has_match_sofascore = self._has_column("matches", "sofascore_id")
        event_id = _safe_int(match_row.get("sofascore_id")) if has_match_sofascore else 0

        home_sofascore = _safe_int(home_row.get("sofascore_id")) if has_team_sofascore else 0
        away_sofascore = _safe_int(away_row.get("sofascore_id")) if has_team_sofascore else 0
        if home_sofascore > 0 and away_sofascore > 0:
            return {"event_id": event_id, "home_sofascore_id": home_sofascore, "away_sofascore_id": away_sofascore}

        if event_id > 0:
            event_payload = await self._request(f"/event/{event_id}", ttl_seconds=1800)
            event = event_payload.get("event", {}) if isinstance(event_payload, dict) else {}
            if isinstance(event, dict):
                event_home = _safe_int(event.get("homeTeam", {}).get("id") if isinstance(event.get("homeTeam"), dict) else 0)
                event_away = _safe_int(event.get("awayTeam", {}).get("id") if isinstance(event.get("awayTeam"), dict) else 0)
                if event_home > 0 and event_away > 0:
                    if has_team_sofascore:
                        try:
                            self.supabase.table("teams").update({"sofascore_id": event_home}).eq("id", match_row["home_team_id"]).execute()
                            self.supabase.table("teams").update({"sofascore_id": event_away}).eq("id", match_row["away_team_id"]).execute()
                        except Exception:
                            logger.exception("teams sofascore_id update failed. match_id=%s", match_id)
                    return {"event_id": event_id, "home_sofascore_id": event_home, "away_sofascore_id": event_away}

        match_date = str(match_row.get("match_date", ""))
        match_day = match_date[:10]
        if len(match_day) != 10:
            return None
        events = await self.get_scheduled_events(match_day)
        if not isinstance(events, list):
            return None

        home_name = str(home_row.get("name", ""))
        away_name = str(away_row.get("name", ""))
        for event in events:
            if not isinstance(event, dict):
                continue
            event_home = event.get("homeTeam", {}) if isinstance(event.get("homeTeam"), dict) else {}
            event_away = event.get("awayTeam", {}) if isinstance(event.get("awayTeam"), dict) else {}
            event_home_name = str(event_home.get("name", ""))
            event_away_name = str(event_away.get("name", ""))

            direct_match = self._name_matches(home_name, event_home_name) and self._name_matches(away_name, event_away_name)
            reverse_match = self._name_matches(home_name, event_away_name) and self._name_matches(away_name, event_home_name)
            if not (direct_match or reverse_match):
                continue

            event_id = _safe_int(event.get("id"))
            home_id = _safe_int(event_home.get("id"))
            away_id = _safe_int(event_away.get("id"))
            if event_id <= 0 or home_id <= 0 or away_id <= 0:
                continue

            if reverse_match:
                home_id, away_id = away_id, home_id

            if has_match_sofascore:
                try:
                    self.supabase.table("matches").update({"sofascore_id": event_id}).eq("id", match_id).execute()
                except Exception:
                    logger.exception("matches sofascore_id update failed. match_id=%s", match_id)
            if has_team_sofascore:
                try:
                    self.supabase.table("teams").update({"sofascore_id": home_id}).eq("id", match_row["home_team_id"]).execute()
                    self.supabase.table("teams").update({"sofascore_id": away_id}).eq("id", match_row["away_team_id"]).execute()
                except Exception:
                    logger.exception("teams sofascore_id update failed from scheduled events. match_id=%s", match_id)
            return {"event_id": event_id, "home_sofascore_id": home_id, "away_sofascore_id": away_id}

        return None

    async def populate_team_stats_from_history(self, team_id: str, sofascore_team_id: int) -> Optional[Dict[str, Any]]:
        if self.supabase is None:
            return None
        if not team_id or sofascore_team_id <= 0:
            return None

        payload = await self._request(f"/team/{sofascore_team_id}/events/last/0", ttl_seconds=3600)
        if payload is None:
            return None
        events = payload.get("events", []) if isinstance(payload, dict) else []
        if not isinstance(events, list) or not events:
            return {"team_id": team_id, "sofascore_team_id": sofascore_team_id, "updated_rows": 0}

        finished_events: List[Dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            status_type = str(event.get("status", {}).get("type", "")).lower() if isinstance(event.get("status"), dict) else ""
            if status_type in {"finished", "ended"}:
                finished_events.append(event)
            if len(finished_events) >= 10:
                break

        if not finished_events:
            return {"team_id": team_id, "sofascore_team_id": sofascore_team_id, "updated_rows": 0}

        collected: List[Dict[str, Any]] = []
        result_points: List[float] = []
        xg_values: List[float] = []
        has_xg_rolling_column = self._has_column("team_stats", "xg_rolling_10")

        for event in finished_events:
            event_id = _safe_int(event.get("id"))
            if event_id <= 0:
                continue
            team_side = self._event_team_side(event, sofascore_team_id)
            if team_side is None:
                continue

            match_id = self._ensure_match_from_event(event)
            if not match_id:
                continue

            stats_payload = await self._request(f"/event/{event_id}/statistics", ttl_seconds=7200)
            stats_map = self._extract_stat_values(stats_payload if isinstance(stats_payload, dict) else {})

            home_goals, away_goals = self._event_goals(event)
            if team_side == "home":
                goals_for = home_goals
                goals_against = away_goals
                side_key = "home"
                opp_key = "away"
            else:
                goals_for = away_goals
                goals_against = home_goals
                side_key = "away"
                opp_key = "home"

            xg_for = stats_map.get("expected goals", {}).get(side_key, 0.0)
            xg_against = stats_map.get("expected goals", {}).get(opp_key, 0.0)
            shots = stats_map.get("total shots", {}).get(side_key, 0.0)
            shots_on_target = stats_map.get("shots on target", {}).get(side_key, 0.0)
            possession = stats_map.get("ball possession", {}).get(side_key, 0.0)

            result_points.append(self._result_points(goals_for, goals_against))
            xg_values.append(float(xg_for))

            row = {
                "team_id": team_id,
                "match_id": match_id,
                "goals_scored": goals_for,
                "goals_conceded": goals_against,
                "xg_for": round(float(xg_for), 3),
                "xg_against": round(float(xg_against), 3),
                "shots": int(round(shots)),
                "shots_on_target": int(round(shots_on_target)),
                "possession": round(float(possession), 2),
            }
            collected.append(row)

        if not collected:
            return {"team_id": team_id, "sofascore_team_id": sofascore_team_id, "updated_rows": 0}

        last6 = result_points[:6]
        form_last6 = round(sum(last6) / len(last6), 3) if last6 else 0.0
        xg_rolling_10 = round(sum(xg_values) / len(xg_values), 3) if xg_values else 0.0

        updated = 0
        for row in collected:
            payload_row = {
                **row,
                "form_last6": form_last6,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if has_xg_rolling_column:
                payload_row["xg_rolling_10"] = xg_rolling_10
            try:
                self.supabase.table("team_stats").upsert(payload_row, on_conflict="team_id,match_id").execute()
                updated += 1
            except Exception:
                logger.exception("team_stats populate failed. team_id=%s match_id=%s", team_id, row.get("match_id"))

        logger.info(
            "team_stats populate tamamlandi. team_id=%s sofascore_team_id=%s rows=%s form_last6=%s xg_rolling_10=%s",
            team_id,
            sofascore_team_id,
            updated,
            form_last6,
            xg_rolling_10,
        )
        return {
            "team_id": team_id,
            "sofascore_team_id": sofascore_team_id,
            "updated_rows": updated,
            "form_last6": form_last6,
            "xg_rolling_10": xg_rolling_10,
        }

    async def populate_team_stats_for_match(self, match_id: str) -> Optional[Dict[str, Any]]:
        mapping = await self._resolve_sofascore_team_ids_for_match(match_id)
        if not mapping:
            return None
        match_row = self._resolve_match_by_id(match_id)
        if not match_row:
            return None

        home_team_id = str(match_row.get("home_team_id") or "")
        away_team_id = str(match_row.get("away_team_id") or "")
        if not home_team_id or not away_team_id:
            return None

        home_stats = await self.populate_team_stats_from_history(home_team_id, _safe_int(mapping.get("home_sofascore_id")))
        away_stats = await self.populate_team_stats_from_history(away_team_id, _safe_int(mapping.get("away_sofascore_id")))
        return {
            "match_id": match_id,
            "event_id": _safe_int(mapping.get("event_id")),
            "home": home_stats,
            "away": away_stats,
        }

    async def get_event_lineups(self, event_id: int) -> Optional[Dict[str, Any]]:
        payload = await self._request(f"/event/{event_id}/lineups", ttl_seconds=600)
        if payload is None:
            return None
        match = self._resolve_internal_match(event_id)
        if match is None or self.supabase is None:
            return payload

        home = payload.get("home", {}) if isinstance(payload, dict) else {}
        away = payload.get("away", {}) if isinstance(payload, dict) else {}
        home_missing = len(home.get("missingPlayers", [])) if isinstance(home.get("missingPlayers"), list) else 0
        away_missing = len(away.get("missingPlayers", [])) if isinstance(away.get("missingPlayers"), list) else 0

        confidence = max(35.0, 80.0 - (home_missing + away_missing) * 3.0)
        pred_payload = {
            "match_id": match["id"],
            "market_type": "SOFASCORE_LINEUP_SIGNAL",
            "predicted_outcome": "LINEUP_OK" if (home_missing + away_missing) <= 4 else "LINEUP_RISK",
            "confidence_score": confidence,
            "ev_percentage": 0.0,
            "recommended": confidence >= 60.0,
        }
        try:
            existing = (
                self.supabase.table("predictions")
                .select("id")
                .eq("match_id", match["id"])
                .eq("market_type", "SOFASCORE_LINEUP_SIGNAL")
                .limit(1)
                .execute()
            )
            if existing.data:
                self.supabase.table("predictions").update(pred_payload).eq("id", existing.data[0]["id"]).execute()
            else:
                self.supabase.table("predictions").insert(pred_payload).execute()
        except Exception:
            logger.exception("lineup prediction save failed. event_id=%s", event_id)
        return payload

    async def get_event_pregame_form(self, event_id: int) -> Optional[Dict[str, Any]]:
        payload = await self._request(f"/event/{event_id}/pregame-form", ttl_seconds=600)
        if payload is None:
            return None
        match = self._resolve_internal_match(event_id)
        if match is None or self.supabase is None:
            return payload

        def form_points(raw_form: Any) -> int:
            if not isinstance(raw_form, list):
                return 0
            points = 0
            for item in raw_form[:5]:
                flag = str(item).upper()
                if flag == "W":
                    points += 3
                elif flag == "D":
                    points += 1
            return points

        home = payload.get("homeTeam", {}) if isinstance(payload, dict) else {}
        away = payload.get("awayTeam", {}) if isinstance(payload, dict) else {}
        home_points = form_points(home.get("form"))
        away_points = form_points(away.get("form"))
        gap = home_points - away_points
        confidence = max(40.0, min(85.0, 55.0 + abs(gap) * 4.0))
        predicted = "HOME_FORM_EDGE" if gap > 0 else "AWAY_FORM_EDGE" if gap < 0 else "FORM_BALANCED"

        row = {
            "match_id": match["id"],
            "market_type": "SOFASCORE_PREGAME_FORM",
            "predicted_outcome": predicted,
            "confidence_score": confidence,
            "ev_percentage": 0.0,
            "recommended": confidence >= 60.0,
        }
        try:
            existing = (
                self.supabase.table("predictions")
                .select("id")
                .eq("match_id", match["id"])
                .eq("market_type", "SOFASCORE_PREGAME_FORM")
                .limit(1)
                .execute()
            )
            if existing.data:
                self.supabase.table("predictions").update(row).eq("id", existing.data[0]["id"]).execute()
            else:
                self.supabase.table("predictions").insert(row).execute()
        except Exception:
            logger.exception("pregame form prediction save failed. event_id=%s", event_id)
        return payload

    async def get_h2h(self, sofascore_event_id: int) -> Optional[Dict[str, Any]]:
        base_event_payload = await self._request(f"/event/{sofascore_event_id}", ttl_seconds=1800)
        base_event = base_event_payload.get("event", {}) if isinstance(base_event_payload, dict) else {}
        focus_home_team = _safe_int(base_event.get("homeTeam", {}).get("id") if isinstance(base_event.get("homeTeam"), dict) else 0)

        payload = await self._request(f"/event/{sofascore_event_id}/h2h/events", ttl_seconds=1200)
        events = payload.get("events", []) if isinstance(payload, dict) else []

        home_wins = 0
        away_wins = 0
        draws = 0
        weighted_home = 0.0
        weighted_total = 0.0

        if isinstance(events, list) and events:
            for item in events[:10]:
                if not isinstance(item, dict):
                    continue
                if focus_home_team <= 0:
                    continue
                side = self._event_team_side(item, focus_home_team)
                if side is None:
                    continue

                team_goals_home, team_goals_away = self._event_goals(item)
                if side == "home":
                    focus_goals = team_goals_home
                    opp_goals = team_goals_away
                else:
                    focus_goals = team_goals_away
                    opp_goals = team_goals_home

                tournament = item.get("tournament", {}) if isinstance(item.get("tournament"), dict) else {}
                unique = tournament.get("uniqueTournament", {}) if isinstance(tournament.get("uniqueTournament"), dict) else {}
                tournament_id = _safe_int(unique.get("id"))
                is_tournament = bool(item.get("isTournament", False)) or (tournament_id > 0 and tournament_id not in SOFASCORE_TOURNAMENT_ID_SET)
                weight = 0.3 if is_tournament else 0.7
                weighted_total += weight

                if focus_goals > opp_goals:
                    home_wins += 1
                    weighted_home += weight
                elif focus_goals < opp_goals:
                    away_wins += 1
                else:
                    draws += 1

            ratio = round(weighted_home / weighted_total, 4) if weighted_total > 0 else 0.5
            return {
                "home_wins": home_wins,
                "away_wins": away_wins,
                "draws": draws,
                "ratio": ratio,
            }

        summary_payload = await self._request(f"/event/{sofascore_event_id}/h2h", ttl_seconds=1200)
        team_duel = summary_payload.get("teamDuel", {}) if isinstance(summary_payload, dict) else {}
        home_wins = _safe_int(team_duel.get("homeWins"))
        away_wins = _safe_int(team_duel.get("awayWins"))
        draws = _safe_int(team_duel.get("draws"))
        total = home_wins + away_wins + draws
        ratio = round(home_wins / total, 4) if total > 0 else 0.5
        return {
            "home_wins": home_wins,
            "away_wins": away_wins,
            "draws": draws,
            "ratio": ratio,
        }

    async def close(self) -> None:
        return


_default_service = SofaScoreService()


def get_service() -> SofaScoreService:
    return _default_service


async def get_scheduled_events(date: str) -> Optional[List[Dict[str, Any]]]:
    return await _default_service.get_scheduled_events(date)


async def get_event_statistics(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_event_statistics(event_id)


async def get_event_odds(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_event_odds(event_id)


async def get_team_performance(team_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_team_performance(team_id)


async def populate_team_stats_from_history(team_id: str, sofascore_team_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.populate_team_stats_from_history(team_id, sofascore_team_id)


async def populate_team_stats_for_match(match_id: str) -> Optional[Dict[str, Any]]:
    return await _default_service.populate_team_stats_for_match(match_id)


async def get_event_lineups(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_event_lineups(event_id)


async def get_event_pregame_form(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_event_pregame_form(event_id)


async def get_h2h(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_h2h(event_id)
