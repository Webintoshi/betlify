from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import NAMESPACE_URL, uuid5

import httpx
from dotenv import load_dotenv
from supabase import Client, create_client

from config import DEFAULT_SEASON, TRACKED_LEAGUE_IDS, TRACKED_LEAGUES

logger = logging.getLogger(__name__)

API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"
CALENDAR_YEAR_LEAGUE_IDS = {4, 5, 6, 960}

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env", override=True)


def stable_uuid(resource_prefix: str, external_id: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"{resource_prefix}-{external_id}"))


def _normalize_name(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _canonical_country_name(value: Any) -> str:
    text = str(value or "").strip()
    normalized = _normalize_name(text)
    aliases = {
        "turkey": "Türkiye",
        "turkiye": "Türkiye",
    }
    if normalized in aliases:
        return aliases[normalized]
    return text or "Unknown"


def _canonical_league_name(value: Any) -> str:
    text = str(value or "").strip()
    normalized = _normalize_name(text)
    aliases = {
        "turkiyesuperlig": "Trendyol Süper Lig",
        "turkiyesuperleague": "Trendyol Süper Lig",
        "turkeysuperlig": "Trendyol Süper Lig",
        "superlig": "Trendyol Süper Lig",
        "trendyolsuperlig": "Trendyol Süper Lig",
        "turkiye1lig": "Trendyol 1. Lig",
        "tff1lig": "Trendyol 1. Lig",
        "trendyol1lig": "Trendyol 1. Lig",
    }
    if normalized in aliases:
        return aliases[normalized]
    return text or "Unknown"


def map_fixture_status(raw_status: str) -> str:
    normalized = (raw_status or "").upper()
    if normalized in {"FT", "AET", "PEN", "CANC", "PST"}:
        return "finished"
    if normalized in {"1H", "2H", "HT", "LIVE", "ET"}:
        return "live"
    return "scheduled"


def resolve_season_for_date(date_value: str, league_id: Optional[int] = None, default: int = DEFAULT_SEASON) -> int:
    text = str(date_value or "").strip()
    if not text:
        return int(default)

    normalized = text.replace("Z", "+00:00")
    parsed: Optional[datetime] = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            parsed = None

    if parsed is None:
        return int(default)

    league = int(league_id or 0)
    if league in CALENDAR_YEAR_LEAGUE_IDS:
        return int(parsed.year)

    # Avrupa formati sezonu: Temmuz-Haziran -> mart 2026 = 2025 sezonu.
    return int(parsed.year if parsed.month >= 7 else parsed.year - 1)


def _parse_percent(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return 0.0


class ApiFootballService:
    def __init__(
        self,
        *,
        supabase_client: Optional[Client] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.api_key = os.getenv("API_FOOTBALL_KEY", "")
        self.supabase = supabase_client or self._build_supabase_client()
        self.http_client = http_client or httpx.AsyncClient(timeout=10.0)
        self.requests_remaining: Optional[int] = None
        self.requests_limit: Optional[int] = None

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
            if value is None:
                return fallback
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _safe_float(value: Any, fallback: float = 0.0) -> float:
        try:
            if value is None:
                return fallback
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _resolve_team_uuid_by_api_team_id(self, api_team_id: int) -> Optional[str]:
        if self.supabase is None or api_team_id <= 0:
            return None
        try:
            result = (
                self.supabase.table("teams")
                .select("id")
                .eq("api_team_id", api_team_id)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if not rows:
                return None
            return str(rows[0].get("id") or "") or None
        except Exception:
            return None

    def _resolve_canonical_team_id(
        self,
        *,
        team_name: str,
        league_name: str,
        country_name: str,
        api_team_id: int,
    ) -> str:
        resolved_by_api = self._resolve_team_uuid_by_api_team_id(api_team_id)
        if resolved_by_api:
            return resolved_by_api
        if self.supabase is None:
            return stable_uuid("api-football-team", api_team_id)

        normalized_name = _normalize_name(team_name)
        normalized_league_name = _canonical_league_name(league_name)
        normalized_country_name = _canonical_country_name(country_name)
        candidates: List[Dict[str, Any]] = []
        try:
            query = (
                self.supabase.table("teams")
                .select("id,name,league,country,created_at,api_team_id,sofascore_id,logo_url,coach_name")
                .eq("league", normalized_league_name)
                .limit(300)
            )
            if normalized_country_name != "Unknown":
                query = query.eq("country", normalized_country_name)
            result = query.execute()
            candidates = result.data or []
        except Exception:
            candidates = []

        exact_candidates = [row for row in candidates if _normalize_name(row.get("name")) == normalized_name]
        if exact_candidates:
            exact_candidates.sort(
                key=lambda row: (
                    0 if self._safe_int(row.get("sofascore_id")) > 0 else 1,
                    0 if str(row.get("country") or "").strip() not in {"", "Unknown"} else 1,
                    0 if self._safe_int(row.get("api_team_id")) == api_team_id and api_team_id > 0 else 1,
                    0 if str(row.get("logo_url") or "").strip() else 1,
                    0 if str(row.get("coach_name") or "").strip() else 1,
                    str(row.get("created_at") or ""),
                    str(row.get("id") or ""),
                )
            )
            resolved = str(exact_candidates[0].get("id") or "").strip()
            if resolved:
                return resolved

        return stable_uuid("api-football-team", api_team_id)

    def _quota_available(self) -> bool:
        if self.requests_remaining is not None and self.requests_remaining < 10:
            logger.warning("Kalan API istegi az (%s), yeni istek atilmadi.", self.requests_remaining)
            return False
        return True

    def _update_rate_limit_state(self, headers: httpx.Headers) -> None:
        remaining_raw = headers.get("x-ratelimit-requests-remaining")
        limit_raw = headers.get("x-ratelimit-requests-limit")
        if remaining_raw is not None:
            self.requests_remaining = self._safe_int(remaining_raw, fallback=self.requests_remaining or 0)
        if limit_raw is not None:
            self.requests_limit = self._safe_int(limit_raw, fallback=self.requests_limit or 0)
        if self.requests_remaining is not None:
            logger.info("API-Football kalan istek: %s", self.requests_remaining)

    @staticmethod
    def _payload_has_errors(payload: Dict[str, Any]) -> bool:
        errors = payload.get("errors", [])
        if isinstance(errors, list):
            return len(errors) > 0
        if isinstance(errors, dict):
            return any(value not in (None, "", [], {}) for value in errors.values())
        return bool(errors)

    def _get_cached_payload(self, cache_key: str) -> Optional[Dict[str, Any]]:
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
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _set_cached_payload(self, cache_key: str, payload: Dict[str, Any], ttl_seconds: int) -> None:
        if self.supabase is None:
            return
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            cache_row = {
                "cache_key": cache_key,
                "payload": payload,
                "expires_at": expires_at.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.supabase.table("api_cache").upsert(cache_row, on_conflict="cache_key").execute()
        except Exception:
            return

    async def _request(self, endpoint: str, params: Dict[str, Any], ttl_seconds: int = 1200) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("API_FOOTBALL_KEY tanimli degil.")
            return None
        if not self._quota_available():
            return None

        cache_key = f"api_football:{endpoint}:{sorted(params.items())}"
        cached_payload = self._get_cached_payload(cache_key)
        if cached_payload is not None:
            return cached_payload

        url = f"{API_FOOTBALL_BASE_URL}{endpoint}"
        headers = {"x-apisports-key": os.getenv("API_FOOTBALL_KEY")}
        try:
            response = await self.http_client.get(url, headers=headers, params=params, timeout=10.0)
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

        self._update_rate_limit_state(response.headers)
        await asyncio.sleep(1)

        try:
            payload = response.json()
        except ValueError:
            logger.error("Gecersiz JSON: %s", url)
            return None

        if not isinstance(payload, dict):
            return None
        if self._payload_has_errors(payload):
            logger.error("API-Football errors: %s", payload.get("errors"))
            return None

        self._set_cached_payload(cache_key, payload, ttl_seconds)
        return payload

    def _ensure_team(self, team_payload: Dict[str, Any], league_name: str, country_name: str) -> Optional[str]:
        if self.supabase is None:
            return None
        api_team_id = self._safe_int(team_payload.get("id"))
        if api_team_id <= 0:
            return None

        team_name = str(team_payload.get("name") or f"Team {api_team_id}").strip()
        resolved_league_name = _canonical_league_name(league_name)
        resolved_country_name = _canonical_country_name(country_name)
        team_uuid = self._resolve_canonical_team_id(
            team_name=team_name,
            league_name=resolved_league_name,
            country_name=resolved_country_name,
            api_team_id=api_team_id,
        )
        record = {
            "id": team_uuid,
            "api_team_id": api_team_id,
            "name": team_name,
            "league": resolved_league_name,
            "country": resolved_country_name,
            "market_value": 0,
        }
        try:
            self.supabase.table("teams").upsert(record, on_conflict="id").execute()
            return team_uuid
        except Exception:
            try:
                self.supabase.table("teams").upsert(record, on_conflict="id").execute()
                return team_uuid
            except Exception:
                logger.exception("Team upsert failed. api_team_id=%s", api_team_id)
                return None

    def _match_lookup_by_api_id(self, api_match_id: int) -> Optional[Dict[str, Any]]:
        if self.supabase is None:
            return None
        try:
            result = (
                self.supabase.table("matches")
                .select("id,status")
                .eq("api_match_id", api_match_id)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    def _build_match_record(self, fixture_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        fixture = fixture_item.get("fixture", {})
        teams = fixture_item.get("teams", {})
        league = fixture_item.get("league", {})

        api_match_id = self._safe_int(fixture.get("id"))
        if api_match_id <= 0:
            return None

        home_team_id = self._ensure_team(
            teams.get("home", {}) if isinstance(teams.get("home"), dict) else {},
            league.get("name", "Unknown League"),
            league.get("country", "Unknown"),
        )
        away_team_id = self._ensure_team(
            teams.get("away", {}) if isinstance(teams.get("away"), dict) else {},
            league.get("name", "Unknown League"),
            league.get("country", "Unknown"),
        )
        if not home_team_id or not away_team_id:
            return None

        score = fixture_item.get("score", {})
        halftime = score.get("halftime", {}) if isinstance(score.get("halftime"), dict) else {}
        fulltime = score.get("fulltime", {}) if isinstance(score.get("fulltime"), dict) else {}

        return {
            "id": stable_uuid("api-football-match", api_match_id),
            "api_match_id": api_match_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "league": league.get("name", f"League {league.get('id', '')}"),
            "match_date": fixture.get("date"),
            "status": map_fixture_status(fixture.get("status", {}).get("short", "")),
            "season": str(
                league.get(
                    "season",
                    resolve_season_for_date(
                        str(fixture.get("date") or ""),
                        self._safe_int(league.get("id"), 0),
                        default=DEFAULT_SEASON,
                    ),
                )
            ),
            "ht_home": self._safe_int(halftime.get("home")),
            "ht_away": self._safe_int(halftime.get("away")),
            "ft_home": self._safe_int(fulltime.get("home")),
            "ft_away": self._safe_int(fulltime.get("away")),
        }

    async def get_fixtures_by_date(self, date: str) -> List[Dict[str, Any]]:
        if self.supabase is None:
            return []

        processed: List[Dict[str, Any]] = []
        inserted_count = 0
        updated_count = 0

        for league_id in TRACKED_LEAGUE_IDS:
            season = resolve_season_for_date(date, league_id, default=DEFAULT_SEASON)
            payload = await self._request(
                "/fixtures",
                {"date": date, "league": league_id, "season": season},
                ttl_seconds=1800,
            )
            if payload is None:
                continue

            for fixture_item in payload.get("response", []):
                record = self._build_match_record(fixture_item)
                if not record:
                    continue

                existing = self._match_lookup_by_api_id(self._safe_int(record["api_match_id"]))
                try:
                    if existing:
                        self.supabase.table("matches").update(record).eq("id", existing["id"]).execute()
                        updated_count += 1
                    else:
                        self.supabase.table("matches").insert(record).execute()
                        inserted_count += 1
                    processed.append(record)
                except Exception:
                    logger.exception("Match save failed. api_match_id=%s", record.get("api_match_id"))

        logger.info(
            "%s mac cekildi, inserted=%s updated=%s, tarih=%s kalan istek: %s",
            len(processed),
            inserted_count,
            updated_count,
            date,
            self.requests_remaining,
        )
        return processed

    def _latest_match_id_for_team(self, team_uuid: str) -> Optional[str]:
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

    async def get_team_statistics(self, team_id: int, league_id: int, season: int) -> Optional[Dict[str, Any]]:
        payload = await self._request(
            "/teams/statistics",
            {"league": league_id, "season": season, "team": team_id},
            ttl_seconds=21600,
        )
        if payload is None:
            return None

        response = payload.get("response", {})
        if not isinstance(response, dict):
            return None

        team_payload = response.get("team", {}) if isinstance(response.get("team"), dict) else {"id": team_id}
        team_uuid = self._ensure_team(team_payload, TRACKED_LEAGUES.get(league_id, str(league_id)), "")
        if not team_uuid or self.supabase is None:
            return response

        match_id = self._latest_match_id_for_team(team_uuid)
        if not match_id:
            return response

        fixtures_played = max(1, self._safe_int(response.get("fixtures", {}).get("played", {}).get("total"), 1))
        goals_for = self._safe_float(response.get("goals", {}).get("for", {}).get("total", {}).get("total"), 0.0)
        goals_against = self._safe_float(response.get("goals", {}).get("against", {}).get("total", {}).get("total"), 0.0)
        shots = self._safe_float(response.get("shots", {}).get("total"), 0.0)
        shots_on = self._safe_float(response.get("shots", {}).get("on"), 0.0)
        form = str(response.get("form", ""))[-6:]
        form_points = sum(3 if item == "W" else 1 if item == "D" else 0 for item in form)

        stats_record = {
            "team_id": team_uuid,
            "match_id": match_id,
            "goals_scored": int(round(goals_for / fixtures_played)),
            "goals_conceded": int(round(goals_against / fixtures_played)),
            "xg_for": round(goals_for / fixtures_played, 3),
            "xg_against": round(goals_against / fixtures_played, 3),
            "shots": int(round(shots / fixtures_played)),
            "shots_on_target": int(round(shots_on / fixtures_played)),
            "possession": 50.0,
            "form_last6": round(form_points / 18.0, 3),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.supabase.table("team_stats").upsert(stats_record, on_conflict="team_id,match_id").execute()
        except Exception:
            logger.exception("team_stats update failed. team_id=%s league_id=%s", team_id, league_id)
        return response

    async def get_head_to_head(self, team1_id: int, team2_id: int) -> Optional[List[Dict[str, Any]]]:
        payload = await self._request(
            "/fixtures/headtohead",
            {"h2h": f"{team1_id}-{team2_id}", "last": 10},
            ttl_seconds=21600,
        )
        if payload is None:
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(days=730)
        rows: List[Dict[str, Any]] = []
        for match in payload.get("response", []):
            fixture = match.get("fixture", {}) if isinstance(match.get("fixture"), dict) else {}
            league = match.get("league", {}) if isinstance(match.get("league"), dict) else {}
            date_raw = fixture.get("date")
            if not date_raw:
                continue
            try:
                parsed = datetime.fromisoformat(str(date_raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed < cutoff:
                continue
            league_type = str(league.get("type", "League")).lower()
            league_name = str(league.get("name", "")).lower()
            is_cup = league_type != "league" or any(keyword in league_name for keyword in ["cup", "uefa", "world", "euro"])
            rows.append({**match, "is_cup": is_cup})
        return rows

    async def get_injuries(self, fixture_id: int) -> Optional[List[Dict[str, Any]]]:
        payload = await self._request("/injuries", {"fixture": fixture_id}, ttl_seconds=3600)
        if payload is None:
            return None

        injuries: List[Dict[str, Any]] = []
        for row in payload.get("response", []):
            player = row.get("player", {}) if isinstance(row.get("player"), dict) else {}
            team = row.get("team", {}) if isinstance(row.get("team"), dict) else {}
            injury = row.get("player", {}).get("injury", {}) if isinstance(row.get("player"), dict) else {}
            injuries.append(
                {
                    "fixture_id": fixture_id,
                    "team_id": self._safe_int(team.get("id")),
                    "team_name": team.get("name"),
                    "player": player.get("name"),
                    "reason": injury.get("reason"),
                    "type": injury.get("type"),
                }
            )
        return injuries

    def _resolve_match(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        if self.supabase is None:
            return None
        try:
            result = (
                self.supabase.table("matches")
                .select("id,status")
                .eq("api_match_id", fixture_id)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception:
            return None

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

    async def get_odds(self, fixture_id: int) -> Optional[List[Dict[str, Any]]]:
        payload = await self._request("/fixtures/odds", {"fixture": fixture_id}, ttl_seconds=1200)
        if payload is None:
            return None
        match_info = self._resolve_match(fixture_id)
        if not match_info or self.supabase is None:
            return None

        match_id = str(match_info["id"])
        is_finished = str(match_info.get("status", "")).lower() == "finished"
        changes: List[Dict[str, Any]] = []

        for event in payload.get("response", []):
            for bookmaker in event.get("bookmakers", []) if isinstance(event.get("bookmakers"), list) else []:
                bookmaker_name = str(bookmaker.get("name", "Unknown"))
                for bet in bookmaker.get("bets", []) if isinstance(bookmaker.get("bets"), list) else []:
                    bet_name = str(bet.get("name", "Unknown"))
                    for value in bet.get("values", []) if isinstance(bet.get("values"), list) else []:
                        odd_value = self._safe_float(value.get("odd"), fallback=-1.0)
                        if odd_value <= 0:
                            continue

                        market_type = f"{bet_name}:{value.get('value', 'Unknown')}"
                        existing_row = self._existing_odd_row(match_id, bookmaker_name, market_type)
                        recorded_at = datetime.now(timezone.utc).isoformat()
                        try:
                            if existing_row:
                                opening_odd = self._safe_float(
                                    existing_row.get("opening_odd") or existing_row.get("current_odd"),
                                    fallback=odd_value,
                                )
                                update_payload = {
                                    "opening_odd": opening_odd,
                                    "current_odd": odd_value,
                                    "recorded_at": recorded_at,
                                }
                                if is_finished:
                                    update_payload["closing_odd"] = odd_value
                                self.supabase.table("odds_history").update(update_payload).eq("id", existing_row["id"]).execute()
                                changes.append({"action": "updated", "market_type": market_type, "odd": odd_value})
                            else:
                                insert_payload = {
                                    "match_id": match_id,
                                    "market_type": market_type,
                                    "bookmaker": bookmaker_name,
                                    "opening_odd": odd_value,
                                    "current_odd": odd_value,
                                    "closing_odd": odd_value if is_finished else None,
                                    "recorded_at": recorded_at,
                                }
                                self.supabase.table("odds_history").insert(insert_payload).execute()
                                changes.append({"action": "inserted", "market_type": market_type, "odd": odd_value})
                        except Exception:
                            logger.exception("odds_history save failed. fixture_id=%s", fixture_id)

        return changes

    async def get_standings(self, league_id: int, season: int) -> Optional[List[Dict[str, Any]]]:
        payload = await self._request("/standings", {"league": league_id, "season": season}, ttl_seconds=21600)
        if payload is None:
            return None

        rows: List[Dict[str, Any]] = []
        for league_row in payload.get("response", []):
            league = league_row.get("league", {}) if isinstance(league_row.get("league"), dict) else {}
            for group in league.get("standings", []) if isinstance(league.get("standings"), list) else []:
                for standing in group:
                    rows.append(standing)
                    team_payload = standing.get("team", {}) if isinstance(standing.get("team"), dict) else {}
                    self._ensure_team(team_payload, league.get("name", "Unknown"), league.get("country", "Unknown"))
        return rows

    async def get_predictions(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        payload = await self._request("/predictions", {"fixture": fixture_id}, ttl_seconds=3600)
        if payload is None:
            return None
        if self.supabase is None:
            return payload

        response_rows = payload.get("response", [])
        if not response_rows:
            return payload

        first = response_rows[0] if isinstance(response_rows[0], dict) else {}
        match = self._resolve_match(fixture_id)
        if not match:
            return first

        predictions = first.get("predictions", {}) if isinstance(first.get("predictions"), dict) else {}
        teams = first.get("teams", {}) if isinstance(first.get("teams"), dict) else {}
        winner = predictions.get("winner", {}) if isinstance(predictions.get("winner"), dict) else {}
        winner_name = str(winner.get("name", "")).lower()
        home_name = str(teams.get("home", {}).get("name", "")).lower() if isinstance(teams.get("home"), dict) else ""
        away_name = str(teams.get("away", {}).get("name", "")).lower() if isinstance(teams.get("away"), dict) else ""

        if home_name and winner_name == home_name:
            predicted_outcome = "MS1"
        elif away_name and winner_name == away_name:
            predicted_outcome = "MS2"
        elif not winner_name:
            predicted_outcome = "MSX"
        else:
            predicted_outcome = "MSX"

        perc = predictions.get("percent", {}) if isinstance(predictions.get("percent"), dict) else {}
        confidence = max(
            _parse_percent(perc.get("home")),
            _parse_percent(perc.get("draw")),
            _parse_percent(perc.get("away")),
        )
        prediction_payload = {
            "match_id": match["id"],
            "market_type": "API_REFERENCE",
            "predicted_outcome": predicted_outcome,
            "confidence_score": confidence if confidence > 0 else 50.0,
            "ev_percentage": 0.0,
            "recommended": confidence >= 60.0,
        }
        try:
            existing = (
                self.supabase.table("predictions")
                .select("id")
                .eq("match_id", match["id"])
                .eq("market_type", "API_REFERENCE")
                .limit(1)
                .execute()
            )
            if existing.data:
                self.supabase.table("predictions").update(prediction_payload).eq("id", existing.data[0]["id"]).execute()
            else:
                self.supabase.table("predictions").insert(prediction_payload).execute()
        except Exception:
            logger.exception("API reference prediction save failed. fixture_id=%s", fixture_id)
        return first

    async def close(self) -> None:
        try:
            await self.http_client.aclose()
        except Exception:
            logger.exception("ApiFootballService HTTP client close failed.")


_default_service = ApiFootballService()


def get_service() -> ApiFootballService:
    return _default_service


async def get_fixtures_by_date(date: str) -> Optional[List[Dict[str, Any]]]:
    return await _default_service.get_fixtures_by_date(date)


async def get_team_statistics(team_id: int, league_id: int, season: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_team_statistics(team_id, league_id, season)


async def get_head_to_head(team1_id: int, team2_id: int) -> Optional[List[Dict[str, Any]]]:
    return await _default_service.get_head_to_head(team1_id, team2_id)


async def get_injuries(fixture_id: int) -> Optional[List[Dict[str, Any]]]:
    return await _default_service.get_injuries(fixture_id)


async def get_odds(fixture_id: int) -> Optional[List[Dict[str, Any]]]:
    return await _default_service.get_odds(fixture_id)


async def get_standings(league_id: int, season: int) -> Optional[List[Dict[str, Any]]]:
    return await _default_service.get_standings(league_id, season)


async def get_predictions(fixture_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_predictions(fixture_id)
