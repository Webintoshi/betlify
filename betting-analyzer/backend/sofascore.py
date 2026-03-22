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

from config import SOFASCORE_TOURNAMENT_ID_SET, SOFASCORE_TOURNAMENT_IDS, TRACKED_LEAGUES
from proxy_pool import ProxyPool, mask_proxy

logger = logging.getLogger("sofascore")

BASE_URL = "https://www.sofascore.com/api/v1"
SOFASCORE_TEAM_LOGO_URL = "https://api.sofascore.app/api/v1/team/{team_id}/image"
SOFASCORE_PROFILE_STALE_DAYS = 7

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


def _normalize_competition_name(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").replace("_", " ").split())


def _is_stale_timestamp(raw_value: Any, *, days: int = SOFASCORE_PROFILE_STALE_DAYS) -> bool:
    text = str(raw_value or "").strip()
    if not text:
        return True
    try:
        last_updated = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - last_updated) > timedelta(days=max(1, int(days)))


_TRACKED_COMPETITION_HINTS = {
    *[_normalize_competition_name(name) for name in TRACKED_LEAGUES.values()],
    *[_normalize_competition_name(name) for name in SOFASCORE_TOURNAMENT_IDS.values()],
    "uefa champions league",
    "uefa europa league",
    "uefa conference league",
    "uefa nations league",
    "uefa euro",
    "fifa world cup",
    "turkey super league",
    "turkey 1 lig",
    "premier league",
    "championship",
    "la liga",
    "la liga 2",
    "serie a",
    "serie b",
    "bundesliga",
    "2 bundesliga",
    "ligue 1",
    "ligue 2",
    "eredivisie",
    "primeira liga",
    "jupiler pro league",
    "scottish premiership",
    "ekstraklasa",
    "austrian bundesliga",
}


def _is_tracked_tournament(tournament_id: int, tournament_name: str) -> bool:
    if tournament_id in SOFASCORE_TOURNAMENT_ID_SET:
        return True
    normalized = _normalize_competition_name(tournament_name)
    if not normalized:
        return False
    for hint in _TRACKED_COMPETITION_HINTS:
        if not hint:
            continue
        if normalized == hint or normalized in hint or hint in normalized:
            return True
    return False


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
        max_attempts = 1 if not self.proxy_pool.enabled else min(3, self.proxy_pool.size)

        for attempt in range(1, max_attempts + 1):
            proxy = self.proxy_pool.next()
            proxy_masked = mask_proxy(proxy)
            try:
                async with AsyncSession(impersonate="chrome120") as session:
                    response = await session.get(
                        url,
                        params=params,
                        headers=HEADERS,
                        timeout=15,
                        proxy=proxy,
                    )
            except Exception as exc:
                logger.error(
                    "Sofascore request failed (attempt=%s proxy=%s): %s",
                    attempt,
                    proxy_masked,
                    exc,
                )
                continue

            if response.status_code == 429:
                logger.warning("Sofascore 429 - 60s bekleniyor (proxy=%s)", proxy_masked)
                await asyncio.sleep(60)
                continue

            if response.status_code == 403:
                logger.error("Sofascore 403: %s (proxy=%s)", url, proxy_masked)
                continue

            if response.status_code >= 400:
                logger.error("HTTP %s: %s (proxy=%s)", response.status_code, url, proxy_masked)
                continue

            try:
                return response.json()
            except Exception:
                logger.error("Sofascore JSON parse hatasi: %s (proxy=%s)", url, proxy_masked)
                return None

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
        if self._has_column("teams", "logo_url"):
            select_columns += ",logo_url"
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
    def _team_logo_url(team_sofascore_id: int) -> str:
        if team_sofascore_id <= 0:
            return ""
        return SOFASCORE_TEAM_LOGO_URL.format(team_id=team_sofascore_id)

    @staticmethod
    def _team_profile_url(team_sofascore_id: int, slug: str = "") -> str:
        if team_sofascore_id <= 0:
            return ""
        normalized_slug = str(slug or "").strip().strip("/")
        if normalized_slug:
            return f"https://www.sofascore.com/tr/football/team/{normalized_slug}/{team_sofascore_id}"
        return f"https://www.sofascore.com/tr/team/{team_sofascore_id}"

    def _resolve_team_uuid_by_sofascore_id(self, sofascore_team_id: int) -> Optional[str]:
        if self.supabase is None or sofascore_team_id <= 0:
            return None
        if not self._has_column("teams", "sofascore_id"):
            return None
        try:
            result = (
                self.supabase.table("teams")
                .select("id")
                .eq("sofascore_id", sofascore_team_id)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if not rows:
                return None
            return str(rows[0].get("id") or "") or None
        except Exception:
            return None

    def _get_cached_team_profile_row(
        self,
        *,
        team_id: str = "",
        sofascore_team_id: int = 0,
    ) -> Optional[Dict[str, Any]]:
        if self.supabase is None or not self._has_column("team_profile_cache", "team_id"):
            return None
        try:
            query = self.supabase.table("team_profile_cache").select(
                "team_id,team_sofascore_id,team_name,country,logo_url,coach_name,coach_sofascore_id,sofascore_url,payload,updated_at"
            ).limit(1)
            if team_id:
                result = query.eq("team_id", team_id).execute()
            elif sofascore_team_id > 0:
                result = query.eq("team_sofascore_id", sofascore_team_id).execute()
            else:
                return None
            rows = result.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    def _upsert_team_profile_cache(self, *, team_id: str, payload: Dict[str, Any]) -> bool:
        if self.supabase is None or not team_id or not self._has_column("team_profile_cache", "team_id"):
            return False
        team_sofascore_id = _safe_int(payload.get("team_sofascore_id"))
        if team_sofascore_id <= 0:
            return False
        row = {
            "team_id": team_id,
            "team_sofascore_id": team_sofascore_id,
            "team_name": str(payload.get("team_name") or ""),
            "country": payload.get("country") or None,
            "logo_url": payload.get("logo_url") or None,
            "coach_name": payload.get("coach_name") or None,
            "coach_sofascore_id": _safe_int(payload.get("coach_sofascore_id")) or None,
            "sofascore_url": payload.get("sofascore_url") or None,
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.supabase.table("team_profile_cache").upsert(
                row,
                on_conflict="team_sofascore_id",
            ).execute()
            return True
        except Exception:
            logger.exception("team_profile_cache upsert failed. team_id=%s", team_id)
            return False

    def _sync_team_profile_to_teams_table(self, *, team_id: str, payload: Dict[str, Any]) -> bool:
        if self.supabase is None or not team_id:
            return False
        update_payload: Dict[str, Any] = {}
        team_name = str(payload.get("team_name") or "").strip()
        if team_name:
            update_payload["name"] = team_name
        country = str(payload.get("country") or "").strip()
        if country:
            update_payload["country"] = country
        league_name = str(payload.get("league") or "").strip()
        if league_name:
            update_payload["league"] = league_name
        if self._has_column("teams", "slug"):
            update_payload["slug"] = str(payload.get("slug") or "").strip() or None
        if self._has_column("teams", "sofascore_team_url"):
            update_payload["sofascore_team_url"] = str(payload.get("sofascore_url") or "").strip() or None
        if self._has_column("teams", "coach_name"):
            update_payload["coach_name"] = str(payload.get("coach_name") or "").strip() or None
        if self._has_column("teams", "coach_sofascore_id"):
            update_payload["coach_sofascore_id"] = _safe_int(payload.get("coach_sofascore_id")) or None
        if self._has_column("teams", "team_status"):
            update_payload["team_status"] = str(payload.get("team_status") or "active").strip() or "active"
        if self._has_column("teams", "profile_last_fetched_at"):
            update_payload["profile_last_fetched_at"] = datetime.now(timezone.utc).isoformat()
        if self._has_column("teams", "profile_source"):
            update_payload["profile_source"] = "sofascore"
        if self._has_column("teams", "profile_sync_status"):
            update_payload["profile_sync_status"] = "ready"
        if self._has_column("teams", "logo_url"):
            update_payload["logo_url"] = str(payload.get("logo_url") or "").strip() or None
        if self._has_column("teams", "logo_source"):
            update_payload["logo_source"] = "sofascore"
        if self._has_column("teams", "logo_status"):
            update_payload["logo_status"] = "ready" if payload.get("logo_url") else "pending"
        if self._has_column("teams", "logo_last_fetched_at") and payload.get("logo_url"):
            update_payload["logo_last_fetched_at"] = datetime.now(timezone.utc).isoformat()
        if self._has_column("teams", "logo_etag") and payload.get("logo_url"):
            update_payload["logo_etag"] = f"sofascore-team-{_safe_int(payload.get('team_sofascore_id'))}"
        if self._has_column("teams", "sofascore_last_synced_at"):
            update_payload["sofascore_last_synced_at"] = datetime.now(timezone.utc).isoformat()
        if self._has_column("teams", "sofascore_id"):
            update_payload["sofascore_id"] = _safe_int(payload.get("team_sofascore_id")) or None

        if not update_payload:
            return False
        try:
            self.supabase.table("teams").update(update_payload).eq("id", team_id).execute()
            return True
        except Exception:
            logger.exception("teams profile sync failed. team_id=%s", team_id)
            return False

    def _parse_team_profile_payload(self, payload: Dict[str, Any], team_id: int) -> Optional[Dict[str, Any]]:
        team = payload.get("team", {}) if isinstance(payload.get("team"), dict) else {}
        if not team:
            return None
        manager = team.get("manager", {}) if isinstance(team.get("manager"), dict) else {}
        primary_tournament = team.get("primaryUniqueTournament", {}) if isinstance(team.get("primaryUniqueTournament"), dict) else {}
        tournament = team.get("tournament", {}) if isinstance(team.get("tournament"), dict) else {}
        unique_tournament = tournament.get("uniqueTournament", {}) if isinstance(tournament.get("uniqueTournament"), dict) else {}
        country_node = team.get("country", {}) if isinstance(team.get("country"), dict) else {}
        venue = team.get("venue", {}) if isinstance(team.get("venue"), dict) else {}
        venue_country = venue.get("country", {}) if isinstance(venue.get("country"), dict) else {}
        category = team.get("category", {}) if isinstance(team.get("category"), dict) else {}

        slug = str(team.get("slug") or "").strip()
        country = (
            str(country_node.get("name") or "").strip()
            or str(venue_country.get("name") or "").strip()
            or str(category.get("name") or "").strip()
        )
        league_name = (
            str(primary_tournament.get("name") or "").strip()
            or str(unique_tournament.get("name") or "").strip()
            or str(tournament.get("name") or "").strip()
        )
        coach_name = str(manager.get("name") or "").strip() or None
        return {
            "team_sofascore_id": int(team_id),
            "team_name": str(team.get("name") or f"Team {team_id}").strip(),
            "country": country or None,
            "logo_url": self._team_logo_url(team_id),
            "coach_name": coach_name,
            "coach_sofascore_id": _safe_int(manager.get("id")) or None,
            "slug": slug or None,
            "sofascore_url": self._team_profile_url(team_id, slug=slug),
            "league": league_name or None,
            "team_status": "inactive" if bool(team.get("disabled")) else "active",
            "payload": payload,
        }

    def sync_team_logo(
        self,
        *,
        team_id: Optional[str],
        sofascore_team_id: int,
        force: bool = False,
    ) -> Dict[str, Any]:
        if self.supabase is None:
            return {"updated": False, "reason": "supabase_unavailable"}
        if sofascore_team_id <= 0:
            return {"updated": False, "reason": "invalid_sofascore_team_id"}

        resolved_team_id = str(team_id or "").strip() or self._resolve_team_uuid_by_sofascore_id(sofascore_team_id) or ""
        if not resolved_team_id:
            return {"updated": False, "reason": "team_not_found"}

        now = datetime.now(timezone.utc)
        logo_url = self._team_logo_url(sofascore_team_id)
        if not logo_url:
            return {"updated": False, "reason": "logo_url_missing"}

        stale = True
        if not force and self._has_column("teams", "logo_last_fetched_at"):
            try:
                existing = (
                    self.supabase.table("teams")
                    .select("logo_url,logo_last_fetched_at")
                    .eq("id", resolved_team_id)
                    .limit(1)
                    .execute()
                )
                row = (existing.data or [None])[0]
                if isinstance(row, dict):
                    existing_logo = str(row.get("logo_url") or "")
                    last_fetched_raw = str(row.get("logo_last_fetched_at") or "")
                    if existing_logo and last_fetched_raw:
                        last_fetched = datetime.fromisoformat(last_fetched_raw.replace("Z", "+00:00"))
                        stale = (now - last_fetched) > timedelta(days=7)
            except Exception:
                stale = True

        if not force and not stale:
            return {"updated": False, "reason": "fresh_cache", "logo_url": logo_url}

        payload: Dict[str, Any] = {}
        if self._has_column("teams", "logo_url"):
            payload["logo_url"] = logo_url
        if self._has_column("teams", "logo_source"):
            payload["logo_source"] = "sofascore"
        if self._has_column("teams", "logo_status"):
            payload["logo_status"] = "ready"
        if self._has_column("teams", "logo_last_fetched_at"):
            payload["logo_last_fetched_at"] = now.isoformat()
        if self._has_column("teams", "logo_etag"):
            payload["logo_etag"] = f"sofascore-team-{sofascore_team_id}"
        if self._has_column("teams", "sofascore_last_synced_at"):
            payload["sofascore_last_synced_at"] = now.isoformat()
        if self._has_column("teams", "sofascore_id"):
            payload["sofascore_id"] = sofascore_team_id

        if not payload:
            return {"updated": False, "reason": "columns_missing"}

        try:
            self.supabase.table("teams").update(payload).eq("id", resolved_team_id).execute()
            return {"updated": True, "team_id": resolved_team_id, "logo_url": logo_url}
        except Exception:
            logger.exception("team logo sync failed. team_id=%s sofascore_team_id=%s", resolved_team_id, sofascore_team_id)
            return {"updated": False, "reason": "update_failed", "team_id": resolved_team_id}

    def _team_id_map_from_sofascore_ids(self, sofascore_team_ids: List[int]) -> Dict[int, str]:
        if self.supabase is None or not sofascore_team_ids:
            return {}
        if not self._has_column("teams", "sofascore_id"):
            return {}
        try:
            unique_ids = sorted({int(team_id) for team_id in sofascore_team_ids if int(team_id) > 0})
            if not unique_ids:
                return {}
            rows = (
                self.supabase.table("teams")
                .select("id,sofascore_id")
                .in_("sofascore_id", unique_ids)
                .execute()
                .data
                or []
            )
            return {
                _safe_int(row.get("sofascore_id")): str(row.get("id"))
                for row in rows
                if _safe_int(row.get("sofascore_id")) > 0 and str(row.get("id") or "")
            }
        except Exception:
            return {}

    def _upsert_team_season_stats_cache(self, *, team_id: str, payload: Dict[str, Any]) -> bool:
        if self.supabase is None or not team_id:
            return False
        if not self._has_column("team_season_stats_cache", "team_id"):
            return False
        row = {
            "team_id": team_id,
            "team_sofascore_id": _safe_int(payload.get("team_sofascore_id")),
            "tournament_id": _safe_int(payload.get("tournament_id")),
            "season_id": _safe_int(payload.get("season_id")),
            "position": _safe_int(payload.get("position")),
            "matches_played": _safe_int(payload.get("matches_played")),
            "goals_for": round(float(payload.get("goals_for", 0) or 0), 3),
            "goals_against": round(float(payload.get("goals_against", 0) or 0), 3),
            "goals_per_match": round(float(payload.get("goals_per_match", 0) or 0), 3),
            "goals_conceded_per_match": round(float(payload.get("goals_conceded_per_match", 0) or 0), 3),
            "clean_sheets": _safe_int(payload.get("clean_sheets")),
            "assists": _safe_int(payload.get("assists")),
            "expected_goals": round(float(payload.get("expected_goals", 0) or 0), 3),
            "shots_on_target": round(float(payload.get("shots_on_target", 0) or 0), 3),
            "big_chances": round(float(payload.get("big_chances", 0) or 0), 3),
            "possession": round(float(payload.get("possession", 0) or 0), 3),
            "avg_rating": round(float(payload.get("avg_rating", 0) or 0), 3),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if row["team_sofascore_id"] <= 0 or row["tournament_id"] <= 0 or row["season_id"] <= 0:
            return False
        try:
            self.supabase.table("team_season_stats_cache").upsert(
                row,
                on_conflict="team_id,tournament_id,season_id",
            ).execute()
            return True
        except Exception:
            logger.exception("team_season_stats_cache upsert failed. team_id=%s", team_id)
            return False

    def _replace_team_top_players_cache(
        self,
        *,
        team_id: str,
        team_sofascore_id: int,
        players: List[Dict[str, Any]],
        tournament_id: Optional[int],
        season_id: Optional[int],
    ) -> int:
        if self.supabase is None or not team_id:
            return 0
        if not self._has_column("team_top_players_cache", "team_id"):
            return 0

        t_id = int(tournament_id or 0)
        s_id = int(season_id or 0)
        try:
            cleanup = self.supabase.table("team_top_players_cache").delete().eq("team_id", team_id)
            cleanup = cleanup.eq("tournament_id", t_id) if t_id > 0 else cleanup.is_("tournament_id", "null")
            cleanup = cleanup.eq("season_id", s_id) if s_id > 0 else cleanup.is_("season_id", "null")
            cleanup.execute()
        except Exception:
            logger.exception("team_top_players_cache cleanup failed. team_id=%s", team_id)

        saved = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        for player in players:
            name = str(player.get("name") or "").strip()
            if not name:
                continue
            row = {
                "team_id": team_id,
                "team_sofascore_id": int(team_sofascore_id),
                "tournament_id": t_id if t_id > 0 else None,
                "season_id": s_id if s_id > 0 else None,
                "player_sofascore_id": _safe_int(player.get("player_id")) or None,
                "player_name": name,
                "position": str(player.get("position") or ""),
                "rating": round(float(player.get("rating", 0) or 0), 2),
                "minutes_played": _safe_int(player.get("minutes_played")),
                "updated_at": now_iso,
            }
            try:
                self.supabase.table("team_top_players_cache").upsert(
                    row,
                    on_conflict="team_id,tournament_id,season_id,player_name",
                ).execute()
                saved += 1
            except Exception:
                logger.exception("team_top_players_cache upsert failed. team_id=%s player=%s", team_id, name)
        return saved

    def _upsert_league_standings_cache(
        self,
        *,
        tournament_id: int,
        season_id: int,
        rows: List[Dict[str, Any]],
    ) -> int:
        if self.supabase is None:
            return 0
        if tournament_id <= 0 or season_id <= 0:
            return 0
        if not self._has_column("league_standings_cache", "tournament_id"):
            return 0

        by_sofascore = self._team_id_map_from_sofascore_ids(
            [_safe_int(row.get("team_sofascore_id")) for row in rows if isinstance(row, dict)]
        )
        saved = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        for row in rows:
            if not isinstance(row, dict):
                continue
            team_sofascore_id = _safe_int(row.get("team_sofascore_id"))
            if team_sofascore_id <= 0:
                continue
            payload = {
                "tournament_id": int(tournament_id),
                "season_id": int(season_id),
                "team_id": by_sofascore.get(team_sofascore_id),
                "team_sofascore_id": team_sofascore_id,
                "team_name": str(row.get("team_name") or ""),
                "position": _safe_int(row.get("position")),
                "played": _safe_int(row.get("played")),
                "wins": _safe_int(row.get("wins")),
                "draws": _safe_int(row.get("draws")),
                "losses": _safe_int(row.get("losses")),
                "points": _safe_int(row.get("points")),
                "goals_for": _safe_int(row.get("goals_for")),
                "goals_against": _safe_int(row.get("goals_against")),
                "goal_diff": _safe_int(row.get("goal_diff")),
                "form": str(row.get("form") or ""),
                "updated_at": now_iso,
            }
            try:
                self.supabase.table("league_standings_cache").upsert(
                    payload,
                    on_conflict="tournament_id,season_id,team_sofascore_id",
                ).execute()
                saved += 1
            except Exception:
                logger.exception(
                    "league_standings_cache upsert failed. tournament=%s season=%s team_sofascore_id=%s",
                    tournament_id,
                    season_id,
                    team_sofascore_id,
                )
        return saved

    async def sync_match_sofascore_bundle(self, match_id: str, force: bool = False) -> Dict[str, Any]:
        if self.supabase is None:
            return {"updated": False, "reason": "supabase_unavailable"}

        mapping = await self._resolve_sofascore_team_ids_for_match(match_id)
        if not isinstance(mapping, dict):
            return {"updated": False, "reason": "mapping_missing"}

        event_id = _safe_int(mapping.get("event_id"))
        home_sofa_id = _safe_int(mapping.get("home_sofascore_id"))
        away_sofa_id = _safe_int(mapping.get("away_sofascore_id"))
        match_row = self._resolve_match_by_id(match_id)
        if not match_row:
            return {"updated": False, "reason": "match_missing"}

        home_team_id = str(match_row.get("home_team_id") or "")
        away_team_id = str(match_row.get("away_team_id") or "")
        profile_updates = 0
        for team_id, sofa_id in [(home_team_id, home_sofa_id), (away_team_id, away_sofa_id)]:
            if sofa_id <= 0:
                continue
            profile_res = await self.sync_team_profile(team_id, sofa_id, force=force)
            if profile_res.get("updated"):
                profile_updates += 1

        tournament_id = 0
        season_id = 0
        if event_id > 0:
            event = await self.get_event_detail(event_id, ttl_seconds=120 if force else 900)
            if isinstance(event, dict):
                tournament = event.get("tournament", {}) if isinstance(event.get("tournament"), dict) else {}
                unique = tournament.get("uniqueTournament", {}) if isinstance(tournament.get("uniqueTournament"), dict) else {}
                season = event.get("season", {}) if isinstance(event.get("season"), dict) else {}
                tournament_id = _safe_int(unique.get("id") or tournament.get("id"))
                season_id = _safe_int(season.get("id") or season.get("year"))

        season_cache_updates = 0
        top_players_updates = 0
        standings_updates = 0
        if tournament_id > 0 and season_id > 0:
            standings = await self.get_tournament_standings(tournament_id, season_id)
            if isinstance(standings, list):
                standings_updates = self._upsert_league_standings_cache(
                    tournament_id=tournament_id,
                    season_id=season_id,
                    rows=standings,
                )

            for team_id, sofa_id in [(home_team_id, home_sofa_id), (away_team_id, away_sofa_id)]:
                if not team_id or sofa_id <= 0:
                    continue
                season_stats = await self.get_team_season_statistics(sofa_id, tournament_id, season_id)
                if isinstance(season_stats, dict) and season_stats:
                    if self._upsert_team_season_stats_cache(team_id=team_id, payload=season_stats):
                        season_cache_updates += 1
                top_players = await self.get_team_top_players(
                    sofa_id,
                    limit=8,
                    tournament_id=tournament_id,
                    season_id=season_id,
                )
                if isinstance(top_players, list) and top_players:
                    top_players_updates += self._replace_team_top_players_cache(
                        team_id=team_id,
                        team_sofascore_id=sofa_id,
                        players=top_players,
                        tournament_id=tournament_id,
                        season_id=season_id,
                    )

        now_iso = datetime.now(timezone.utc).isoformat()
        for team_id in [home_team_id, away_team_id]:
            if not team_id:
                continue
            if self._has_column("teams", "sofascore_last_synced_at"):
                try:
                    self.supabase.table("teams").update({"sofascore_last_synced_at": now_iso}).eq("id", team_id).execute()
                except Exception:
                    logger.exception("teams sofascore_last_synced_at update failed. team_id=%s", team_id)

        return {
            "updated": True,
            "match_id": match_id,
            "event_id": event_id,
            "tournament_id": tournament_id,
            "season_id": season_id,
            "logo_updates": profile_updates,
            "profile_updates": profile_updates,
            "season_cache_updates": season_cache_updates,
            "top_players_updates": top_players_updates,
            "standings_updates": standings_updates,
        }

    def refresh_team_logos(self, *, force: bool = False, limit: int = 0) -> Dict[str, Any]:
        if self.supabase is None:
            return {"processed": 0, "updated": 0, "reason": "supabase_unavailable"}
        if not self._has_column("teams", "sofascore_id"):
            return {"processed": 0, "updated": 0, "reason": "sofascore_id_missing"}

        try:
            try:
                result = (
                    self.supabase.table("teams")
                    .select("id,sofascore_id,logo_url,logo_last_fetched_at")
                    .not_.is_("sofascore_id", "null")
                    .order("name")
                    .execute()
                )
            except Exception:
                result = (
                    self.supabase.table("teams")
                    .select("id,sofascore_id")
                    .not_.is_("sofascore_id", "null")
                    .order("name")
                    .execute()
                )
            rows = result.data or []
        except Exception:
            logger.exception("team logo refresh list failed.")
            return {"processed": 0, "updated": 0, "reason": "query_failed"}

        processed = 0
        updated = 0
        for row in rows:
            team_id = str(row.get("id") or "")
            sofascore_team_id = _safe_int(row.get("sofascore_id"))
            if not team_id or sofascore_team_id <= 0:
                continue
            processed += 1
            response = self.sync_team_logo(
                team_id=team_id,
                sofascore_team_id=sofascore_team_id,
                force=force,
            )
            if response.get("updated"):
                updated += 1
            if limit > 0 and processed >= int(limit):
                break

        logger.info("Team logo refresh tamamlandi. processed=%s updated=%s force=%s", processed, updated, force)
        return {"processed": processed, "updated": updated, "force": bool(force)}

    async def get_latest_tournament_season_id(self, tournament_id: int) -> Optional[int]:
        if tournament_id <= 0:
            return None
        payload = await self._request(f"/unique-tournament/{tournament_id}/seasons", ttl_seconds=21600)
        if payload is None:
            return None
        seasons = payload.get("seasons", []) if isinstance(payload, dict) else []
        if not isinstance(seasons, list) or not seasons:
            return None
        first = seasons[0] if isinstance(seasons[0], dict) else {}
        season_id = _safe_int(first.get("id"))
        return season_id if season_id > 0 else None

    async def get_team_profile(self, team_id: int) -> Optional[Dict[str, Any]]:
        if team_id <= 0:
            return None
        payload = await self._request(f"/team/{team_id}", ttl_seconds=21600)
        if payload is None:
            return None
        normalized = self._parse_team_profile_payload(payload if isinstance(payload, dict) else {}, team_id)
        return normalized or {}

    async def sync_team_profile(
        self,
        team_id: str,
        sofascore_team_id: int,
        force: bool = False,
    ) -> Dict[str, Any]:
        if self.supabase is None:
            return {"updated": False, "reason": "supabase_unavailable"}
        if sofascore_team_id <= 0:
            return {"updated": False, "reason": "invalid_sofascore_team_id"}

        resolved_team_id = str(team_id or "").strip() or self._resolve_team_uuid_by_sofascore_id(sofascore_team_id) or ""
        if not resolved_team_id:
            return {"updated": False, "reason": "team_not_found"}

        cached = self._get_cached_team_profile_row(team_id=resolved_team_id, sofascore_team_id=sofascore_team_id)
        if cached and not force and not _is_stale_timestamp(cached.get("updated_at")):
            normalized_cached = {
                "team_sofascore_id": _safe_int(cached.get("team_sofascore_id")),
                "team_name": str(cached.get("team_name") or "").strip(),
                "country": cached.get("country"),
                "logo_url": cached.get("logo_url"),
                "coach_name": cached.get("coach_name"),
                "coach_sofascore_id": _safe_int(cached.get("coach_sofascore_id")) or None,
                "slug": None,
                "sofascore_url": cached.get("sofascore_url"),
                "league": None,
                "team_status": "active",
                "payload": cached.get("payload") if isinstance(cached.get("payload"), dict) else {},
            }
            self._sync_team_profile_to_teams_table(team_id=resolved_team_id, payload=normalized_cached)
            return {
                "updated": False,
                "reason": "fresh_cache",
                "team_id": resolved_team_id,
                "team_sofascore_id": sofascore_team_id,
                "team_name": normalized_cached["team_name"],
                "coach_name": normalized_cached["coach_name"],
                "logo_url": normalized_cached["logo_url"],
            }

        profile = await self.get_team_profile(sofascore_team_id)
        if not isinstance(profile, dict) or not profile:
            stale_payload: Dict[str, Any] = {}
            if self._has_column("teams", "profile_sync_status"):
                stale_payload["profile_sync_status"] = "stale"
            if stale_payload:
                try:
                    self.supabase.table("teams").update(stale_payload).eq("id", resolved_team_id).execute()
                except Exception:
                    logger.exception("team profile stale status update failed. team_id=%s", resolved_team_id)
            return {"updated": False, "reason": "profile_fetch_failed", "team_id": resolved_team_id}

        self._sync_team_profile_to_teams_table(team_id=resolved_team_id, payload=profile)
        self._upsert_team_profile_cache(team_id=resolved_team_id, payload=profile)
        return {
            "updated": True,
            "team_id": resolved_team_id,
            "team_sofascore_id": sofascore_team_id,
            "team_name": profile.get("team_name"),
            "coach_name": profile.get("coach_name"),
            "logo_url": profile.get("logo_url"),
        }

    async def discover_teams_from_scheduled_events(self, date: str) -> List[Dict[str, Any]]:
        events = await self.get_scheduled_events(date)
        if not isinstance(events, list):
            return []
        discovered: Dict[int, Dict[str, Any]] = {}
        for event in events:
            if not isinstance(event, dict):
                continue
            tournament = event.get("tournament", {}) if isinstance(event.get("tournament"), dict) else {}
            unique = tournament.get("uniqueTournament", {}) if isinstance(tournament.get("uniqueTournament"), dict) else {}
            league_name = str(unique.get("name") or tournament.get("name") or "Unknown")
            country_name = str(tournament.get("category", {}).get("name") or "Unknown") if isinstance(tournament.get("category"), dict) else "Unknown"
            for side in ("homeTeam", "awayTeam"):
                team_node = event.get(side, {}) if isinstance(event.get(side), dict) else {}
                team_sofascore_id = _safe_int(team_node.get("id"))
                if team_sofascore_id <= 0:
                    continue
                team_uuid = self._ensure_team(team_node, league_name, country_name)
                if not team_uuid:
                    continue
                discovered[team_sofascore_id] = {
                    "team_id": team_uuid,
                    "team_sofascore_id": team_sofascore_id,
                    "team_name": str(team_node.get("name") or "").strip(),
                    "league": league_name,
                    "country": country_name,
                }
        return list(discovered.values())

    async def discover_teams_from_standings(self, tournament_id: int, season_id: int) -> List[Dict[str, Any]]:
        if tournament_id <= 0:
            return []
        resolved_season_id = season_id if season_id > 0 else (await self.get_latest_tournament_season_id(tournament_id) or 0)
        if resolved_season_id <= 0:
            return []

        rows = await self.get_tournament_standings(tournament_id, resolved_season_id)
        if not isinstance(rows, list):
            return []

        league_name = SOFASCORE_TOURNAMENT_IDS.get(tournament_id, f"Tournament {tournament_id}")
        discovered: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            team_sofascore_id = _safe_int(row.get("team_sofascore_id"))
            if team_sofascore_id <= 0:
                continue
            team_payload = {
                "id": team_sofascore_id,
                "name": row.get("team_name") or f"Team {team_sofascore_id}",
            }
            team_uuid = self._ensure_team(team_payload, league_name, "Unknown")
            if not team_uuid:
                continue
            discovered.append(
                {
                    "team_id": team_uuid,
                    "team_sofascore_id": team_sofascore_id,
                    "team_name": str(row.get("team_name") or "").strip(),
                    "league": league_name,
                    "season_id": resolved_season_id,
                    "tournament_id": tournament_id,
                }
            )
        return discovered

    async def discover_all_tracked_teams(self) -> Dict[str, Any]:
        if self.supabase is None:
            return {"processed": 0, "discovered": 0, "source_breakdown": {}, "reason": "supabase_unavailable"}

        unique_rows: Dict[int, Dict[str, Any]] = {}
        source_breakdown: Dict[str, int] = {}

        today = datetime.now(timezone.utc).date()
        for date_str in [today.isoformat(), (today + timedelta(days=1)).isoformat()]:
            rows = await self.discover_teams_from_scheduled_events(date_str)
            source_breakdown[f"scheduled:{date_str}"] = len(rows)
            for row in rows:
                team_sofascore_id = _safe_int(row.get("team_sofascore_id"))
                if team_sofascore_id > 0:
                    unique_rows[team_sofascore_id] = row

        for tournament_id in sorted(SOFASCORE_TOURNAMENT_IDS.keys()):
            rows = await self.discover_teams_from_standings(tournament_id, 0)
            source_breakdown[f"standings:{tournament_id}"] = len(rows)
            for row in rows:
                team_sofascore_id = _safe_int(row.get("team_sofascore_id"))
                if team_sofascore_id > 0:
                    unique_rows[team_sofascore_id] = row

        return {
            "processed": len(unique_rows),
            "discovered": len(unique_rows),
            "source_breakdown": source_breakdown,
            "teams": list(unique_rows.values()),
        }

    async def refresh_team_profiles(self, *, force: bool = False, limit: int = 0) -> Dict[str, Any]:
        if self.supabase is None:
            return {"processed": 0, "updated": 0, "reason": "supabase_unavailable"}
        if not self._has_column("teams", "sofascore_id"):
            return {"processed": 0, "updated": 0, "reason": "sofascore_id_missing"}

        select_columns = "id,sofascore_id,name,logo_url,coach_name"
        if self._has_column("teams", "profile_last_fetched_at"):
            select_columns += ",profile_last_fetched_at"
        if self._has_column("teams", "profile_sync_status"):
            select_columns += ",profile_sync_status"

        try:
            rows = (
                self.supabase.table("teams")
                .select(select_columns)
                .not_.is_("sofascore_id", "null")
                .order("name")
                .limit(5000 if limit <= 0 else max(limit * 4, limit))
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("team profile refresh list failed.")
            return {"processed": 0, "updated": 0, "reason": "query_failed"}

        pending_rows: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = str(row.get("profile_sync_status") or "").strip().lower()
            stale = force or _is_stale_timestamp(row.get("profile_last_fetched_at"))
            missing_logo = not str(row.get("logo_url") or "").strip()
            missing_coach = row.get("coach_name") in (None, "")
            needs_sync = force or status in {"", "pending", "stale"} or stale or missing_logo or missing_coach
            if needs_sync:
                pending_rows.append(row)

        processed = 0
        updated = 0
        failed = 0
        for row in pending_rows:
            team_id = str(row.get("id") or "").strip()
            sofascore_team_id = _safe_int(row.get("sofascore_id"))
            if not team_id or sofascore_team_id <= 0:
                continue
            processed += 1
            result = await self.sync_team_profile(team_id, sofascore_team_id, force=force)
            if result.get("updated"):
                updated += 1
            elif result.get("reason") not in {"fresh_cache"}:
                failed += 1
            if limit > 0 and processed >= int(limit):
                break

        logger.info("Team profile refresh tamamlandi. processed=%s updated=%s failed=%s force=%s", processed, updated, failed, force)
        return {"processed": processed, "updated": updated, "failed": failed, "force": bool(force)}

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

    @staticmethod
    def _result_code(team_goals: int, opp_goals: int) -> str:
        if team_goals > opp_goals:
            return "W"
        if team_goals == opp_goals:
            return "D"
        return "L"

    @staticmethod
    def _estimate_xg(shots: float, shots_on_target: float, big_chances: float) -> float:
        # Fallback xG approximation when Sofascore does not expose explicit expected-goals.
        estimated = (shots * 0.08) + (shots_on_target * 0.22) + (big_chances * 0.35)
        return round(max(0.0, min(5.0, estimated)), 3)

    @staticmethod
    def _normalize_missing_status(*, status_raw: str, reason_raw: str) -> str:
        token = f"{status_raw} {reason_raw}".lower()
        if any(flag in token for flag in ["suspend", "ceza", "ban", "red", "kirmizi", "yellow"]):
            return "suspended"
        if any(flag in token for flag in ["doubt", "question", "uncertain", "minor knock"]):
            return "doubtful"
        return "injured"

    def _extract_missing_players(self, team_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        missing = team_payload.get("missingPlayers", []) if isinstance(team_payload.get("missingPlayers"), list) else []
        rows: List[Dict[str, Any]] = []
        for item in missing:
            if not isinstance(item, dict):
                continue
            player_node = item.get("player", {}) if isinstance(item.get("player"), dict) else {}
            player_name = str(player_node.get("name") or item.get("name") or item.get("playerName") or "").strip()
            if not player_name:
                continue
            position = str(player_node.get("position") or player_node.get("shortName") or item.get("position") or "").strip()
            reason = str(item.get("reason") or item.get("missingReason") or item.get("type") or "").strip()
            status_raw = str(item.get("status") or item.get("type") or "").strip()
            expected_return = str(
                item.get("expectedReturn")
                or item.get("expectedReturnDate")
                or item.get("returnDate")
                or ""
            ).strip()
            status = self._normalize_missing_status(status_raw=status_raw, reason_raw=reason)
            rows.append(
                {
                    "player_name": player_name,
                    "position": position,
                    "status": status,
                    "reason": reason,
                    "expected_return": expected_return,
                }
            )
        return rows

    def _save_match_injuries(
        self,
        *,
        match_id: str,
        team_id: str,
        entries: List[Dict[str, Any]],
    ) -> int:
        if self.supabase is None:
            return 0
        if not self._has_column("match_injuries", "match_id"):
            return 0
        saved = 0
        for entry in entries:
            player_name = str(entry.get("player_name") or "").strip()
            if not player_name:
                continue
            payload = {
                "match_id": match_id,
                "team_id": team_id,
                "player_name": player_name,
                "position": entry.get("position") or None,
                "status": entry.get("status") or "injured",
                "reason": entry.get("reason") or None,
                "expected_return": entry.get("expected_return") or None,
            }
            try:
                self.supabase.table("match_injuries").upsert(
                    payload,
                    on_conflict="match_id,team_id,player_name",
                ).execute()
                saved += 1
            except Exception:
                logger.exception("match_injuries upsert failed. match_id=%s player=%s", match_id, player_name)
        return saved

    def _save_h2h_rows(
        self,
        *,
        home_team_id: str,
        away_team_id: str,
        rows: List[Dict[str, Any]],
    ) -> int:
        if self.supabase is None:
            return 0
        if not self._has_column("h2h", "home_team_id"):
            return 0
        saved = 0
        for row in rows:
            sofascore_id = _safe_int(row.get("sofascore_id"))
            match_date = str(row.get("match_date") or "")
            if not match_date:
                continue
            payload = {
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "match_date": match_date,
                "home_goals": _safe_int(row.get("home_goals")),
                "away_goals": _safe_int(row.get("away_goals")),
                "league": row.get("league") or None,
                "sofascore_id": sofascore_id if sofascore_id > 0 else None,
                "is_cup": bool(row.get("is_cup", False)),
            }
            try:
                if sofascore_id > 0:
                    self.supabase.table("h2h").upsert(payload, on_conflict="sofascore_id").execute()
                else:
                    self.supabase.table("h2h").insert(payload).execute()
                saved += 1
            except Exception:
                logger.exception("h2h upsert failed. sofascore_id=%s", sofascore_id)
        return saved

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
        slug = str(team_payload.get("slug") or "").strip()
        record = {
            "id": team_uuid,
            "name": team_payload.get("name", f"Team {sofascore_team_id}"),
            "league": league_name or "Unknown",
            "country": country_name or "Unknown",
            "market_value": 0,
        }
        if has_sofascore_column:
            record["sofascore_id"] = sofascore_team_id
        if self._has_column("teams", "logo_url"):
            record["logo_url"] = self._team_logo_url(sofascore_team_id)
        if self._has_column("teams", "logo_source"):
            record["logo_source"] = "sofascore"
        if self._has_column("teams", "logo_status"):
            record["logo_status"] = "ready"
        if self._has_column("teams", "slug") and slug:
            record["slug"] = slug
        if self._has_column("teams", "sofascore_team_url") and slug:
            record["sofascore_team_url"] = self._team_profile_url(sofascore_team_id, slug=slug)
        if self._has_column("teams", "profile_source"):
            record["profile_source"] = "sofascore"
        if self._has_column("teams", "team_status"):
            record["team_status"] = "inactive" if bool(team_payload.get("disabled")) else "active"
        if self._has_column("teams", "logo_last_fetched_at"):
            record["logo_last_fetched_at"] = datetime.now(timezone.utc).isoformat()
        if self._has_column("teams", "logo_etag"):
            record["logo_etag"] = f"sofascore-team-{sofascore_team_id}"
        if self._has_column("teams", "sofascore_last_synced_at"):
            record["sofascore_last_synced_at"] = datetime.now(timezone.utc).isoformat()
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
            tournament_name = str(unique_tournament.get("name") or tournament.get("name") or "")
            if not _is_tracked_tournament(tournament_id, tournament_name):
                continue

            event_id = _safe_int(event.get("id"))
            if event_id <= 0:
                continue

            home_team = event.get("homeTeam", {}) if isinstance(event.get("homeTeam"), dict) else {}
            away_team = event.get("awayTeam", {}) if isinstance(event.get("awayTeam"), dict) else {}
            league_name = SOFASCORE_TOURNAMENT_IDS.get(tournament_id, tournament_name or "Unknown")
            country = str(tournament.get("category", {}).get("name", "Unknown")) if isinstance(tournament.get("category"), dict) else "Unknown"

            home_uuid = self._ensure_team(home_team, league_name, country)
            away_uuid = self._ensure_team(away_team, league_name, country)
            if not home_uuid or not away_uuid:
                continue
            self.sync_team_logo(team_id=home_uuid, sofascore_team_id=_safe_int(home_team.get("id")), force=False)
            self.sync_team_logo(team_id=away_uuid, sofascore_team_id=_safe_int(away_team.get("id")), force=False)

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

    async def get_event_detail(self, event_id: int, *, ttl_seconds: int = 180) -> Optional[Dict[str, Any]]:
        payload = await self._request(f"/event/{event_id}", ttl_seconds=max(30, int(ttl_seconds)))
        if payload is None:
            return None
        event = payload.get("event", {}) if isinstance(payload, dict) else {}
        if not isinstance(event, dict) or not event:
            return None
        return event

    async def get_event_result(self, event_id: int) -> Optional[Dict[str, Any]]:
        event = await self.get_event_detail(event_id, ttl_seconds=120)
        if not isinstance(event, dict):
            return None

        status_raw = str(event.get("status", {}).get("type", "")).strip().lower() if isinstance(event.get("status"), dict) else ""
        status = map_sofascore_status(status_raw)
        home_goals, away_goals = self._event_goals(event)
        home_period1 = _safe_int(event.get("homeScore", {}).get("period1") if isinstance(event.get("homeScore"), dict) else 0)
        away_period1 = _safe_int(event.get("awayScore", {}).get("period1") if isinstance(event.get("awayScore"), dict) else 0)

        return {
            "sofascore_id": int(event_id),
            "status_raw": status_raw,
            "status": status,
            "finished": status == "finished",
            "home_score": home_goals,
            "away_score": away_goals,
            "ht_home": home_period1,
            "ht_away": away_period1,
            "total_goals": home_goals + away_goals,
            "result": "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D",
            "ht_result": "H" if home_period1 > away_period1 else "A" if home_period1 < away_period1 else "D",
            "btts": home_goals > 0 and away_goals > 0,
            "match_timestamp": _safe_int(event.get("startTimestamp")),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

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
        home_big_chances = stats.get("big chances", {}).get("home", 0.0)
        away_big_chances = stats.get("big chances", {}).get("away", 0.0)
        home_xg = stats.get("expected goals", {}).get("home", 0.0)
        away_xg = stats.get("expected goals", {}).get("away", 0.0)
        if home_xg <= 0:
            home_xg = self._estimate_xg(float(home_shots), float(home_sot), float(home_big_chances))
        if away_xg <= 0:
            away_xg = self._estimate_xg(float(away_shots), float(away_sot), float(away_big_chances))

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
    def _normalize_stat_key(value: str) -> str:
        return "".join(ch for ch in str(value or "").lower() if ch.isalnum())

    def _find_numeric_value(self, payload: Any, key_candidates: List[str]) -> Optional[float]:
        targets = [self._normalize_stat_key(item) for item in key_candidates]

        def walk(node: Any) -> Optional[float]:
            if isinstance(node, dict):
                for key, value in node.items():
                    key_norm = self._normalize_stat_key(str(key))
                    if key_norm in targets and not isinstance(value, (dict, list)):
                        parsed = _safe_float(value, fallback=float("nan"))
                        if parsed == parsed:
                            return parsed
                    nested = walk(value)
                    if nested is not None:
                        return nested
            elif isinstance(node, list):
                for item in node:
                    nested = walk(item)
                    if nested is not None:
                        return nested
            return None

        return walk(payload)

    def _extract_event_nodes(self, payload: Any) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        rows: List[Dict[str, Any]] = []

        def add_event(node: Dict[str, Any]) -> None:
            home = node.get("homeTeam")
            away = node.get("awayTeam")
            if not isinstance(home, dict) or not isinstance(away, dict):
                return
            event_id = _safe_int(node.get("id"))
            key = str(event_id) if event_id > 0 else f"{_safe_int(node.get('startTimestamp'))}:{home.get('name')}:{away.get('name')}"
            if key in seen:
                return
            seen.add(key)
            rows.append(node)

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                add_event(node)
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)
        return rows

    def _extract_team_stat_nodes(self, payload: Any) -> List[Dict[str, Any]]:
        seen: set[int] = set()
        rows: List[Dict[str, Any]] = []

        def push(node: Dict[str, Any]) -> None:
            team = node.get("team") if isinstance(node.get("team"), dict) else {}
            team_id = _safe_int(team.get("id"))
            if team_id <= 0 or team_id in seen:
                return
            seen.add(team_id)
            rows.append(node)

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                push(node)
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)
        return rows

    async def get_team_halftime_statistics(
        self,
        team_id: str,
        sofascore_team_id: int,
        season: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if sofascore_team_id <= 0:
            return None
        params: Dict[str, Any] = {}
        if season:
            params["season"] = season
        payload = await self._request(f"/team/{sofascore_team_id}/statistics", params=params, ttl_seconds=3600)
        if payload is None:
            return None

        goals_scored_first_half = self._find_numeric_value(
            payload,
            [
                "goalsScoredFirstHalf",
                "goalsForFirstHalf",
                "firstHalfGoalsScored",
                "scoredFirstHalf",
                "gsh1",
            ],
        )
        goals_conceded_first_half = self._find_numeric_value(
            payload,
            [
                "goalsConcededFirstHalf",
                "goalsAgainstFirstHalf",
                "firstHalfGoalsConceded",
                "concededFirstHalf",
            ],
        )
        goals_scored_total = self._find_numeric_value(
            payload,
            ["goalsScoredTotal", "goalsScored", "goalsForTotal", "goalsFor"],
        )
        goals_conceded_total = self._find_numeric_value(
            payload,
            ["goalsConcededTotal", "goalsConceded", "goalsAgainstTotal", "goalsAgainst"],
        )
        matches_played = self._find_numeric_value(payload, ["matchesPlayed", "played", "gamesPlayed", "matches"])
        matches_count = max(1.0, goals_scored_total if matches_played is None else matches_played)

        if goals_scored_first_half is None and goals_scored_total is not None:
            goals_scored_first_half = goals_scored_total * 0.42
        if goals_conceded_first_half is None and goals_conceded_total is not None:
            goals_conceded_first_half = goals_conceded_total * 0.40
        if goals_scored_total is None:
            goals_scored_total = max(1.0, (goals_scored_first_half or 0.0) / 0.42)
        if goals_conceded_total is None:
            goals_conceded_total = max(1.0, (goals_conceded_first_half or 0.0) / 0.40)

        ht_ratio = (
            (float(goals_scored_first_half) / float(goals_scored_total))
            if float(goals_scored_total) > 0
            else 0.42
        )
        record = {
            "team_id": team_id,
            "season": str(season or ""),
            "ht_goals_scored_avg": round(float(goals_scored_first_half) / matches_count, 2),
            "ht_goals_conceded_avg": round(float(goals_conceded_first_half) / matches_count, 2),
            "ht_goals_ratio": round(max(0.25, min(0.6, ht_ratio)), 2),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.supabase is not None:
            try:
                self.supabase.table("ht_stats").upsert(record, on_conflict="team_id,season").execute()
            except Exception:
                logger.warning("ht_stats upsert skipped (table may be missing). team_id=%s", team_id)
        return record

    async def get_tournament_season_overall_statistics(
        self,
        tournament_id: int,
        season_id: int,
    ) -> Optional[List[Dict[str, Any]]]:
        if tournament_id <= 0 or season_id <= 0:
            return None
        payload = await self._request(
            f"/unique-tournament/{tournament_id}/season/{season_id}/statistics/overall",
            ttl_seconds=3600,
        )
        if payload is None:
            return None
        stats_list = self._extract_team_stat_nodes(payload if isinstance(payload, dict) else {})
        if not stats_list:
            direct = payload.get("statistics", []) if isinstance(payload, dict) else []
            if isinstance(direct, list):
                stats_list = [row for row in direct if isinstance(row, dict)]
        if not stats_list:
            return []
        normalized: List[Dict[str, Any]] = []
        for row in stats_list:
            if not isinstance(row, dict):
                continue
            expected_goals = self._find_numeric_value(row, ["expectedGoals", "xg"])
            shots_on_target = self._find_numeric_value(row, ["shotsOnTarget", "sot"])
            big_chances = self._find_numeric_value(row, ["bigChances"])
            possession = self._find_numeric_value(row, ["ballPossession", "possession"])
            goals_for = self._find_numeric_value(row, ["goalsScored", "goalsFor", "scoresFor"])
            goals_against = self._find_numeric_value(row, ["goalsConceded", "goalsAgainst", "scoresAgainst"])
            assists = self._find_numeric_value(row, ["assists"])
            clean_sheets = self._find_numeric_value(row, ["cleanSheets", "cleanSheet"])
            matches_played = self._find_numeric_value(row, ["matches", "matchesPlayed", "gamesPlayed", "played"])
            avg_rating = self._find_numeric_value(row, ["averageRating", "sofascoreRating", "rating"])
            per_match_divisor = max(1.0, float(matches_played or 0.0))
            normalized.append(
                {
                    "tournament_id": tournament_id,
                    "season_id": season_id,
                    "team_sofascore_id": _safe_int((row.get("team") or {}).get("id") if isinstance(row.get("team"), dict) else 0),
                    "expected_goals": round(float(expected_goals or 0.0), 3),
                    "shots_on_target": round(float(shots_on_target or 0.0), 3),
                    "big_chances": round(float(big_chances or 0.0), 3),
                    "possession": round(float(possession or 0.0), 3),
                    "goals_for": round(float(goals_for or 0.0), 3),
                    "goals_against": round(float(goals_against or 0.0), 3),
                    "matches_played": int(round(float(matches_played or 0.0))),
                    "goals_per_match": round(float(goals_for or 0.0) / per_match_divisor, 3),
                    "goals_conceded_per_match": round(float(goals_against or 0.0) / per_match_divisor, 3),
                    "assists": int(round(float(assists or 0.0))),
                    "clean_sheets": int(round(float(clean_sheets or 0.0))),
                    "avg_rating": round(float(avg_rating or 0.0), 3),
                }
            )
        return normalized

    async def get_team_season_statistics(
        self,
        team_id: int,
        tournament_id: int,
        season_id: int,
    ) -> Optional[Dict[str, Any]]:
        if team_id <= 0 or tournament_id <= 0 or season_id <= 0:
            return None
        payload = await self._request(
            f"/team/{team_id}/unique-tournament/{tournament_id}/season/{season_id}/statistics/overall",
            ttl_seconds=3600,
        )
        if payload is None:
            return None
        stats = payload.get("statistics", {}) if isinstance(payload, dict) else {}
        if not isinstance(stats, dict) or not stats:
            return {}

        matches_played = int(
            round(
                float(
                    self._find_numeric_value(
                        stats,
                        ["matches", "matchesPlayed", "gamesPlayed", "played", "appearances"],
                    )
                    or 0.0
                )
            )
        )
        goals_for = float(self._find_numeric_value(stats, ["goalsScored", "goalsFor", "scoresFor"]) or 0.0)
        goals_against = float(self._find_numeric_value(stats, ["goalsConceded", "goalsAgainst", "scoresAgainst"]) or 0.0)
        assists = float(self._find_numeric_value(stats, ["assists"]) or 0.0)
        clean_sheets = float(self._find_numeric_value(stats, ["cleanSheets", "cleanSheet"]) or 0.0)
        expected_goals_raw = float(
            self._find_numeric_value(
                stats,
                ["expectedGoals", "xg", "expectedGoalsFor", "xgFor"],
            )
            or 0.0
        )
        shots_on_target_total = float(
            self._find_numeric_value(
                stats,
                ["shotsOnTarget", "sot", "shotsOnTargetTotal"],
            )
            or 0.0
        )
        big_chances_total = float(
            self._find_numeric_value(
                stats,
                ["bigChances", "bigChancesCreated"],
            )
            or 0.0
        )
        possession = float(
            self._find_numeric_value(
                stats,
                ["averageBallPossession", "ballPossession", "possession"],
            )
            or 0.0
        )
        avg_rating = float(
            self._find_numeric_value(
                stats,
                ["avgRating", "averageRating", "sofascoreRating", "rating"],
            )
            or 0.0
        )

        per_match_divisor = float(matches_played) if matches_played > 0 else 1.0
        expected_goals = (
            expected_goals_raw / per_match_divisor
            if expected_goals_raw > 0 and expected_goals_raw > 5.0 and matches_played > 0
            else expected_goals_raw
        )
        if expected_goals <= 0 and matches_played > 0 and goals_for > 0:
            expected_goals = goals_for / per_match_divisor

        normalized = {
            "team_sofascore_id": team_id,
            "tournament_id": tournament_id,
            "season_id": season_id,
            "matches_played": matches_played,
            "goals_for": round(goals_for, 3),
            "goals_against": round(goals_against, 3),
            "goals_per_match": round(goals_for / per_match_divisor, 3),
            "goals_conceded_per_match": round(goals_against / per_match_divisor, 3),
            "clean_sheets": int(round(clean_sheets)),
            "assists": int(round(assists)),
            "expected_goals": round(expected_goals, 3),
            "shots_on_target": round(shots_on_target_total / per_match_divisor, 3),
            "big_chances": round(big_chances_total / per_match_divisor, 3),
            "possession": round(possession, 3),
            "avg_rating": round(avg_rating, 3),
        }
        team_uuid = self._resolve_team_uuid_by_sofascore_id(team_id)
        if team_uuid:
            self._upsert_team_season_stats_cache(team_id=team_uuid, payload=normalized)
        return normalized

    async def get_tournament_standings(
        self,
        tournament_id: int,
        season_id: int,
    ) -> Optional[List[Dict[str, Any]]]:
        if tournament_id <= 0 or season_id <= 0:
            return None
        payload = await self._request(
            f"/unique-tournament/{tournament_id}/season/{season_id}/standings/total",
            ttl_seconds=1800,
        )
        if payload is None:
            return None

        standings_nodes = payload.get("standings", []) if isinstance(payload, dict) else []
        if not isinstance(standings_nodes, list) or not standings_nodes:
            return []
        rows = standings_nodes[0].get("rows", []) if isinstance(standings_nodes[0], dict) else []
        if not isinstance(rows, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            team_node = row.get("team", {}) if isinstance(row.get("team"), dict) else {}
            team_id = _safe_int(team_node.get("id"))
            if team_id <= 0:
                continue
            scores_for = _safe_int(row.get("scoresFor"))
            scores_against = _safe_int(row.get("scoresAgainst"))
            normalized.append(
                {
                    "team_sofascore_id": team_id,
                    "team_name": str(team_node.get("name") or ""),
                    "position": _safe_int(row.get("position")),
                    "played": _safe_int(row.get("matches")),
                    "wins": _safe_int(row.get("wins")),
                    "draws": _safe_int(row.get("draws")),
                    "losses": _safe_int(row.get("losses")),
                    "points": _safe_int(row.get("points")),
                    "goals_for": scores_for,
                    "goals_against": scores_against,
                    "goal_diff": scores_for - scores_against,
                    "form": row.get("form"),
                }
            )
        if normalized:
            self._upsert_league_standings_cache(
                tournament_id=tournament_id,
                season_id=season_id,
                rows=normalized,
            )
        return normalized

    async def get_event_odds_history(self, event_id: int) -> Optional[List[Dict[str, Any]]]:
        payload = await self._request(f"/event/{event_id}/odds/1/all", ttl_seconds=300)
        if payload is None:
            return None
        markets = payload.get("markets", []) if isinstance(payload, dict) else []
        if not isinstance(markets, list):
            return []
        rows: List[Dict[str, Any]] = []
        for market in markets:
            if not isinstance(market, dict):
                continue
            market_name = str(market.get("marketName") or market.get("name") or "Unknown")
            choices = market.get("choices") if isinstance(market.get("choices"), list) else market.get("outcomes", [])
            for outcome in choices if isinstance(choices, list) else []:
                if not isinstance(outcome, dict):
                    continue
                outcome_name = str(outcome.get("name") or outcome.get("choice") or "Unknown")
                current_odd = _safe_float(outcome.get("odds"), fallback=0.0)
                if current_odd <= 0:
                    current_odd = _safe_float(outcome.get("decimalValue"), fallback=0.0)
                opening_odd = _safe_float(outcome.get("openingOdds"), fallback=0.0)
                if opening_odd <= 0:
                    opening_odd = _safe_float(outcome.get("initialOdds"), fallback=0.0)
                if opening_odd <= 0:
                    opening_odd = current_odd
                movement_pct = ((opening_odd - current_odd) / opening_odd * 100.0) if opening_odd > 0 else 0.0
                rows.append(
                    {
                        "event_id": event_id,
                        "market_type": f"{market_name}:{outcome_name}",
                        "opening_odd": round(float(opening_odd), 4),
                        "current_odd": round(float(current_odd), 4),
                        "movement_pct": round(float(movement_pct), 2),
                    }
                )
        return rows

    async def get_team_top_players(
        self,
        team_id: int,
        limit: int = 5,
        tournament_id: Optional[int] = None,
        season_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if team_id <= 0:
            return []

        payloads: List[Dict[str, Any]] = []
        season_top_loaded = False
        if (tournament_id or 0) > 0 and (season_id or 0) > 0:
            season_endpoint = (
                f"/team/{team_id}/unique-tournament/{int(tournament_id or 0)}/season/{int(season_id or 0)}/top-players/overall"
            )
            season_payload = await self._request(season_endpoint, ttl_seconds=3600)
            if isinstance(season_payload, dict):
                payloads.append(season_payload)
                top_players_node = season_payload.get("topPlayers")
                season_top_loaded = bool(
                    (isinstance(top_players_node, dict) and top_players_node)
                    or (isinstance(top_players_node, list) and top_players_node)
                )

        if not season_top_loaded:
            fallback_endpoints = [
                f"/team/{team_id}/top-players/overall",
                f"/team/{team_id}/top-players",
                f"/team/{team_id}/players",
            ]
            for endpoint in fallback_endpoints:
                payload = await self._request(endpoint, ttl_seconds=3600)
                if isinstance(payload, dict):
                    payloads.append(payload)

        if not payloads:
            return []

        rows_by_key: Dict[str, Dict[str, Any]] = {}

        def upsert_row(player_node: Dict[str, Any], source_node: Dict[str, Any], metric_hint: str = "") -> None:
            name = str(player_node.get("name") or source_node.get("name") or "").strip()
            if not name:
                return
            player_id = _safe_int(player_node.get("id") or source_node.get("id"))
            key = f"id:{player_id}" if player_id > 0 else f"name:{_normalize_name(name)}"
            stats = source_node.get("statistics", {}) if isinstance(source_node.get("statistics"), dict) else {}

            rating = _safe_float(stats.get("rating"), fallback=0.0)
            if rating <= 0 and metric_hint == "rating":
                rating = _safe_float(stats.get("value"), fallback=0.0)
            if rating <= 0:
                rating = _safe_float(source_node.get("rating"), fallback=0.0)
            if rating <= 0:
                rating = _safe_float(source_node.get("averageRating"), fallback=0.0)
            if rating <= 0:
                rating = _safe_float(source_node.get("sofascoreRating"), fallback=0.0)
            if rating <= 0:
                nested_rating = self._find_numeric_value(
                    source_node,
                    [
                        "rating",
                        "averageRating",
                        "avgRating",
                        "sofascoreRating",
                        "averageSofascoreRating",
                        "ratingAverage",
                    ],
                )
                rating = float(nested_rating or 0.0)

            appearances = _safe_int(stats.get("appearances"))
            if appearances <= 0:
                appearances = _safe_int(source_node.get("appearances"))
            if appearances <= 0:
                nested_appearances = self._find_numeric_value(
                    source_node,
                    ["appearances", "matchesPlayed", "gamesPlayed"],
                )
                appearances = int(round(float(nested_appearances or 0.0)))

            minutes = _safe_int(stats.get("minutesPlayed"))
            if minutes <= 0:
                minutes = _safe_int(source_node.get("minutesPlayed"))
            if minutes <= 0:
                minutes = _safe_int(source_node.get("minutes"))
            if minutes <= 0:
                nested_minutes = self._find_numeric_value(
                    source_node,
                    ["minutesPlayed", "minutes", "playedMinutes", "minutesTotal"],
                )
                minutes = int(round(float(nested_minutes or 0.0)))
            if minutes <= 0 and appearances > 0:
                minutes = appearances * 90

            row = {
                "player_id": player_id if player_id > 0 else None,
                "name": name,
                "position": str(player_node.get("position") or source_node.get("position") or ""),
                "rating": round(float(rating), 2),
                "minutes_played": int(minutes),
                "appearances": int(appearances),
            }
            existing = rows_by_key.get(key)
            if existing is None:
                rows_by_key[key] = row
                return
            current_tuple = (
                float(row.get("rating", 0.0) or 0.0),
                int(row.get("minutes_played", 0) or 0),
                int(row.get("appearances", 0) or 0),
            )
            existing_tuple = (
                float(existing.get("rating", 0.0) or 0.0),
                int(existing.get("minutes_played", 0) or 0),
                int(existing.get("appearances", 0) or 0),
            )
            if current_tuple > existing_tuple:
                rows_by_key[key] = row

        def walk(node: Any, metric_hint: str = "") -> None:
            if isinstance(node, dict):
                top_players = node.get("topPlayers")
                if isinstance(top_players, dict):
                    for metric, items in top_players.items():
                        if isinstance(items, list):
                            for item in items:
                                if not isinstance(item, dict):
                                    continue
                                player = item.get("player") if isinstance(item.get("player"), dict) else {}
                                if player:
                                    upsert_row(player, item, metric_hint=str(metric))
                        elif isinstance(items, dict):
                            walk(items, metric_hint=str(metric))
                elif isinstance(top_players, list):
                    for item in top_players:
                        if not isinstance(item, dict):
                            continue
                        player = item.get("player") if isinstance(item.get("player"), dict) else {}
                        if player:
                            upsert_row(player, item, metric_hint=metric_hint)

                player = node.get("player") if isinstance(node.get("player"), dict) else None
                if isinstance(player, dict) and (player.get("name") or node.get("name")):
                    upsert_row(player, node, metric_hint=metric_hint)
                elif node.get("name") and (node.get("position") is not None or node.get("rating") is not None):
                    upsert_row(node, node, metric_hint=metric_hint)

                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value, metric_hint=metric_hint)
            elif isinstance(node, list):
                for item in node:
                    walk(item, metric_hint=metric_hint)

        for payload in payloads:
            walk(payload)

        rows = list(rows_by_key.values())
        rows.sort(
            key=lambda row: (
                float(row.get("rating", 0.0) or 0.0),
                int(row.get("minutes_played", 0) or 0),
                int(row.get("appearances", 0) or 0),
            ),
            reverse=True,
        )
        selected = rows[: max(1, int(limit))]
        for row in selected:
            row.pop("appearances", None)
        team_uuid = self._resolve_team_uuid_by_sofascore_id(team_id)
        if team_uuid and selected:
            self._replace_team_top_players_cache(
                team_id=team_uuid,
                team_sofascore_id=team_id,
                players=selected,
                tournament_id=tournament_id,
                season_id=season_id,
            )
        return selected

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
        form_points_last6: List[int] = []
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
            shots_against = stats_map.get("total shots", {}).get(opp_key, 0.0)
            shots_on_target_against = stats_map.get("shots on target", {}).get(opp_key, 0.0)
            big_chances_for = stats_map.get("big chances", {}).get(side_key, 0.0)
            big_chances_against = stats_map.get("big chances", {}).get(opp_key, 0.0)
            possession = stats_map.get("ball possession", {}).get(side_key, 0.0)
            if float(xg_for) <= 0:
                xg_for = self._estimate_xg(float(shots), float(shots_on_target), float(big_chances_for))
            if float(xg_against) <= 0:
                xg_against = self._estimate_xg(
                    float(shots_against),
                    float(shots_on_target_against),
                    float(big_chances_against),
                )

            if goals_for > goals_against:
                form_points_last6.append(3)
            elif goals_for == goals_against:
                form_points_last6.append(1)
            else:
                form_points_last6.append(0)
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

        last6 = form_points_last6[:6]
        form_last6 = round(sum(last6) / 18.0, 3) if last6 else 0.0
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

    async def get_team_recent_matches(self, sofascore_team_id: int, limit: int = 6) -> List[Dict[str, Any]]:
        if sofascore_team_id <= 0:
            return []
        target = max(1, limit)
        events: List[Dict[str, Any]] = []
        seen_event_ids: set[int] = set()
        offsets = [0]
        if target > 20:
            max_offset = min(160, (((target - 1) // 20) + 1) * 20)
            offsets.extend(list(range(20, max_offset + 20, 20)))
        for offset in offsets:
            payload = await self._request(f"/team/{sofascore_team_id}/events/last/{offset}", ttl_seconds=1200)
            if payload is None:
                if offset > 0:
                    break
                continue
            batch = payload.get("events", []) if isinstance(payload, dict) else []
            if not isinstance(batch, list) or not batch:
                if offset > 0:
                    break
                continue
            for item in batch:
                if not isinstance(item, dict):
                    continue
                event_id = _safe_int(item.get("id"))
                if event_id > 0 and event_id in seen_event_ids:
                    continue
                if event_id > 0:
                    seen_event_ids.add(event_id)
                events.append(item)
            if len(events) >= target:
                break

        rows: List[Dict[str, Any]] = []
        for event in events:
            if len(rows) >= target:
                break
            if not isinstance(event, dict):
                continue
            status_type = str(event.get("status", {}).get("type", "")).lower() if isinstance(event.get("status"), dict) else ""
            if status_type not in {"finished", "ended"}:
                continue
            side = self._event_team_side(event, sofascore_team_id)
            if side is None:
                continue

            home_goals, away_goals = self._event_goals(event)
            is_home = side == "home"
            goals_for = home_goals if is_home else away_goals
            goals_against = away_goals if is_home else home_goals
            result = self._result_code(goals_for, goals_against)

            timestamp = _safe_int(event.get("startTimestamp"))
            event_date = (
                datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
                if timestamp > 0
                else datetime.now(timezone.utc).isoformat()
            )
            home_team = event.get("homeTeam", {}) if isinstance(event.get("homeTeam"), dict) else {}
            away_team = event.get("awayTeam", {}) if isinstance(event.get("awayTeam"), dict) else {}
            tournament = event.get("tournament", {}) if isinstance(event.get("tournament"), dict) else {}
            unique = tournament.get("uniqueTournament", {}) if isinstance(tournament.get("uniqueTournament"), dict) else {}
            league_name = str(unique.get("name") or tournament.get("name") or "Unknown")
            tournament_id = _safe_int(unique.get("id") or tournament.get("id"))
            is_cup = bool(event.get("isTournament", False)) or (
                tournament_id > 0 and tournament_id not in SOFASCORE_TOURNAMENT_ID_SET
            )
            home_team_id = _safe_int(home_team.get("id"))
            away_team_id = _safe_int(away_team.get("id"))

            rows.append(
                {
                    "date": event_date,
                    "home_team_name": str(home_team.get("name") or "Home"),
                    "away_team_name": str(away_team.get("name") or "Away"),
                    "home_team_id": home_team_id if home_team_id > 0 else None,
                    "away_team_id": away_team_id if away_team_id > 0 else None,
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "result": result,
                    "is_home": is_home,
                    "event_id": _safe_int(event.get("id")),
                    "league": league_name,
                    "is_cup": is_cup,
                }
            )
        return rows

    async def get_match_injuries(self, sofascore_event_id: int) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        payload = await self._request(f"/event/{sofascore_event_id}/lineups", ttl_seconds=300)
        if payload is None:
            return None
        home_payload = payload.get("home", {}) if isinstance(payload.get("home"), dict) else {}
        away_payload = payload.get("away", {}) if isinstance(payload.get("away"), dict) else {}
        injuries = {
            "home": self._extract_missing_players(home_payload),
            "away": self._extract_missing_players(away_payload),
        }
        match = self._resolve_internal_match(sofascore_event_id)
        if match and self.supabase is not None:
            try:
                home_saved = self._save_match_injuries(
                    match_id=str(match["id"]),
                    team_id=str(match["home_team_id"]),
                    entries=injuries["home"],
                )
                away_saved = self._save_match_injuries(
                    match_id=str(match["id"]),
                    team_id=str(match["away_team_id"]),
                    entries=injuries["away"],
                )
                logger.info(
                    "match_injuries guncellendi. event_id=%s home=%s away=%s",
                    sofascore_event_id,
                    home_saved,
                    away_saved,
                )
            except Exception:
                logger.exception("match_injuries persist failed. event_id=%s", sofascore_event_id)
        return injuries

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
        try:
            home_injuries = self._extract_missing_players(home if isinstance(home, dict) else {})
            away_injuries = self._extract_missing_players(away if isinstance(away, dict) else {})
            self._save_match_injuries(
                match_id=str(match["id"]),
                team_id=str(match["home_team_id"]),
                entries=home_injuries,
            )
            self._save_match_injuries(
                match_id=str(match["id"]),
                team_id=str(match["away_team_id"]),
                entries=away_injuries,
            )
        except Exception:
            logger.exception("lineup injuries save failed. event_id=%s", event_id)
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
        match = self._resolve_internal_match(sofascore_event_id)

        payload = await self._request(f"/event/{sofascore_event_id}/h2h/events", ttl_seconds=1200)
        events = self._extract_event_nodes(payload if isinstance(payload, dict) else {})

        home_wins = 0
        away_wins = 0
        draws = 0
        weighted_home = 0.0
        weighted_total = 0.0
        response_matches: List[Dict[str, Any]] = []
        db_rows: List[Dict[str, Any]] = []

        if isinstance(events, list) and events:
            for item in events[:10]:
                if not isinstance(item, dict):
                    continue

                event_id = _safe_int(item.get("id"))
                home_node = item.get("homeTeam", {}) if isinstance(item.get("homeTeam"), dict) else {}
                away_node = item.get("awayTeam", {}) if isinstance(item.get("awayTeam"), dict) else {}
                event_home_id = _safe_int(home_node.get("id"))
                event_away_id = _safe_int(away_node.get("id"))
                event_home_name = str(home_node.get("name") or "Home")
                event_away_name = str(away_node.get("name") or "Away")
                event_home_goals, event_away_goals = self._event_goals(item)
                timestamp = _safe_int(item.get("startTimestamp"))
                match_date = (
                    datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
                    if timestamp > 0
                    else datetime.now(timezone.utc).isoformat()
                )

                tournament = item.get("tournament", {}) if isinstance(item.get("tournament"), dict) else {}
                unique = tournament.get("uniqueTournament", {}) if isinstance(tournament.get("uniqueTournament"), dict) else {}
                tournament_id = _safe_int(unique.get("id"))
                league_name = str(unique.get("name") or tournament.get("name") or "Unknown")
                is_cup = bool(item.get("isTournament", False)) or (
                    tournament_id > 0 and tournament_id not in SOFASCORE_TOURNAMENT_ID_SET
                )
                weight = 0.3 if is_cup else 0.7

                side = self._event_team_side(item, focus_home_team) if focus_home_team > 0 else None
                if side == "home":
                    focus_goals = event_home_goals
                    opp_goals = event_away_goals
                elif side == "away":
                    focus_goals = event_away_goals
                    opp_goals = event_home_goals
                else:
                    focus_goals = event_home_goals
                    opp_goals = event_away_goals

                if focus_home_team > 0:
                    weighted_total += weight
                    if focus_goals > opp_goals:
                        home_wins += 1
                        weighted_home += weight
                    elif focus_goals < opp_goals:
                        away_wins += 1
                    else:
                        draws += 1

                response_matches.append(
                    {
                        "date": match_date[:10],
                        "match_date": match_date,
                        "home_team": event_home_name,
                        "away_team": event_away_name,
                        "home_goals": event_home_goals,
                        "away_goals": event_away_goals,
                        "league": league_name,
                        "sofascore_id": event_id if event_id > 0 else None,
                        "is_cup": is_cup,
                        "teams": {
                            "home": {"id": event_home_id, "name": event_home_name},
                            "away": {"id": event_away_id, "name": event_away_name},
                        },
                        "goals": {"home": event_home_goals, "away": event_away_goals},
                    }
                )

                if match:
                    db_rows.append(
                        {
                            "match_date": match_date,
                            "home_goals": focus_goals,
                            "away_goals": opp_goals,
                            "league": league_name,
                            "sofascore_id": event_id if event_id > 0 else None,
                            "is_cup": is_cup,
                        }
                    )

            if match and db_rows:
                self._save_h2h_rows(
                    home_team_id=str(match["home_team_id"]),
                    away_team_id=str(match["away_team_id"]),
                    rows=db_rows,
                )

            total = home_wins + away_wins + draws
            ratio = round(weighted_home / weighted_total, 4) if weighted_total > 0 else 0.5
            return {
                "home_wins": home_wins,
                "away_wins": away_wins,
                "draws": draws,
                "ratio": ratio,
                "home_win_rate": round(home_wins / total, 4) if total > 0 else ratio,
                "matches": response_matches[:5],
                "last5": response_matches[:5],
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
            "home_win_rate": ratio,
            "matches": [],
            "last5": [],
        }

    async def get_h2h_matches(self, home_sofascore_id: int, away_sofascore_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        if home_sofascore_id <= 0 or away_sofascore_id <= 0:
            return []
        max_rows = max(1, limit)
        events: List[Dict[str, Any]] = []
        endpoints = [
            f"/team/{home_sofascore_id}/h2h/{away_sofascore_id}",
            f"/team/{away_sofascore_id}/h2h/{home_sofascore_id}",
            f"/team/{home_sofascore_id}/h2h/events/{away_sofascore_id}",
            f"/team/{away_sofascore_id}/h2h/events/{home_sofascore_id}",
        ]
        for endpoint in endpoints:
            payload = await self._request(endpoint, ttl_seconds=1200)
            candidate = self._extract_event_nodes(payload if isinstance(payload, dict) else {})
            if isinstance(candidate, list) and candidate:
                events = candidate
                break

        normalized: List[Dict[str, Any]] = []
        for item in events[:max_rows]:
            if not isinstance(item, dict):
                continue
            home_node = item.get("homeTeam", {}) if isinstance(item.get("homeTeam"), dict) else {}
            away_node = item.get("awayTeam", {}) if isinstance(item.get("awayTeam"), dict) else {}
            event_home_goals, event_away_goals = self._event_goals(item)
            timestamp = _safe_int(item.get("startTimestamp"))
            match_date = (
                datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
                if timestamp > 0
                else datetime.now(timezone.utc).isoformat()
            )
            tournament = item.get("tournament", {}) if isinstance(item.get("tournament"), dict) else {}
            unique = tournament.get("uniqueTournament", {}) if isinstance(tournament.get("uniqueTournament"), dict) else {}
            league_name = str(unique.get("name") or tournament.get("name") or "Unknown")
            normalized.append(
                {
                    "date": match_date[:10],
                    "match_date": match_date,
                    "home_team": str(home_node.get("name") or "Home"),
                    "away_team": str(away_node.get("name") or "Away"),
                    "home_goals": event_home_goals,
                    "away_goals": event_away_goals,
                    "league": league_name,
                    "sofascore_id": _safe_int(item.get("id")) or None,
                }
            )
        if normalized:
            return normalized[:max_rows]

        recent_history = await self.get_team_recent_matches(home_sofascore_id, limit=max(max_rows * 20, 120))
        derived: List[Dict[str, Any]] = []
        for row in recent_history:
            if not isinstance(row, dict):
                continue
            event_home_id = _safe_int(row.get("home_team_id"))
            event_away_id = _safe_int(row.get("away_team_id"))
            if event_home_id <= 0 or event_away_id <= 0:
                continue
            if not (
                (event_home_id == home_sofascore_id and event_away_id == away_sofascore_id)
                or (event_home_id == away_sofascore_id and event_away_id == home_sofascore_id)
            ):
                continue
            derived.append(
                {
                    "date": str(row.get("date") or "")[:10],
                    "match_date": row.get("date"),
                    "home_team": row.get("home_team_name"),
                    "away_team": row.get("away_team_name"),
                    "home_goals": int(row.get("home_goals", 0) or 0),
                    "away_goals": int(row.get("away_goals", 0) or 0),
                    "league": row.get("league"),
                    "sofascore_id": _safe_int(row.get("event_id")) or None,
                    "is_cup": bool(row.get("is_cup", False)),
                }
            )
        if derived:
            return derived[:max_rows]

        if self.supabase is None or not self._has_column("teams", "sofascore_id"):
            return []
        try:
            team_rows = (
                self.supabase.table("teams")
                .select("id,sofascore_id")
                .in_("sofascore_id", [home_sofascore_id, away_sofascore_id])
                .execute()
                .data
                or []
            )
        except Exception:
            return []
        by_sofascore = {_safe_int(row.get("sofascore_id")): row for row in team_rows}
        home_team_row = by_sofascore.get(home_sofascore_id)
        away_team_row = by_sofascore.get(away_sofascore_id)
        if not home_team_row or not away_team_row:
            return []

        home_uuid = str(home_team_row.get("id") or "")
        away_uuid = str(away_team_row.get("id") or "")
        if not home_uuid or not away_uuid:
            return []

        candidates: List[Dict[str, Any]] = []
        try:
            direct = (
                self.supabase.table("matches")
                .select("sofascore_id,match_date")
                .eq("home_team_id", home_uuid)
                .eq("away_team_id", away_uuid)
                .not_.is_("sofascore_id", "null")
                .order("match_date", desc=True)
                .limit(1)
                .execute()
            )
            reverse = (
                self.supabase.table("matches")
                .select("sofascore_id,match_date")
                .eq("home_team_id", away_uuid)
                .eq("away_team_id", home_uuid)
                .not_.is_("sofascore_id", "null")
                .order("match_date", desc=True)
                .limit(1)
                .execute()
            )
            candidates.extend(direct.data or [])
            candidates.extend(reverse.data or [])
        except Exception:
            return []
        if not candidates:
            return []
        candidates.sort(key=lambda row: str(row.get("match_date") or ""), reverse=True)
        reference_event_id = _safe_int(candidates[0].get("sofascore_id"))
        if reference_event_id <= 0:
            return []
        summary = await self.get_h2h(reference_event_id)
        if not isinstance(summary, dict):
            return []
        matches = summary.get("matches", [])
        return matches[:max_rows] if isinstance(matches, list) else []

    async def close(self) -> None:
        return


_default_service = SofaScoreService()


def get_service() -> SofaScoreService:
    return _default_service


async def get_scheduled_events(date: str) -> Optional[List[Dict[str, Any]]]:
    return await _default_service.get_scheduled_events(date)


async def get_event_detail(event_id: int, *, ttl_seconds: int = 180) -> Optional[Dict[str, Any]]:
    return await _default_service.get_event_detail(event_id, ttl_seconds=ttl_seconds)


async def get_event_result(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_event_result(event_id)


async def get_event_statistics(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_event_statistics(event_id)


async def get_event_odds(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_event_odds(event_id)


async def get_team_performance(team_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_team_performance(team_id)


async def get_team_profile(team_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_team_profile(team_id)


async def sync_team_profile(team_id: str, sofascore_team_id: int, force: bool = False) -> Dict[str, Any]:
    return await _default_service.sync_team_profile(team_id, sofascore_team_id, force=force)


async def discover_teams_from_scheduled_events(date: str) -> List[Dict[str, Any]]:
    return await _default_service.discover_teams_from_scheduled_events(date)


async def discover_teams_from_standings(tournament_id: int, season_id: int) -> List[Dict[str, Any]]:
    return await _default_service.discover_teams_from_standings(tournament_id, season_id)


async def populate_team_stats_from_history(team_id: str, sofascore_team_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.populate_team_stats_from_history(team_id, sofascore_team_id)


async def populate_team_stats_for_match(match_id: str) -> Optional[Dict[str, Any]]:
    return await _default_service.populate_team_stats_for_match(match_id)


async def get_team_recent_matches(sofascore_team_id: int, limit: int = 6) -> List[Dict[str, Any]]:
    return await _default_service.get_team_recent_matches(sofascore_team_id, limit=limit)


async def get_team_halftime_statistics(
    team_id: str,
    sofascore_team_id: int,
    season: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    return await _default_service.get_team_halftime_statistics(team_id, sofascore_team_id, season=season)


async def get_tournament_season_overall_statistics(
    tournament_id: int,
    season_id: int,
) -> Optional[List[Dict[str, Any]]]:
    return await _default_service.get_tournament_season_overall_statistics(tournament_id, season_id)


async def get_team_season_statistics(
    team_id: int,
    tournament_id: int,
    season_id: int,
) -> Optional[Dict[str, Any]]:
    return await _default_service.get_team_season_statistics(team_id, tournament_id, season_id)


async def get_event_odds_history(event_id: int) -> Optional[List[Dict[str, Any]]]:
    return await _default_service.get_event_odds_history(event_id)


async def get_match_injuries(sofascore_event_id: int) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    return await _default_service.get_match_injuries(sofascore_event_id)


async def get_event_lineups(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_event_lineups(event_id)


async def get_event_pregame_form(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_event_pregame_form(event_id)


async def get_h2h(event_id: int) -> Optional[Dict[str, Any]]:
    return await _default_service.get_h2h(event_id)


async def get_h2h_matches(home_sofascore_id: int, away_sofascore_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    return await _default_service.get_h2h_matches(home_sofascore_id, away_sofascore_id, limit=limit)
