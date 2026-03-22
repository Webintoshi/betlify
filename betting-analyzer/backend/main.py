from __future__ import annotations

import asyncio
import logging
import os
import re
import unicodedata
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import Client, create_client

from api_football import get_service as get_api_service
from config import ENABLE_SOFASCORE_ENRICHMENT, TRACKED_LEAGUE_IDS
from pi_rating import calculate_pi_ratings
from prediction_engine.config.markets import SUPPORTED_MARKETS
from prediction_engine.engine import run as run_prediction_engine
from scheduler import BettingScheduler
from services.odds_scraper import get_service as get_odds_scraper_service
from services.result_processor import build_performance_summary, list_prediction_results, process_pending_predictions
from sofascore import get_service as get_sofascore_service
from transfermarkt import get_service as get_transfermarkt_service
from weather import get_service as get_weather_service

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env", override=True)

scheduler = BettingScheduler()
api_football = get_api_service()
odds_scraper = get_odds_scraper_service()
sofascore = get_sofascore_service() if ENABLE_SOFASCORE_ENRICHMENT else None
transfermarkt_service = get_transfermarkt_service()
weather_service = get_weather_service()
backfill_task: Optional[asyncio.Task[Any]] = None
SUPPORTED_MARKET_SET = set(SUPPORTED_MARKETS)
backfill_state: Dict[str, Any] = {
    "status": "idle",
    "running": False,
    "started_at": None,
    "finished_at": None,
    "last_result": None,
    "last_error": None,
}
reset_refetch_task: Optional[asyncio.Task[Any]] = None
reset_refetch_state: Dict[str, Any] = {
    "status": "idle",
    "running": False,
    "started_at": None,
    "finished_at": None,
    "processed": 0,
    "total_matches_scanned": 0,
    "success": 0,
    "failed": 0,
    "skipped_no_odds": 0,
    "last_error": None,
}
backtest_task: Optional[asyncio.Task[Any]] = None
backtest_state: Dict[str, Any] = {
    "status": "idle",
    "running": False,
    "started_at": None,
    "finished_at": None,
    "params": None,
    "processed": 0,
    "total_matches_scanned": 0,
    "success": 0,
    "failed": 0,
    "skipped_no_odds": 0,
    "skipped_no_market": 0,
    "summary": None,
    "rows": [],
    "last_error": None,
}
team_profile_backfill_task: Optional[asyncio.Task[Any]] = None
team_profile_backfill_state: Dict[str, Any] = {
    "status": "idle",
    "running": False,
    "started_at": None,
    "finished_at": None,
    "chunk_size": 0,
    "max_chunks": 0,
    "force": False,
    "chunks_completed": 0,
    "processed": 0,
    "updated": 0,
    "failed": 0,
    "pending_remaining": None,
    "last_result": None,
    "last_error": None,
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.set_match_analyzer(_run_match_analysis)
    scheduler.start()
    try:
        yield
    finally:
        await scheduler.shutdown()
        await weather_service.close()


app = FastAPI(title="Bahis Analiz Sistemi API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:7777",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_supabase_client() -> Client:
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not supabase_url or not supabase_service_key or "BURAYA_" in supabase_service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required.")
    try:
        return create_client(supabase_url, supabase_service_key)
    except Exception as exc:
        raise RuntimeError("Supabase credentials are invalid.") from exc


class AnalyzeRequest(BaseModel):
    confidence_threshold: float = Field(default=60.0, ge=0.0, le=100.0)


class CouponSelection(BaseModel):
    match_id: str
    home_team: str
    away_team: str
    market_type: str
    odd: float = Field(gt=0)
    confidence_score: float = Field(default=0.0, ge=0.0, le=100.0)
    ev_percentage: float = 0.0


class CouponCreateRequest(BaseModel):
    selections: List[CouponSelection]
    total_odds: Optional[float] = Field(default=None, gt=0)
    status: str = Field(default="pending")


class SettingsUpdateRequest(BaseModel):
    minimum_confidence: float = Field(default=60.0, ge=50.0, le=80.0)
    minimum_ev: float = Field(default=0.0, ge=0.0, le=20.0)
    tracked_leagues: List[int] = Field(default_factory=list)


class BacktestRunRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    days_back: int = Field(default=30, ge=3, le=365)
    league: Optional[str] = None
    min_confidence: float = Field(default=51.0, ge=0.0, le=100.0)
    include_non_recommended: bool = Field(default=True)
    max_matches: int = Field(default=300, ge=20, le=3000)
    store_rows: int = Field(default=500, ge=50, le=5000)


def _is_profile_stale(raw_value: Any, *, days: int = 7) -> bool:
    text = str(raw_value or "").strip()
    if not text:
        return True
    try:
        last_updated = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - last_updated) > timedelta(days=max(1, int(days)))


def _load_team_profile_cache_map(client: Client, team_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not team_ids:
        return {}
    try:
        rows = (
            client.table("team_profile_cache")
            .select("team_id,team_sofascore_id,team_name,country,logo_url,coach_name,coach_sofascore_id,sofascore_url,updated_at")
            .in_("team_id", team_ids)
            .execute()
            .data
            or []
        )
    except Exception:
        return {}
    return {
        str(row.get("team_id")): row
        for row in rows
        if isinstance(row, dict) and str(row.get("team_id") or "")
    }


def _count_pending_team_profiles(client: Client) -> int:
    try:
        result = (
            client.table("teams")
            .select("id", count="exact")
            .not_.is_("sofascore_id", "null")
            .in_("profile_sync_status", ["pending", "stale"])
            .limit(1)
            .execute()
        )
        return int(result.count or 0)
    except Exception:
        return 0


async def _run_team_profile_backfill(
    *,
    chunk_size: int,
    max_chunks: int,
    force: bool,
) -> None:
    team_profile_backfill_state.update(
        {
            "status": "running",
            "running": True,
            "started_at": datetime.now(scheduler.timezone).isoformat(),
            "finished_at": None,
            "chunk_size": chunk_size,
            "max_chunks": max_chunks,
            "force": bool(force),
            "chunks_completed": 0,
            "processed": 0,
            "updated": 0,
            "failed": 0,
            "pending_remaining": None,
            "last_result": None,
            "last_error": None,
        }
    )

    try:
        client = get_supabase_client()
        total_chunks = max(0, int(max_chunks))
        normalized_chunk = max(1, min(int(chunk_size), 1000))

        while True:
            if total_chunks > 0 and int(team_profile_backfill_state.get("chunks_completed") or 0) >= total_chunks:
                break

            result = await scheduler.refresh_sofascore_team_profiles(force=force, limit=normalized_chunk)
            processed = int(result.get("processed", 0) or 0)
            updated = int(result.get("updated", 0) or 0)
            failed = int(result.get("failed", 0) or 0)

            if processed <= 0:
                team_profile_backfill_state["last_result"] = result
                team_profile_backfill_state["pending_remaining"] = _count_pending_team_profiles(client)
                break

            team_profile_backfill_state["chunks_completed"] = int(team_profile_backfill_state.get("chunks_completed") or 0) + 1
            team_profile_backfill_state["processed"] = int(team_profile_backfill_state.get("processed") or 0) + processed
            team_profile_backfill_state["updated"] = int(team_profile_backfill_state.get("updated") or 0) + updated
            team_profile_backfill_state["failed"] = int(team_profile_backfill_state.get("failed") or 0) + failed
            team_profile_backfill_state["pending_remaining"] = _count_pending_team_profiles(client)
            team_profile_backfill_state["last_result"] = result
            await asyncio.sleep(1)

        team_profile_backfill_state.update(
            {
                "status": "completed",
                "running": False,
                "finished_at": datetime.now(scheduler.timezone).isoformat(),
            }
        )
    except Exception as exc:
        logger.exception("Team profile backfill failed.")
        team_profile_backfill_state.update(
            {
                "status": "failed",
                "running": False,
                "finished_at": datetime.now(scheduler.timezone).isoformat(),
                "last_error": str(exc),
            }
        )


async def _run_full_backfill() -> None:
    backfill_state.update(
        {
            "status": "running",
            "running": True,
            "started_at": datetime.now(scheduler.timezone).isoformat(),
            "finished_at": None,
            "last_error": None,
        }
    )
    logger.info("Full backfill basladi.")

    try:
        now = datetime.now(scheduler.timezone).date()
        date_window = [(now - timedelta(days=offset)).isoformat() for offset in range(14, -1, -1)]

        fixtures_result = await scheduler.fetch_specific_dates(date_window)

        sofascore_payload: Dict[str, Any] = {"enabled": bool(ENABLE_SOFASCORE_ENRICHMENT and sofascore is not None)}
        if ENABLE_SOFASCORE_ENRICHMENT and sofascore is not None:
            sofascore_total = 0
            sofascore_by_date: Dict[str, int] = {}
            for date_str in [now.isoformat(), (now + timedelta(days=1)).isoformat()]:
                rows = await sofascore.get_scheduled_events(date_str)
                count = len(rows or [])
                sofascore_total += count
                sofascore_by_date[date_str] = count
            sofascore_payload.update(
                {
                    "total_saved": sofascore_total,
                    "by_date": sofascore_by_date,
                    "daily_team_stats": await scheduler.populate_today_team_stats_history(),
                    "injuries_h2h": await scheduler.refresh_today_injuries_and_h2h(),
                }
            )
        else:
            sofascore_payload.update(
                {
                    "total_saved": 0,
                    "by_date": {},
                    "daily_team_stats": {"processed_matches": 0, "updated_teams": 0, "skipped": True},
                    "injuries_h2h": {"processed_matches": 0, "injury_rows": 0, "h2h_rows": 0, "skipped": True},
                }
            )

        odds_events_sync_result = await scheduler.sync_oddsapi_events()
        odds_refresh_result = await scheduler.refresh_oddsapi_odds()
        odds_results_result = await scheduler.reconcile_oddsapi_results()
        weekly_stats_result = await scheduler.update_weekly_team_stats()
        pi_rating_result = await scheduler.refresh_pi_ratings()

        result_payload = {
            "fixtures": fixtures_result,
            "sofascore": {
                "enabled": sofascore_payload.get("enabled", False),
                "total_saved": sofascore_payload.get("total_saved", 0),
                "by_date": sofascore_payload.get("by_date", {}),
            },
            "daily_team_stats": sofascore_payload.get("daily_team_stats"),
            "injuries_h2h": sofascore_payload.get("injuries_h2h"),
            "oddsapi_events_sync": odds_events_sync_result,
            "odds_refresh": odds_refresh_result,
            "odds_results_reconcile": odds_results_result,
            "weekly_team_stats": weekly_stats_result,
            "pi_rating": pi_rating_result,
        }

        backfill_state.update(
            {
                "status": "completed",
                "running": False,
                "finished_at": datetime.now(scheduler.timezone).isoformat(),
                "last_result": result_payload,
                "last_error": None,
            }
        )
        logger.info("Full backfill tamamlandi.")
    except Exception as exc:
        logger.exception("Full backfill basarisiz.")
        backfill_state.update(
            {
                "status": "failed",
                "running": False,
                "finished_at": datetime.now(scheduler.timezone).isoformat(),
                "last_error": str(exc),
            }
        )


async def _run_reset_and_refetch() -> None:
    reset_refetch_state.update(
        {
            "status": "running",
            "running": True,
            "started_at": datetime.now(scheduler.timezone).isoformat(),
            "finished_at": None,
            "processed": 0,
            "total_matches_scanned": 0,
            "success": 0,
            "failed": 0,
            "skipped_no_odds": 0,
            "last_error": None,
        }
    )
    try:
        client = get_supabase_client()
        try:
            client.table("predictions").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception:
            logger.warning("Prediction reset skipped.")
        try:
            client.table("market_probabilities").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception:
            logger.warning("Market probability reset skipped.")
        try:
            client.table("odds").update({"ev": None}).neq("id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception:
            logger.warning("Odds EV reset skipped.")

        try:
            client.table("matches").update({"confidence_score": 0, "best_bet": None}).neq("id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception:
            logger.warning("Match confidence/best_bet reset skipped.")

        try:
            matches: List[Dict[str, Any]] = []
            batch_size = 1000
            offset = 0
            while True:
                chunk = (
                    client.table("matches")
                    .select("id,match_date,status")
                    .order("match_date")
                    .range(offset, offset + batch_size - 1)
                    .execute()
                    .data
                    or []
                )
                if not chunk:
                    break
                matches.extend(chunk)
                if len(chunk) < batch_size:
                    break
                offset += batch_size
        except Exception:
            matches = []

        total_scanned = len(matches)
        success = 0
        failed = 0
        skipped_no_odds = 0

        for idx, match in enumerate(matches, start=1):
            match_id = str(match.get("id") or "").strip()
            if not match_id:
                continue
            try:
                odds_map = _fetch_odds(client, match_id)
                if not odds_map:
                    skipped_no_odds += 1
                    reset_refetch_state.update(
                        {
                            "processed": idx,
                            "total_matches_scanned": total_scanned,
                            "success": success,
                            "failed": failed,
                            "skipped_no_odds": skipped_no_odds,
                        }
                    )
                    continue
                await _run_match_analysis(match_id, confidence_threshold=51.0, include_details=False, refresh_live=False)
                success += 1
            except Exception:
                failed += 1
                logger.exception("Reset-refetch analyze failed. match_id=%s", match_id)

            reset_refetch_state.update(
                {
                    "processed": idx,
                    "total_matches_scanned": total_scanned,
                    "success": success,
                    "failed": failed,
                    "skipped_no_odds": skipped_no_odds,
                }
            )

        reset_refetch_state.update(
            {
                "status": "completed",
                "running": False,
                "finished_at": datetime.now(scheduler.timezone).isoformat(),
                "processed": len(matches),
                "total_matches_scanned": total_scanned,
                "success": success,
                "failed": failed,
                "skipped_no_odds": skipped_no_odds,
                "last_error": None,
            }
        )
    except Exception as exc:
        logger.exception("Reset-refetch failed.")
        reset_refetch_state.update(
            {
                "status": "failed",
                "running": False,
                "finished_at": datetime.now(scheduler.timezone).isoformat(),
                "last_error": str(exc),
            }
        )


def _resolve_match_id(client: Client, match_id_or_api_id: str) -> Optional[str]:
    try:
        by_internal = (
            client.table("matches")
            .select("id")
            .eq("id", match_id_or_api_id)
            .limit(1)
            .execute()
        )
        if by_internal.data:
            return by_internal.data[0].get("id")
    except Exception:
        logger.exception("Internal match id lookup failed.")

    try:
        if match_id_or_api_id.isdigit():
            by_odds_api_event = (
                client.table("matches")
                .select("id")
                .eq("odds_api_event_id", int(match_id_or_api_id))
                .limit(1)
                .execute()
            )
            if by_odds_api_event.data:
                return by_odds_api_event.data[0].get("id")
    except Exception:
        logger.exception("Odds API event id lookup failed.")

    try:
        if match_id_or_api_id.isdigit():
            by_api = (
                client.table("matches")
                .select("id")
                .eq("api_match_id", int(match_id_or_api_id))
                .limit(1)
                .execute()
            )
            if by_api.data:
                return by_api.data[0].get("id")
    except Exception:
        logger.exception("API match id lookup failed.")
    return None


def _fetch_match_base(client: Client, match_id: str) -> Dict[str, Any]:
    full_select = (
        "id,api_match_id,odds_api_event_id,home_team_id,away_team_id,league,match_date,status,season,ht_home,ht_away,ft_home,ft_away"
    )
    fallback_select = "id,api_match_id,home_team_id,away_team_id,league,match_date,status,season,ht_home,ht_away,ft_home,ft_away"
    try:
        try:
            result = client.table("matches").select(full_select).eq("id", match_id).single().execute()
        except Exception:
            result = client.table("matches").select(fallback_select).eq("id", match_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Match not found.")
        return result.data
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Match read failed.")
        raise HTTPException(status_code=500, detail="Failed to read match.") from exc


def _fetch_team_rows(client: Client, home_team_id: str, away_team_id: str) -> Dict[str, Dict[str, Any]]:
    full_select = "id,name,market_value,api_team_id,pi_rating,country,sofascore_id,logo_url"
    fallback_select = "id,name,market_value,api_team_id,pi_rating,country,sofascore_id"
    fallback_select_legacy = "id,name,market_value,api_team_id,country"
    try:
        try:
            result = client.table("teams").select(full_select).in_("id", [home_team_id, away_team_id]).execute()
        except Exception:
            try:
                result = client.table("teams").select(fallback_select).in_("id", [home_team_id, away_team_id]).execute()
            except Exception:
                result = client.table("teams").select(fallback_select_legacy).in_("id", [home_team_id, away_team_id]).execute()
        return {row["id"]: row for row in (result.data or []) if row.get("id")}
    except Exception:
        logger.exception("Team rows read failed.")
        return {}


def _fetch_cached_sofascore_bundle(
    client: Client,
    *,
    home_team_id: str,
    away_team_id: str,
) -> Dict[str, Any]:
    bundle: Dict[str, Any] = {
        "tournament_id": 0,
        "season_id": 0,
        "season_team_stats": {"home": {}, "away": {}},
        "top_players": {"home": [], "away": []},
        "standings": [],
    }
    team_ids = [home_team_id, away_team_id]

    season_rows: List[Dict[str, Any]] = []
    try:
        season_result = (
            client.table("team_season_stats_cache")
            .select("*")
            .in_("team_id", team_ids)
            .order("updated_at", desc=True)
            .limit(100)
            .execute()
        )
        season_rows = season_result.data or []
    except Exception:
        season_rows = []

    home_candidates = [row for row in season_rows if str(row.get("team_id") or "") == home_team_id]
    away_candidates = [row for row in season_rows if str(row.get("team_id") or "") == away_team_id]
    home_row = home_candidates[0] if home_candidates else {}
    away_row = away_candidates[0] if away_candidates else {}

    tournament_id = int(home_row.get("tournament_id", 0) or away_row.get("tournament_id", 0) or 0)
    season_id = int(home_row.get("season_id", 0) or away_row.get("season_id", 0) or 0)

    if tournament_id > 0 and season_id > 0:
        for candidates, side in [(home_candidates, "home"), (away_candidates, "away")]:
            preferred = next(
                (
                    row
                    for row in candidates
                    if int(row.get("tournament_id", 0) or 0) == tournament_id
                    and int(row.get("season_id", 0) or 0) == season_id
                ),
                None,
            )
            if isinstance(preferred, dict):
                bundle["season_team_stats"][side] = preferred
    else:
        if isinstance(home_row, dict) and home_row:
            bundle["season_team_stats"]["home"] = home_row
        if isinstance(away_row, dict) and away_row:
            bundle["season_team_stats"]["away"] = away_row

    bundle["tournament_id"] = tournament_id
    bundle["season_id"] = season_id

    top_players_rows: List[Dict[str, Any]] = []
    try:
        players_query = (
            client.table("team_top_players_cache")
            .select("*")
            .in_("team_id", team_ids)
            .order("updated_at", desc=True)
            .limit(200)
        )
        top_players_rows = players_query.execute().data or []
    except Exception:
        top_players_rows = []

    def _select_players(team_id: str) -> List[Dict[str, Any]]:
        candidates = [row for row in top_players_rows if str(row.get("team_id") or "") == team_id]
        if tournament_id > 0 and season_id > 0:
            scoped = [
                row
                for row in candidates
                if int(row.get("tournament_id", 0) or 0) == tournament_id
                and int(row.get("season_id", 0) or 0) == season_id
            ]
            if scoped:
                candidates = scoped
        candidates.sort(
            key=lambda row: (
                float(row.get("rating", 0) or 0),
                int(row.get("minutes_played", 0) or 0),
            ),
            reverse=True,
        )
        return candidates[:5]

    bundle["top_players"]["home"] = _select_players(home_team_id)
    bundle["top_players"]["away"] = _select_players(away_team_id)

    if tournament_id > 0 and season_id > 0:
        try:
            standings_rows = (
                client.table("league_standings_cache")
                .select("*")
                .eq("tournament_id", tournament_id)
                .eq("season_id", season_id)
                .order("position")
                .limit(40)
                .execute()
                .data
                or []
            )
            bundle["standings"] = standings_rows
        except Exception:
            bundle["standings"] = []

    return bundle


def _fetch_team_stats(client: Client, team_ids: List[str]) -> List[Dict[str, Any]]:
    if not team_ids:
        return []
    try:
        result = (
            client.table("team_stats")
            .select("*")
            .in_("team_id", team_ids)
            .order("updated_at", desc=True)
            .limit(200)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("team_stats read failed.")
        return []


def _fetch_match_injuries(
    client: Client,
    match_id: str,
    home_team_id: str,
    away_team_id: str,
) -> Dict[str, List[Dict[str, Any]]]:
    try:
        result = (
            client.table("match_injuries")
            .select("team_id,player_name,position,status,reason,expected_return,created_at")
            .eq("match_id", match_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        return {"home": [], "away": []}

    home_rows: List[Dict[str, Any]] = []
    away_rows: List[Dict[str, Any]] = []
    for row in result.data or []:
        entry = {
            "player_name": str(row.get("player_name") or ""),
            "position": str(row.get("position") or ""),
            "status": str(row.get("status") or "injured"),
            "reason": str(row.get("reason") or ""),
            "expected_return": str(row.get("expected_return") or ""),
        }
        team_id = str(row.get("team_id") or "")
        if team_id == home_team_id:
            home_rows.append(entry)
        elif team_id == away_team_id:
            away_rows.append(entry)
    return {"home": home_rows, "away": away_rows}


def _fetch_h2h_rows(client: Client, home_team_id: str, away_team_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    max_rows = max(1, limit)
    try:
        direct = (
            client.table("h2h")
            .select("match_date,home_goals,away_goals,league,is_cup")
            .eq("home_team_id", home_team_id)
            .eq("away_team_id", away_team_id)
            .order("match_date", desc=True)
            .limit(max_rows)
            .execute()
        )
        reverse = (
            client.table("h2h")
            .select("match_date,home_goals,away_goals,league,is_cup")
            .eq("home_team_id", away_team_id)
            .eq("away_team_id", home_team_id)
            .order("match_date", desc=True)
            .limit(max_rows)
            .execute()
        )
    except Exception:
        return []

    normalized: List[Dict[str, Any]] = []
    for row in direct.data or []:
        normalized.append(
            {
                "match_date": row.get("match_date"),
                "home_goals": int(row.get("home_goals", 0) or 0),
                "away_goals": int(row.get("away_goals", 0) or 0),
                "league": row.get("league"),
                "is_cup": bool(row.get("is_cup", False)),
            }
        )
    for row in reverse.data or []:
        normalized.append(
            {
                "match_date": row.get("match_date"),
                "home_goals": int(row.get("away_goals", 0) or 0),
                "away_goals": int(row.get("home_goals", 0) or 0),
                "league": row.get("league"),
                "is_cup": bool(row.get("is_cup", False)),
            }
        )
    normalized.sort(key=lambda item: str(item.get("match_date") or ""), reverse=True)
    return normalized[:max_rows]


def _team_xg_rolling_10(client: Client, team_id: str) -> float:
    try:
        result = (
            client.table("team_stats")
            .select("xg_for,updated_at")
            .eq("team_id", team_id)
            .order("updated_at", desc=True)
            .limit(10)
            .execute()
        )
    except Exception:
        return 0.0
    rows = result.data or []
    if not rows:
        return 0.0
    values: List[float] = []
    for row in rows:
        try:
            values.append(float(row.get("xg_for", 0) or 0))
        except (TypeError, ValueError):
            continue
    return round(sum(values) / len(values), 3) if values else 0.0


def _estimate_pi_rating_delta(client: Client, home_team_id: str, away_team_id: str) -> float:
    try:
        result = (
            client.table("matches")
            .select("home_team_id,away_team_id,ft_home,ft_away,status,match_date")
            .eq("status", "finished")
            .not_.is_("ft_home", "null")
            .not_.is_("ft_away", "null")
            .order("match_date")
            .limit(5000)
            .execute()
        )
    except Exception:
        return 0.0
    ratings = calculate_pi_ratings(result.data or [])
    home_rating = float(ratings.get(home_team_id, 1500.0))
    away_rating = float(ratings.get(away_team_id, 1500.0))
    return round(home_rating - away_rating, 2)


def _team_form_sequence(rows: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    sequence: List[Dict[str, Any]] = []
    for row in rows[:limit]:
        goals_scored = int(row.get("goals_scored", 0) or 0)
        goals_conceded = int(row.get("goals_conceded", 0) or 0)
        if goals_scored > goals_conceded:
            result = "W"
        elif goals_scored == goals_conceded:
            result = "D"
        else:
            result = "L"
        sequence.append(
            {
                "result": result,
                "goals_scored": goals_scored,
                "goals_conceded": goals_conceded,
                "updated_at": row.get("updated_at"),
            }
        )
    return sequence


def _form_score_from_results(results: List[str]) -> float:
    if not results:
        return 0.0
    points = 0
    for item in results[:6]:
        flag = str(item).upper()
        if flag == "W":
            points += 3
        elif flag == "D":
            points += 1
    return round(points / 18.0, 3)


def _build_form_payload(
    *,
    recent_matches: List[Dict[str, Any]],
    fallback_stats: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if recent_matches:
        last6 = [str(item.get("result") or "D").upper() for item in recent_matches[:6]]
        matches = [
            {
                "date": item.get("date"),
                "home_team_name": item.get("home_team_name"),
                "away_team_name": item.get("away_team_name"),
                "home_goals": int(item.get("home_goals", 0) or 0),
                "away_goals": int(item.get("away_goals", 0) or 0),
                "result": str(item.get("result") or "D").upper(),
                "is_home": bool(item.get("is_home", False)),
            }
            for item in recent_matches[:6]
        ]
        legacy = [
            {
                "result": str(item.get("result") or "D").upper(),
                "goals_scored": (
                    int(item.get("home_goals", 0) or 0)
                    if bool(item.get("is_home", False))
                    else int(item.get("away_goals", 0) or 0)
                ),
                "goals_conceded": (
                    int(item.get("away_goals", 0) or 0)
                    if bool(item.get("is_home", False))
                    else int(item.get("home_goals", 0) or 0)
                ),
                "updated_at": item.get("date"),
            }
            for item in recent_matches[:6]
        ]
        return {
            "last6": last6,
            "score": _form_score_from_results(last6),
            "matches": matches,
            "legacy": legacy,
        }

    legacy = _team_form_sequence(fallback_stats, limit=6)
    last6 = [str(item.get("result") or "D").upper() for item in legacy]
    return {
        "last6": last6,
        "score": _form_score_from_results(last6),
        "matches": [],
        "legacy": legacy,
    }


def _avg_stat(rows: List[Dict[str, Any]], key: str, limit: int = 10) -> float:
    values: List[float] = []
    for row in rows[: max(1, limit)]:
        try:
            values.append(float(row.get(key, 0) or 0))
        except (TypeError, ValueError):
            continue
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _fetch_ht_ratios(
    client: Client,
    home_team_id: str,
    away_team_id: str,
    season: Optional[str],
) -> Dict[str, float]:
    default = {"home": 0.42, "away": 0.40}
    try:
        query = client.table("ht_stats").select("team_id,ht_goals_ratio,season").in_("team_id", [home_team_id, away_team_id])
        if season:
            query = query.eq("season", str(season))
        result = query.execute()
    except Exception:
        return default

    rows = result.data or []
    by_team = {str(row.get("team_id")): row for row in rows if row.get("team_id")}
    home_ratio = float(by_team.get(home_team_id, {}).get("ht_goals_ratio", default["home"]) or default["home"])
    away_ratio = float(by_team.get(away_team_id, {}).get("ht_goals_ratio", default["away"]) or default["away"])
    return {
        "home": max(0.25, min(0.6, home_ratio)),
        "away": max(0.25, min(0.6, away_ratio)),
    }


def _flatten_injuries(
    injuries_by_side: Dict[str, List[Dict[str, Any]]],
    *,
    home_team_id: str,
    away_team_id: str,
    home_team_name: str,
    away_team_name: str,
) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []
    for side, team_id, team_name in [
        ("home", home_team_id, home_team_name),
        ("away", away_team_id, away_team_name),
    ]:
        for row in injuries_by_side.get(side, []) or []:
            flat.append(
                {
                    "team_id": team_id,
                    "team_name": team_name,
                    "team_side": side,
                    "player": row.get("player_name") or row.get("player"),
                    "player_name": row.get("player_name") or row.get("player"),
                    "position": row.get("position"),
                    "status": row.get("status") or row.get("type") or "injured",
                    "type": row.get("status") or row.get("type") or "injured",
                    "reason": row.get("reason"),
                    "expected_return": row.get("expected_return"),
                }
            )
    return flat


def _safe_iso_date(value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    return raw[:10]


def _parse_correct_filter(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "dogru", "doğru"}:
        return True
    if normalized in {"0", "false", "no", "yanlis", "yanlış"}:
        return False
    return None


def _count_odds_rows(client: Client, match_id: Optional[str]) -> int:
    if not match_id:
        return 0
    bookmaker = getattr(odds_scraper, "bookmaker_key", "betfair_exchange")
    try:
        result = (
            client.table("odds_history")
            .select("id", count="exact")
            .eq("match_id", match_id)
            .eq("bookmaker", bookmaker)
            .execute()
        )
        return int(result.count or 0)
    except Exception:
        return 0


def _normalize_market_key(market_type: str) -> Optional[str]:
    direct = str(market_type or "").strip().upper()
    if direct in SUPPORTED_MARKETS:
        return direct
    normalized = market_type.lower()
    if "match winner:home" in normalized or "1x2:home" in normalized:
        return "MS1"
    if "match winner:draw" in normalized or "1x2:draw" in normalized:
        return "MSX"
    if "match winner:away" in normalized or "1x2:away" in normalized:
        return "MS2"
    if "both teams to score:yes" in normalized:
        return "KG_VAR"
    if "both teams to score:no" in normalized:
        return "KG_YOK"
    if "over/under:over 0.5" in normalized:
        return "MS_O0.5"
    if "over/under:under 0.5" in normalized:
        return "MS_U0.5"
    if "over/under:over 1.5" in normalized:
        return "MS_O1.5"
    if "over/under:under 1.5" in normalized:
        return "MS_U1.5"
    if "over/under:over 2.5" in normalized:
        return "MS_O2.5"
    if "over/under:under 2.5" in normalized:
        return "MS_U2.5"
    if "over/under:over 3.5" in normalized:
        return "MS_O3.5"
    if "over/under:under 3.5" in normalized:
        return "MS_U3.5"
    return None


def _normalize_team_name_for_matching(team_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(team_name or ""))
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9 ]+", " ", ascii_only)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _parse_threshold_from_market(market_type: str, token: str) -> Optional[float]:
    prefix = f"{token}"
    if not market_type.startswith(prefix):
        return None
    raw = market_type[len(prefix) :]
    try:
        return float(raw)
    except ValueError:
        return None


def _evaluate_prediction_hit(
    market_type: str,
    *,
    home_score: int,
    away_score: int,
    ht_home: Optional[int] = None,
    ht_away: Optional[int] = None,
) -> Optional[bool]:
    market = str(market_type or "").strip().upper()
    if not market:
        return None

    total_goals = home_score + away_score
    goal_diff = home_score - away_score

    if market in {"MS1", "HCP_-0.5"}:
        return home_score > away_score
    if market == "MSX":
        return home_score == away_score
    if market == "MS2":
        return away_score > home_score
    if market in {"HCP_+0.5", "HCP_+1X"}:
        return away_score >= home_score
    if market == "KG_VAR":
        return home_score > 0 and away_score > 0
    if market == "KG_YOK":
        return not (home_score > 0 and away_score > 0)

    if market.startswith("MS_O"):
        threshold = _parse_threshold_from_market(market, "MS_O")
        if threshold is None:
            return None
        return float(total_goals) > threshold
    if market.startswith("MS_U"):
        threshold = _parse_threshold_from_market(market, "MS_U")
        if threshold is None:
            return None
        return float(total_goals) < threshold

    if market == "IY1":
        if ht_home is None or ht_away is None:
            return None
        return ht_home > ht_away
    if market == "IYX":
        if ht_home is None or ht_away is None:
            return None
        return ht_home == ht_away
    if market == "IY2":
        if ht_home is None or ht_away is None:
            return None
        return ht_home < ht_away

    if market.startswith("IY_O"):
        if ht_home is None or ht_away is None:
            return None
        threshold = _parse_threshold_from_market(market, "IY_O")
        if threshold is None:
            return None
        return float(ht_home + ht_away) > threshold
    if market.startswith("IY_U"):
        if ht_home is None or ht_away is None:
            return None
        threshold = _parse_threshold_from_market(market, "IY_U")
        if threshold is None:
            return None
        return float(ht_home + ht_away) < threshold

    if market.startswith("HCP_+"):
        threshold = _parse_threshold_from_market(market, "HCP_+")
        if threshold is None:
            return None
        return float(goal_diff) <= threshold
    if market.startswith("HCP_-"):
        threshold = _parse_threshold_from_market(market, "HCP_-")
        if threshold is None:
            return None
        return float(goal_diff) > threshold

    return None


def _find_match_by_team_and_date(client: Client, historical_match: Dict[str, Any]) -> Optional[str]:
    date_str = str(historical_match.get("date") or "")
    home_name = _normalize_team_name_for_matching(str(historical_match.get("home_team") or ""))
    away_name = _normalize_team_name_for_matching(str(historical_match.get("away_team") or ""))
    if not date_str or not home_name or not away_name:
        return None

    try:
        start_iso = f"{date_str}T00:00:00+00:00"
        end_iso = f"{date_str}T23:59:59+00:00"
        matches = (
            client.table("matches")
            .select("id,home_team_id,away_team_id,match_date")
            .gte("match_date", start_iso)
            .lte("match_date", end_iso)
            .limit(500)
            .execute()
            .data
            or []
        )
    except Exception:
        return None

    team_ids = sorted(
        {
            str(row.get("home_team_id") or "")
            for row in matches
            if row.get("home_team_id")
        }
        | {
            str(row.get("away_team_id") or "")
            for row in matches
            if row.get("away_team_id")
        }
    )
    if not team_ids:
        return None

    try:
        teams = client.table("teams").select("id,name").in_("id", team_ids).execute().data or []
    except Exception:
        return None
    name_map = {str(row.get("id")): _normalize_team_name_for_matching(str(row.get("name") or "")) for row in teams}

    for row in matches:
        row_home = name_map.get(str(row.get("home_team_id") or ""), "")
        row_away = name_map.get(str(row.get("away_team_id") or ""), "")
        if row_home == home_name and row_away == away_name:
            return str(row.get("id") or "")
    return None


def _fetch_latest_prediction_for_match(client: Client, match_id: str) -> Optional[Dict[str, Any]]:
    try:
        rows = (
            client.table("predictions")
            .select("id,match_id,market_type,predicted_outcome,confidence_score,ev_percentage,recommended,created_at,kelly_pct")
            .eq("match_id", match_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
            .data
            or []
        )
    except Exception:
        return None
    if not rows:
        return None
    for row in rows:
        market_type = str(row.get("market_type") or "").strip().upper()
        if market_type and market_type not in SUPPORTED_MARKET_SET:
            continue
        if bool(row.get("recommended")):
            return row
    for row in rows:
        market_type = str(row.get("market_type") or "").strip().upper()
        if market_type and market_type in SUPPORTED_MARKET_SET:
            return row
    return None


def _fetch_market_probability(client: Client, match_id: str, market_type: str) -> Optional[float]:
    try:
        rows = (
            client.table("market_probabilities")
            .select("probability")
            .eq("match_id", match_id)
            .eq("market", market_type)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception:
        return None
    if not rows:
        return None
    try:
        return float(rows[0].get("probability"))
    except (TypeError, ValueError):
        return None


def _fetch_market_odd(client: Client, match_id: str, market_type: str) -> Optional[float]:
    try:
        rows = (
            client.table("odds")
            .select("odd,recorded_at")
            .eq("match_id", match_id)
            .eq("market", market_type)
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if rows:
            value = float(rows[0].get("odd"))
            if value > 0:
                return round(value, 4)
    except Exception:
        pass

    try:
        rows = (
            client.table("odds_history")
            .select("current_odd,closing_odd,opening_odd,recorded_at")
            .eq("match_id", match_id)
            .eq("market_type", market_type)
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception:
        return None
    if not rows:
        return None
    odd = rows[0].get("current_odd") or rows[0].get("closing_odd") or rows[0].get("opening_odd")
    try:
        value = float(odd)
    except (TypeError, ValueError):
        return None
    return round(value, 4) if value > 0 else None


def _compute_backtest_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    evaluated_rows = [row for row in rows if row.get("hit") is not None]
    total = len(rows)
    evaluated = len(evaluated_rows)
    hits = len([row for row in evaluated_rows if row.get("hit") is True])
    misses = len([row for row in evaluated_rows if row.get("hit") is False])
    unresolved = total - evaluated

    total_pnl = round(
        sum(float(row.get("profit_units", 0.0) or 0.0) for row in evaluated_rows),
        4,
    )
    roi_pct = round((total_pnl / evaluated) * 100.0, 2) if evaluated > 0 else 0.0
    hit_rate_pct = round((hits / evaluated) * 100.0, 2) if evaluated > 0 else 0.0

    ev_values = [float(row.get("our_ev", 0.0) or 0.0) for row in rows]
    avg_ev = round(sum(ev_values) / len(ev_values), 4) if ev_values else 0.0

    by_market: Dict[str, Dict[str, Any]] = {}
    for row in evaluated_rows:
        market = str(row.get("our_market") or "UNKNOWN")
        bucket = by_market.setdefault(
            market,
            {"market": market, "count": 0, "hits": 0, "misses": 0, "hit_rate_pct": 0.0},
        )
        bucket["count"] += 1
        if row.get("hit") is True:
            bucket["hits"] += 1
        else:
            bucket["misses"] += 1

    for market in by_market.values():
        if market["count"] > 0:
            market["hit_rate_pct"] = round((market["hits"] / market["count"]) * 100.0, 2)

    return {
        "total_predictions": total,
        "evaluated_predictions": evaluated,
        "hits": hits,
        "misses": misses,
        "unresolved": unresolved,
        "hit_rate_pct": hit_rate_pct,
        "avg_ev": avg_ev,
        "total_pnl_units": total_pnl,
        "roi_pct": roi_pct,
        "by_market": sorted(by_market.values(), key=lambda item: item["count"], reverse=True),
    }


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_backtest_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _resolve_backtest_window(
    *,
    start_date: Optional[str],
    end_date: Optional[str],
    days_back: int,
) -> Tuple[date, date]:
    today = datetime.now(scheduler.timezone).date()
    end_value = _parse_backtest_date(end_date) or today
    start_value = _parse_backtest_date(start_date)
    if start_value is None:
        span = max(1, int(days_back))
        start_value = end_value - timedelta(days=span - 1)
    if start_value > end_value:
        start_value, end_value = end_value, start_value
    return start_value, end_value


def _fetch_finished_matches_for_backtest(
    client: Client,
    *,
    start_date: date,
    end_date: date,
    league_filter: Optional[str],
    max_matches: int,
) -> List[Dict[str, Any]]:
    start_iso = f"{start_date.isoformat()}T00:00:00+00:00"
    end_iso = f"{end_date.isoformat()}T23:59:59+00:00"
    query = (
        client.table("matches")
        .select("id,home_team_id,away_team_id,league,match_date,status,ft_home,ft_away,ht_home,ht_away")
        .gte("match_date", start_iso)
        .lte("match_date", end_iso)
        .eq("status", "finished")
        .not_.is_("ft_home", "null")
        .not_.is_("ft_away", "null")
        .order("match_date")
        .limit(max(1, int(max_matches)))
    )
    if league_filter:
        query = query.ilike("league", f"%{league_filter.strip()}%")
    return query.execute().data or []


def _fetch_team_stats_before(
    client: Client,
    *,
    team_ids: List[str],
    before_iso: str,
    per_team_limit: int = 80,
) -> Dict[str, List[Dict[str, Any]]]:
    if not team_ids:
        return {}
    fetch_limit = max(60, int(per_team_limit) * max(1, len(team_ids)))
    try:
        rows = (
            client.table("team_stats")
            .select("*")
            .in_("team_id", team_ids)
            .lte("updated_at", before_iso)
            .order("updated_at", desc=True)
            .limit(fetch_limit)
            .execute()
            .data
            or []
        )
    except Exception:
        logger.exception("team_stats pre-match read failed.")
        return {team_id: [] for team_id in team_ids}

    grouped: Dict[str, List[Dict[str, Any]]] = {team_id: [] for team_id in team_ids}
    for row in rows:
        team_id = str(row.get("team_id") or "")
        if team_id not in grouped:
            continue
        bucket = grouped[team_id]
        if len(bucket) >= per_team_limit:
            continue
        bucket.append(row)
    return grouped


def _fetch_h2h_rows_before(
    client: Client,
    *,
    home_team_id: str,
    away_team_id: str,
    before_iso: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    max_rows = max(1, int(limit))
    try:
        direct = (
            client.table("h2h")
            .select("match_date,home_goals,away_goals,league,is_cup")
            .eq("home_team_id", home_team_id)
            .eq("away_team_id", away_team_id)
            .lt("match_date", before_iso)
            .order("match_date", desc=True)
            .limit(max_rows)
            .execute()
        )
        reverse = (
            client.table("h2h")
            .select("match_date,home_goals,away_goals,league,is_cup")
            .eq("home_team_id", away_team_id)
            .eq("away_team_id", home_team_id)
            .lt("match_date", before_iso)
            .order("match_date", desc=True)
            .limit(max_rows)
            .execute()
        )
    except Exception:
        logger.exception("h2h pre-match read failed.")
        return []

    normalized: List[Dict[str, Any]] = []
    for row in direct.data or []:
        normalized.append(
            {
                "match_date": row.get("match_date"),
                "home_goals": int(row.get("home_goals", 0) or 0),
                "away_goals": int(row.get("away_goals", 0) or 0),
                "league": row.get("league"),
                "is_cup": bool(row.get("is_cup", False)),
            }
        )
    for row in reverse.data or []:
        normalized.append(
            {
                "match_date": row.get("match_date"),
                "home_goals": int(row.get("away_goals", 0) or 0),
                "away_goals": int(row.get("home_goals", 0) or 0),
                "league": row.get("league"),
                "is_cup": bool(row.get("is_cup", False)),
            }
        )

    normalized.sort(key=lambda item: str(item.get("match_date") or ""), reverse=True)
    return normalized[:max_rows]


def _fetch_odds_before(client: Client, match_id: str, before_iso: str) -> Dict[str, float]:
    bookmaker = getattr(odds_scraper, "bookmaker_key", "betfair_exchange")
    mapped: Dict[str, float] = {}

    try:
        rows = (
            client.table("odds_history")
            .select("market_type,current_odd,closing_odd,opening_odd,recorded_at")
            .eq("match_id", match_id)
            .eq("bookmaker", bookmaker)
            .lte("recorded_at", before_iso)
            .order("recorded_at", desc=True)
            .limit(1000)
            .execute()
            .data
            or []
        )
        for row in rows:
            key = _normalize_market_key(str(row.get("market_type") or ""))
            if not key or key in mapped:
                continue
            odd = row.get("current_odd") or row.get("closing_odd") or row.get("opening_odd")
            try:
                odd_value = float(odd)
            except (TypeError, ValueError):
                continue
            if odd_value > 0:
                mapped[key] = odd_value
    except Exception:
        logger.exception("odds_history pre-match read failed.")

    if mapped:
        return mapped

    try:
        rows = (
            client.table("odds")
            .select("market,odd,recorded_at")
            .eq("match_id", match_id)
            .lte("recorded_at", before_iso)
            .order("recorded_at", desc=True)
            .limit(1000)
            .execute()
            .data
            or []
        )
        for row in rows:
            key = _normalize_market_key(str(row.get("market") or ""))
            if not key or key in mapped:
                continue
            try:
                odd_value = float(row.get("odd"))
            except (TypeError, ValueError):
                continue
            if odd_value > 0:
                mapped[key] = odd_value
    except Exception:
        logger.exception("odds table pre-match read failed.")
    if mapped:
        return mapped

    # Son fallback: zaman filtresi olmadan en güncel odds snapshot'unu kullan.
    # Bazı maçlarda kickoff öncesi snapshot yoksa backtest tamamen boş kalmasın.
    try:
        latest = _fetch_odds(client, match_id)
        if latest:
            return latest
    except Exception:
        logger.exception("odds latest fallback read failed.")
    return mapped


def _fetch_bookmaker_odds_entries_before(client: Client, match_id: str, before_iso: str) -> List[Dict[str, Any]]:
    bookmaker = getattr(odds_scraper, "bookmaker_key", "betfair_exchange")
    grouped: Dict[str, Dict[str, Any]] = {}
    try:
        rows = (
            client.table("odds_history")
            .select("bookmaker,market_type,current_odd,closing_odd,opening_odd,recorded_at")
            .eq("match_id", match_id)
            .eq("bookmaker", bookmaker)
            .lte("recorded_at", before_iso)
            .order("recorded_at", desc=True)
            .limit(2000)
            .execute()
            .data
            or []
        )
    except Exception:
        rows = []

    for row in rows:
        book_name = str(row.get("bookmaker") or "unknown").strip().lower() or "unknown"
        market = _normalize_market_key(str(row.get("market_type") or ""))
        if not market:
            continue
        odd_raw = row.get("current_odd") or row.get("closing_odd") or row.get("opening_odd")
        try:
            odd = float(odd_raw)
        except (TypeError, ValueError):
            continue
        if odd <= 1.0:
            continue
        grouped.setdefault(book_name, {"book": book_name})
        if market not in grouped[book_name]:
            grouped[book_name][market] = round(odd, 4)

    if grouped:
        return list(grouped.values())

    try:
        latest_grouped = _fetch_bookmaker_odds_entries(client, match_id)
        if latest_grouped:
            return latest_grouped
    except Exception:
        logger.exception("bookmaker odds latest fallback read failed.")

    fallback = _fetch_odds_before(client, match_id, before_iso)
    if not fallback:
        return []
    return [{"book": "internal", **{k: float(v) for k, v in fallback.items() if float(v) > 1.0}}]


def _build_backtest_row(
    *,
    client: Client,
    match_row: Dict[str, Any],
    min_confidence: float,
    include_non_recommended: bool,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    match_id = str(match_row.get("id") or "")
    if not match_id:
        return None, "invalid_match_id"

    kickoff_dt = _parse_iso_datetime(match_row.get("match_date"))
    if kickoff_dt is None:
        return None, "invalid_match_date"
    kickoff_iso = kickoff_dt.astimezone(timezone.utc).isoformat()

    home_team_id = str(match_row.get("home_team_id") or "")
    away_team_id = str(match_row.get("away_team_id") or "")
    team_rows = _fetch_team_rows(client, home_team_id, away_team_id)
    home_team = team_rows.get(home_team_id, {}) if isinstance(team_rows, dict) else {}
    away_team = team_rows.get(away_team_id, {}) if isinstance(team_rows, dict) else {}

    stats_grouped = _fetch_team_stats_before(
        client,
        team_ids=[home_team_id, away_team_id],
        before_iso=kickoff_iso,
        per_team_limit=60,
    )
    home_stats = list(stats_grouped.get(home_team_id, []) or [])
    away_stats = list(stats_grouped.get(away_team_id, []) or [])

    home_form_payload = _build_form_payload(recent_matches=[], fallback_stats=home_stats)
    away_form_payload = _build_form_payload(recent_matches=[], fallback_stats=away_stats)
    h2h_rows = _fetch_h2h_rows_before(
        client,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        before_iso=kickoff_iso,
        limit=10,
    )
    bookmaker_odds = _fetch_bookmaker_odds_entries_before(client, match_id, kickoff_iso)
    opening_odds = _fetch_odds_before(client, match_id, kickoff_iso)

    if not bookmaker_odds:
        return None, "no_odds"

    engine_match_data = _build_engine_match_data(
        match_id=match_id,
        league=str(match_row.get("league", "") or "default"),
        home_stats=home_stats,
        away_stats=away_stats,
        home_form_payload=home_form_payload,
        away_form_payload=away_form_payload,
        h2h_rows=h2h_rows,
    )

    engine_result = run_prediction_engine(
        match_data=engine_match_data,
        home_stats=engine_match_data.get("home_team_stats", {}),
        away_stats=engine_match_data.get("away_team_stats", {}),
        h2h=engine_match_data.get("h2h", {}),
        bookmakers=bookmaker_odds,
        opening_odds=opening_odds,
    )
    ev_result = _build_ev_result_from_engine(engine_result=engine_result, confidence_threshold=min_confidence)
    best_market = ev_result.get("best_market")
    if not isinstance(best_market, dict):
        return None, "no_market"

    recommended = bool(best_market.get("recommended", False))
    if not include_non_recommended and not recommended:
        return None, "not_recommended"

    market_type = str(best_market.get("market_type") or best_market.get("market") or "").strip()
    if not market_type:
        return None, "no_market"

    try:
        odd = float(best_market.get("odd", 0.0) or 0.0)
    except (TypeError, ValueError):
        odd = 0.0
    try:
        probability = float(best_market.get("probability", 0.0) or 0.0)
    except (TypeError, ValueError):
        probability = 0.0
    try:
        ev_value = float(best_market.get("ev", 0.0) or 0.0)
    except (TypeError, ValueError):
        ev_value = 0.0

    ft_home = int(match_row.get("ft_home", 0) or 0)
    ft_away = int(match_row.get("ft_away", 0) or 0)
    ht_home_raw = match_row.get("ht_home")
    ht_away_raw = match_row.get("ht_away")
    ht_home = int(ht_home_raw) if ht_home_raw is not None else None
    ht_away = int(ht_away_raw) if ht_away_raw is not None else None
    hit = _evaluate_prediction_hit(
        market_type,
        home_score=ft_home,
        away_score=ft_away,
        ht_home=ht_home,
        ht_away=ht_away,
    )
    if hit is True and odd > 1.0:
        profit_units = round(odd - 1.0, 4)
    elif hit is False:
        profit_units = -1.0
    else:
        profit_units = 0.0

    confidence = float(engine_result.get("confidence_score", 0.0) or 0.0)
    home_name = str(home_team.get("name") or "Ev Sahibi")
    away_name = str(away_team.get("name") or "Deplasman")

    return (
        {
            "match_id": match_id,
            "date": str(match_row.get("match_date") or ""),
            "league": str(match_row.get("league") or ""),
            "home_team": home_name,
            "away_team": away_name,
            "score": f"{ft_home}-{ft_away}",
            "our_market": market_type,
            "our_probability": round(probability, 4),
            "our_odd": round(odd, 4),
            "our_ev": round(ev_value, 4),
            "confidence_score": round(confidence, 2),
            "recommended": recommended,
            "reject_reason": best_market.get("reject_reason"),
            "kelly_pct": round(float(best_market.get("kelly_pct", 0.0) or 0.0), 2),
            "hit": hit,
            "profit_units": profit_units,
            "meta": engine_result.get("meta", {}),
        },
        None,
    )


async def _run_backtest_lab(request: BacktestRunRequest) -> None:
    start_date, end_date = _resolve_backtest_window(
        start_date=request.start_date,
        end_date=request.end_date,
        days_back=request.days_back,
    )

    backtest_state.update(
        {
            "status": "running",
            "running": True,
            "started_at": datetime.now(scheduler.timezone).isoformat(),
            "finished_at": None,
            "params": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days_back": int(request.days_back),
                "league": str(request.league or ""),
                "min_confidence": float(request.min_confidence),
                "include_non_recommended": bool(request.include_non_recommended),
                "max_matches": int(request.max_matches),
                "store_rows": int(request.store_rows),
            },
            "processed": 0,
            "total_matches_scanned": 0,
            "success": 0,
            "failed": 0,
            "skipped_no_odds": 0,
            "skipped_no_market": 0,
            "summary": None,
            "rows": [],
            "last_error": None,
        }
    )

    try:
        client = get_supabase_client()
        matches = _fetch_finished_matches_for_backtest(
            client,
            start_date=start_date,
            end_date=end_date,
            league_filter=request.league,
            max_matches=request.max_matches,
        )

        total = len(matches)
        success = 0
        failed = 0
        skipped_no_odds = 0
        skipped_no_market = 0
        all_rows: List[Dict[str, Any]] = []

        for index, match_row in enumerate(matches, start=1):
            try:
                row, skip_reason = _build_backtest_row(
                    client=client,
                    match_row=match_row,
                    min_confidence=float(request.min_confidence),
                    include_non_recommended=bool(request.include_non_recommended),
                )
                if row is not None:
                    all_rows.append(row)
                    success += 1
                elif skip_reason == "no_odds":
                    skipped_no_odds += 1
                else:
                    skipped_no_market += 1
            except Exception:
                failed += 1
                logger.exception("Backtest analyze failed. match_id=%s", match_row.get("id"))

            if index % 25 == 0:
                await asyncio.sleep(0)

            backtest_state.update(
                {
                    "processed": index,
                    "total_matches_scanned": total,
                    "success": success,
                    "failed": failed,
                    "skipped_no_odds": skipped_no_odds,
                    "skipped_no_market": skipped_no_market,
                }
            )

        summary = _compute_backtest_summary(all_rows)
        sorted_rows = sorted(all_rows, key=lambda item: str(item.get("date") or ""), reverse=True)
        store_limit = max(1, int(request.store_rows))

        backtest_state.update(
            {
                "status": "completed",
                "running": False,
                "finished_at": datetime.now(scheduler.timezone).isoformat(),
                "processed": total,
                "total_matches_scanned": total,
                "success": success,
                "failed": failed,
                "skipped_no_odds": skipped_no_odds,
                "skipped_no_market": skipped_no_market,
                "summary": summary,
                "rows": sorted_rows[:store_limit],
                "last_error": None,
            }
        )
    except Exception as exc:
        logger.exception("Backtest run failed.")
        backtest_state.update(
            {
                "status": "failed",
                "running": False,
                "finished_at": datetime.now(scheduler.timezone).isoformat(),
                "last_error": str(exc),
            }
        )


def _fetch_odds(client: Client, match_id: str) -> Dict[str, float]:
    bookmaker = getattr(odds_scraper, "bookmaker_key", "betfair_exchange")
    try:
        odds_result = (
            client.table("odds_history")
            .select("market_type,current_odd,closing_odd,opening_odd,recorded_at")
            .eq("match_id", match_id)
            .eq("bookmaker", bookmaker)
            .order("recorded_at", desc=True)
            .limit(1000)
            .execute()
        )
    except Exception:
        logger.exception("odds_history read failed.")
        return {}

    mapped: Dict[str, float] = {}
    for row in odds_result.data or []:
        market_type = str(row.get("market_type", ""))
        key = _normalize_market_key(market_type)
        if not key or key in mapped:
            continue
        odd = row.get("current_odd") or row.get("closing_odd") or row.get("opening_odd")
        try:
            mapped[key] = float(odd)
        except (TypeError, ValueError):
            continue
    if mapped:
        return mapped

    # Fallback: odds snapshot tablosundan oku (betfair-only filtrelenmez)
    try:
        odds_rows = (
            client.table("odds")
            .select("market,odd,recorded_at")
            .eq("match_id", match_id)
            .order("recorded_at", desc=True)
            .limit(1000)
            .execute()
            .data
            or []
        )
        for row in odds_rows:
            key = _normalize_market_key(str(row.get("market") or ""))
            if not key or key in mapped:
                continue
            try:
                odd_value = float(row.get("odd"))
            except (TypeError, ValueError):
                continue
            if odd_value > 0:
                mapped[key] = odd_value
    except Exception:
        logger.exception("odds table fallback read failed.")
    return mapped


def _fetch_bookmaker_odds_entries(client: Client, match_id: str) -> List[Dict[str, Any]]:
    bookmaker = getattr(odds_scraper, "bookmaker_key", "betfair_exchange")
    try:
        rows = (
            client.table("odds_history")
            .select("bookmaker,market_type,current_odd,closing_odd,opening_odd,recorded_at")
            .eq("match_id", match_id)
            .eq("bookmaker", bookmaker)
            .order("recorded_at", desc=True)
            .limit(2000)
            .execute()
            .data
            or []
        )
    except Exception:
        rows = []

    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        bookmaker = str(row.get("bookmaker") or "unknown").strip().lower() or "unknown"
        market = _normalize_market_key(str(row.get("market_type") or ""))
        if not market:
            continue
        odd_raw = row.get("current_odd") or row.get("closing_odd") or row.get("opening_odd")
        try:
            odd = float(odd_raw)
        except (TypeError, ValueError):
            continue
        if odd <= 1.0:
            continue
        grouped.setdefault(bookmaker, {"book": bookmaker})
        if market not in grouped[bookmaker]:
            grouped[bookmaker][market] = round(odd, 4)

    if grouped:
        return list(grouped.values())

    fallback = _fetch_odds(client, match_id)
    if not fallback:
        return []
    return [{"book": "internal", **{k: float(v) for k, v in fallback.items() if float(v) > 1.0}}]


def _build_engine_match_data(
    *,
    match_id: str,
    league: str,
    home_stats: List[Dict[str, Any]],
    away_stats: List[Dict[str, Any]],
    home_form_payload: Dict[str, Any],
    away_form_payload: Dict[str, Any],
    h2h_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    home_avg_goals_for = _avg_stat(home_stats, "goals_scored", limit=10) or 1.4
    away_avg_goals_for = _avg_stat(away_stats, "goals_scored", limit=10) or 1.1
    home_avg_goals_against = _avg_stat(home_stats, "goals_conceded", limit=10) or 1.2
    away_avg_goals_against = _avg_stat(away_stats, "goals_conceded", limit=10) or 1.3
    home_avg_xg_for = _avg_stat(home_stats, "xg_for", limit=10) or home_avg_goals_for
    away_avg_xg_for = _avg_stat(away_stats, "xg_for", limit=10) or away_avg_goals_for
    home_avg_xg_against = _avg_stat(home_stats, "xg_against", limit=10) or home_avg_goals_against
    away_avg_xg_against = _avg_stat(away_stats, "xg_against", limit=10) or away_avg_goals_against

    if h2h_rows:
        avg_h2h_home = round(sum(float(row.get("home_goals", 0) or 0) for row in h2h_rows[:10]) / min(len(h2h_rows[:10]), 10), 3)
        avg_h2h_away = round(sum(float(row.get("away_goals", 0) or 0) for row in h2h_rows[:10]) / min(len(h2h_rows[:10]), 10), 3)
    else:
        avg_h2h_home = home_avg_goals_for
        avg_h2h_away = away_avg_goals_for

    return {
        "match_id": match_id,
        "league": league,
        "home_team_stats": {
            "last6": home_form_payload.get("last6", []),
            "avg_xg_for": home_avg_xg_for,
            "avg_xg_against": home_avg_xg_against,
            "avg_goals_for": home_avg_goals_for,
            "avg_goals_against": home_avg_goals_against,
            "home_avg_goals_for": home_avg_goals_for,
            "home_avg_goals_against": home_avg_goals_against,
        },
        "away_team_stats": {
            "last6": away_form_payload.get("last6", []),
            "avg_xg_for": away_avg_xg_for,
            "avg_xg_against": away_avg_xg_against,
            "avg_goals_for": away_avg_goals_for,
            "avg_goals_against": away_avg_goals_against,
            "away_avg_goals_for": away_avg_goals_for,
            "away_avg_goals_against": away_avg_goals_against,
        },
        "h2h": {
            "avg_home_goals": avg_h2h_home,
            "avg_away_goals": avg_h2h_away,
            "matches": h2h_rows[:5],
        },
    }


def _convert_engine_markets(engine_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    converted: List[Dict[str, Any]] = []
    for row in engine_rows:
        market = str(row.get("market") or row.get("market_type") or "").strip()
        if not market:
            continue
        try:
            probability = float(row.get("probability", 0.0) or 0.0)
            odd = float(row.get("odd", 0.0) or 0.0)
            ev = float(row.get("ev", 0.0) or 0.0)
            kelly = float(row.get("kelly_pct", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        converted.append(
            {
                "market": market,
                "market_type": market,
                "predicted_outcome": market,
                "probability": round(probability, 6),
                "odd": round(odd, 4),
                "odd_source": "bookmaker",
                "ev": round(ev, 4),
                "ev_percentage": round(ev * 100.0, 2),
                "recommended": bool(row.get("recommended", False)),
                "suspicious_high_ev": bool(row.get("suspicious_high_ev", False)),
                "kelly_pct": round(kelly, 2),
                "kelly_note": (
                    f"Bankroll'unun %{round(kelly, 2)} kadarini oynayin"
                    if kelly > 0
                    else "Oynama"
                ),
                "reject_reason": row.get("reject_reason"),
            }
        )
    return sorted(converted, key=lambda item: item["ev"], reverse=True)


def _build_ev_result_from_engine(
    *,
    engine_result: Dict[str, Any],
    confidence_threshold: float,
) -> Dict[str, Any]:
    all_rows: List[Dict[str, Any]] = []
    if isinstance(engine_result.get("all_markets"), list):
        all_rows = engine_result.get("all_markets", []) or []
    elif isinstance(engine_result.get("ev"), dict):
        all_rows = (engine_result.get("ev", {}) or {}).get("all_markets", []) or []
    all_markets = _convert_engine_markets(all_rows)

    confidence_score = float(engine_result.get("confidence_score", 0.0) or 0.0)
    best_market: Optional[Dict[str, Any]] = None
    preferred = engine_result.get("recommended_market")
    if isinstance(preferred, dict) and preferred:
        preferred_market = str(preferred.get("market") or preferred.get("market_type") or "")
        best_market = next((row for row in all_markets if row.get("market_type") == preferred_market), None)
    if best_market is None and all_markets:
        best_market = all_markets[0]

    any_recommended = any(bool(item.get("recommended")) for item in all_markets)
    effective_recommended = any_recommended and (confidence_score >= float(confidence_threshold))

    if best_market is not None:
        best_market = {
            **best_market,
            "recommended": bool(best_market.get("recommended", False) and confidence_score >= float(confidence_threshold)),
            "confidence_gate_passed": bool(confidence_score >= float(confidence_threshold)),
        }

    return {
        "confidence_score": round(confidence_score, 2),
        "confidence_threshold": float(confidence_threshold),
        "recommended": bool(effective_recommended),
        "recommended_by_ev_only": bool(any_recommended),
        "best_market": best_market,
        "all_markets": all_markets,
    }


def _competition_type_and_stage(league_name: str) -> Tuple[str, str]:
    value = league_name.lower()
    stage = "regular"
    if "quarter" in value:
        stage = "quarter final"
    elif "semi" in value:
        stage = "semi final"
    elif "final" in value:
        stage = "final"
    elif "group" in value:
        stage = "group stage"

    if any(flag in value for flag in ["uefa", "cup", "world cup", "euro"]):
        return "cup", stage
    return "league", stage


def _h2h_points_ratio(h2h_rows: List[Dict[str, Any]], home_api_team_id: int) -> float:
    if not h2h_rows:
        return 0.5
    points = 0.0
    max_points = 0.0
    for row in h2h_rows:
        teams = row.get("teams", {}) if isinstance(row.get("teams"), dict) else {}
        goals = row.get("goals", {}) if isinstance(row.get("goals"), dict) else {}
        home_team = teams.get("home", {}) if isinstance(teams.get("home"), dict) else {}
        away_team = teams.get("away", {}) if isinstance(teams.get("away"), dict) else {}
        fixture_home_id = int(home_team.get("id", 0) or 0)
        fixture_away_id = int(away_team.get("id", 0) or 0)
        home_goals = int(goals.get("home", 0) or 0)
        away_goals = int(goals.get("away", 0) or 0)
        if fixture_home_id <= 0 or fixture_away_id <= 0:
            continue

        max_points += 3.0
        if fixture_home_id == home_api_team_id:
            if home_goals > away_goals:
                points += 3
            elif home_goals == away_goals:
                points += 1
        elif fixture_away_id == home_api_team_id:
            if away_goals > home_goals:
                points += 3
            elif away_goals == home_goals:
                points += 1
    return (points / max_points) if max_points else 0.5


def _build_match_context(
    match_row: Dict[str, Any],
    team_stats: List[Dict[str, Any]],
    team_rows: Dict[str, Dict[str, Any]],
    odds: Dict[str, float],
    injuries: List[Dict[str, Any]],
    h2h_rows: List[Dict[str, Any]],
    h2h_summary: Optional[Dict[str, Any]],
    weather_payload: Optional[Dict[str, Any]],
    pi_rating_delta: float,
) -> Dict[str, Any]:
    home_stats = [row for row in team_stats if row.get("team_id") == match_row["home_team_id"]]
    away_stats = [row for row in team_stats if row.get("team_id") == match_row["away_team_id"]]

    def avg(rows: List[Dict[str, Any]], key: str) -> float:
        values = [float(item.get(key, 0) or 0) for item in rows]
        return sum(values) / len(values) if values else 0.0

    home_form = avg(home_stats, "form_last6")
    away_form = avg(away_stats, "form_last6")
    home_goals_for = avg(home_stats, "goals_scored")
    home_goals_against = avg(home_stats, "goals_conceded")
    away_goals_for = avg(away_stats, "goals_scored")
    away_goals_against = avg(away_stats, "goals_conceded")
    home_xg_for = avg(home_stats, "xg_for")
    home_xg_against = avg(home_stats, "xg_against")
    away_xg_for = avg(away_stats, "xg_for")
    away_xg_against = avg(away_stats, "xg_against")

    home_market_value = float(team_rows.get(match_row["home_team_id"], {}).get("market_value", 0) or 0)
    away_market_value = float(team_rows.get(match_row["away_team_id"], {}).get("market_value", 0) or 0)
    market_value_delta_pct = ((home_market_value - away_market_value) / away_market_value * 100.0) if away_market_value > 0 else 0.0

    missing_players = len(injuries)
    key_absences = len(
        [
            row
            for row in injuries
            if any(
                token in f"{row.get('reason', '')} {row.get('status', '')} {row.get('type', '')}".lower()
                for token in ["susp", "ceza", "kirmizi", "yellow suspension", "injur", "doubt"]
            )
        ]
    )

    competition_type, competition_stage = _competition_type_and_stage(str(match_row.get("league", "")))
    home_api_id = int(team_rows.get(match_row["home_team_id"], {}).get("api_team_id", 0) or 0)
    h2h_ratio = (
        float(h2h_summary.get("ratio", 0.5))
        if isinstance(h2h_summary, dict) and h2h_summary.get("ratio") is not None
        else _h2h_points_ratio(h2h_rows, home_api_id)
    )
    weather_score = float(weather_payload.get("weather_score", 50.0)) if isinstance(weather_payload, dict) else 50.0
    opening_odd = odds.get("MS1")
    closing_odd = odds.get("MS1")
    odds_movement = 0.0
    if opening_odd and closing_odd and float(opening_odd) > 0:
        odds_movement = max(
            -1.0,
            min(1.0, ((float(opening_odd) - float(closing_odd)) / float(opening_odd)) * 5.0),
        )
    squad_availability = max(0.0, min(1.0, 1.0 - (missing_players * 0.08) - (key_absences * 0.12)))

    return {
        "form_points_last6": max(0.0, min(18.0, home_form * 18.0)),
        "home_form_score": max(0.0, min(1.0, home_form)),
        "away_form_score": max(0.0, min(1.0, away_form)),
        "home_attack": max(0.05, home_goals_for),
        "home_defense": max(0.05, home_goals_against),
        "away_attack": max(0.05, away_goals_for),
        "away_defense": max(0.05, away_goals_against),
        "home_attack_xg": max(0.05, home_xg_for),
        "home_defense_xg": max(0.05, home_xg_against),
        "away_attack_xg": max(0.05, away_xg_for),
        "away_defense_xg": max(0.05, away_xg_against),
        "league_avg_goals": 1.35,
        "home_advantage": 1.15,
        "ht_home_ratio": float(match_row.get("ht_home_ratio", 0.42) or 0.42),
        "ht_away_ratio": float(match_row.get("ht_away_ratio", 0.40) or 0.40),
        "xg_diff_last6": (home_xg_for - home_xg_against) - (away_xg_for - away_xg_against),
        "missing_players": float(missing_players),
        "key_absences": float(key_absences),
        "squad_availability": squad_availability,
        "xg_rolling_diff_10": home_xg_for - away_xg_for,
        "market_value_delta_pct": market_value_delta_pct,
        "opening_odd": opening_odd,
        "closing_odd": closing_odd,
        "odds_movement": odds_movement,
        "h2h_points_ratio": h2h_ratio,
        "h2h_ratio": h2h_ratio,
        "h2h_summary": h2h_summary or {"ratio": h2h_ratio},
        "h2h_matches": [
            {
                "home_goals": (
                    int(row.get("home_goals", 0) or 0)
                    if row.get("home_goals") is not None
                    else int(row.get("goals", {}).get("home", 0) or 0)
                ),
                "away_goals": (
                    int(row.get("away_goals", 0) or 0)
                    if row.get("away_goals") is not None
                    else int(row.get("goals", {}).get("away", 0) or 0)
                ),
                "is_cup": bool(row.get("is_cup", False)),
            }
            for row in h2h_rows
        ],
        "standing_pressure": 0.5,
        "competition_type": competition_type,
        "competition_stage": competition_stage,
        "is_group_last_week": False,
        "elimination_risk": False,
        "leadership_race": False,
        "home_position": 0,
        "league_size": 20,
        "points_gap_to_leader": 99,
        "social_sentiment_score": 0.0,
        "weather_score": weather_score,
        "weather_impact_score": (weather_score - 50.0) / 50.0,
        "pi_rating_delta": pi_rating_delta,
    }


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _build_criteria_scores_from_context(context: Dict[str, Any]) -> Dict[str, float]:
    opening = float(context.get("opening_odd", 0.0) or 0.0)
    closing = float(context.get("closing_odd", opening) or opening)
    movement_ratio = 0.0
    if opening > 0:
        movement_ratio = (opening - closing) / opening

    return {
        "form_last6_xg": _clamp_score((float(context.get("form_points_last6", 9.0) or 9.0) / 18.0) * 100.0),
        "squad_availability": _clamp_score(float(context.get("squad_availability", 0.5) or 0.5) * 100.0),
        "xg_rolling_10": _clamp_score((float(context.get("xg_rolling_diff_10", 0.0) or 0.0) + 2.0) / 4.0 * 100.0),
        "market_value": _clamp_score((float(context.get("market_value_delta_pct", 0.0) or 0.0) + 50.0)),
        "odds_movement": _clamp_score((movement_ratio + 1.0) / 2.0 * 100.0),
        "h2h_recent": _clamp_score(float(context.get("h2h_points_ratio", 0.5) or 0.5) * 100.0),
        "standing_motivation": _clamp_score(float(context.get("standing_pressure", 0.5) or 0.5) * 100.0),
        "social_sentiment": _clamp_score((float(context.get("social_sentiment_score", 0.0) or 0.0) + 1.0) / 2.0 * 100.0),
        "weather_pitch": _clamp_score(float(context.get("weather_score", 50.0) or 50.0)),
        "pi_rating_delta": _clamp_score((float(context.get("pi_rating_delta", 0.0) or 0.0) + 300.0) / 600.0 * 100.0),
    }


def _save_market_probabilities(
    client: Client,
    match_id: str,
    market_probabilities: Mapping[str, float],
    lambda_payload: Mapping[str, float],
) -> None:
    for market, probability in market_probabilities.items():
        row = {
            "match_id": match_id,
            "market": market,
            "probability": float(probability),
            "lambda_home": float(lambda_payload.get("home", 0.0) or 0.0),
            "lambda_away": float(lambda_payload.get("away", 0.0) or 0.0),
            "model_version": "prediction-engine-v3",
        }
        try:
            client.table("market_probabilities").upsert(row, on_conflict="match_id,market").execute()
        except Exception:
            # Table might not exist yet before migration is applied.
            break


def _save_predictions(
    client: Client,
    match_id: str,
    ev_result: Dict[str, Any],
    lambda_payload: Optional[Mapping[str, float]] = None,
) -> None:
    best = ev_result.get("best_market")
    if not best:
        return
    payload = {
        "match_id": match_id,
        "market_type": best["market_type"],
        "predicted_outcome": best["predicted_outcome"],
        "confidence_score": ev_result["confidence_score"],
        "ev_percentage": best["ev_percentage"],
        "recommended": bool(best["recommended"]),
        "kelly_pct": float(best.get("kelly_pct", 0.0) or 0.0),
        "lambda_home": float((lambda_payload or {}).get("home", 0.0) or 0.0),
        "lambda_away": float((lambda_payload or {}).get("away", 0.0) or 0.0),
        "ht_lambda_home": float((lambda_payload or {}).get("ht_home", 0.0) or 0.0),
        "ht_lambda_away": float((lambda_payload or {}).get("ht_away", 0.0) or 0.0),
    }
    try:
        try:
            existing = (
                client.table("predictions")
                .select("id")
                .eq("match_id", match_id)
                .eq("market_type", payload["market_type"])
                .limit(1)
                .execute()
            )
            if existing.data:
                client.table("predictions").update(payload).eq("id", existing.data[0]["id"]).execute()
            else:
                client.table("predictions").insert(payload).execute()
        except Exception:
            fallback = {k: v for k, v in payload.items() if k not in {"kelly_pct", "lambda_home", "lambda_away", "ht_lambda_home", "ht_lambda_away"}}
            existing = (
                client.table("predictions")
                .select("id")
                .eq("match_id", match_id)
                .eq("market_type", fallback["market_type"])
                .limit(1)
                .execute()
            )
            if existing.data:
                client.table("predictions").update(fallback).eq("id", existing.data[0]["id"]).execute()
            else:
                client.table("predictions").insert(fallback).execute()
        best_market_name = str(best.get("market_type") or "")
        client.table("matches").update(
            {
                "confidence_score": ev_result["confidence_score"],
                "best_bet": best_market_name,
            }
        ).eq("id", str(match_id)).execute()
    except Exception:
        logger.exception("Prediction save failed.")


async def _run_match_analysis(
    match_id_or_api_id: str,
    confidence_threshold: float,
    *,
    include_details: bool = False,
    refresh_live: bool = False,
) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    resolved_match_id = _resolve_match_id(client, match_id_or_api_id)
    if not resolved_match_id:
        raise HTTPException(status_code=404, detail="Match not found.")

    match_row = _fetch_match_base(client, resolved_match_id)
    team_rows = _fetch_team_rows(client, match_row["home_team_id"], match_row["away_team_id"])
    team_stats = _fetch_team_stats(client, [str(match_row["home_team_id"]), str(match_row["away_team_id"])])
    home_stats = [row for row in team_stats if row.get("team_id") == match_row["home_team_id"]]
    away_stats = [row for row in team_stats if row.get("team_id") == match_row["away_team_id"]]

    api_match_id = int(match_row.get("api_match_id", 0) or 0)
    sofascore_match_id = int(match_row.get("sofascore_id", 0) or 0)
    home_team_id = str(match_row["home_team_id"])
    away_team_id = str(match_row["away_team_id"])
    injuries: List[Dict[str, Any]] = []
    injuries_by_side: Dict[str, List[Dict[str, Any]]] = {"home": [], "away": []}
    h2h_rows: List[Dict[str, Any]] = []
    h2h_summary: Optional[Dict[str, Any]] = None
    h2h_matches: List[Dict[str, Any]] = []
    home_recent_form: List[Dict[str, Any]] = []
    away_recent_form: List[Dict[str, Any]] = []
    sofascore_standings: List[Dict[str, Any]] = []
    sofascore_season_stats: Dict[str, Dict[str, Any]] = {"home": {}, "away": {}}
    sofascore_top_players: Dict[str, List[Dict[str, Any]]] = {"home": [], "away": []}
    sofascore_event_meta: Dict[str, Any] = {}
    sofascore_tournament_id = 0
    sofascore_season_id = 0
    sofascore_mapping: Optional[Dict[str, int]] = None
    cached_sofascore_bundle = _fetch_cached_sofascore_bundle(
        client,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
    )
    if isinstance(cached_sofascore_bundle.get("season_team_stats"), dict):
        cached_season_stats = cached_sofascore_bundle.get("season_team_stats", {})
        if isinstance(cached_season_stats.get("home"), dict):
            sofascore_season_stats["home"] = cached_season_stats.get("home", {}) or {}
        if isinstance(cached_season_stats.get("away"), dict):
            sofascore_season_stats["away"] = cached_season_stats.get("away", {}) or {}
    if isinstance(cached_sofascore_bundle.get("top_players"), dict):
        cached_players = cached_sofascore_bundle.get("top_players", {})
        sofascore_top_players["home"] = list(cached_players.get("home") or [])
        sofascore_top_players["away"] = list(cached_players.get("away") or [])
    if isinstance(cached_sofascore_bundle.get("standings"), list):
        sofascore_standings = list(cached_sofascore_bundle.get("standings") or [])

    sofascore_tournament_id = int(cached_sofascore_bundle.get("tournament_id", 0) or 0)
    sofascore_season_id = int(cached_sofascore_bundle.get("season_id", 0) or 0)
    if sofascore_tournament_id > 0 or sofascore_season_id > 0:
        sofascore_event_meta = {
            "event_id": sofascore_match_id or None,
            "tournament_id": sofascore_tournament_id or None,
            "tournament_name": "",
            "season_id": sofascore_season_id or None,
            "season_name": "",
            "source": "cache",
        }

    cache_missing_for_details = bool(
        include_details
        and (
            not sofascore_season_stats.get("home")
            or not sofascore_season_stats.get("away")
            or not sofascore_top_players.get("home")
            or not sofascore_top_players.get("away")
            or not sofascore_standings
            or not str((team_rows.get(home_team_id, {}) or {}).get("logo_url") or "").strip()
            or not str((team_rows.get(away_team_id, {}) or {}).get("logo_url") or "").strip()
        )
    )
    should_refresh_enrichment = bool(
        ENABLE_SOFASCORE_ENRICHMENT and sofascore is not None and (refresh_live or cache_missing_for_details)
    )
    if api_match_id > 0 and refresh_live:
        await api_football.get_odds(api_match_id)
        await api_football.get_predictions(api_match_id)
        injuries = await api_football.get_injuries(api_match_id) or []

        home_api_id = int(team_rows.get(match_row["home_team_id"], {}).get("api_team_id", 0) or 0)
        away_api_id = int(team_rows.get(match_row["away_team_id"], {}).get("api_team_id", 0) or 0)
        if home_api_id > 0 and away_api_id > 0:
            h2h_rows = await api_football.get_head_to_head(home_api_id, away_api_id) or []
            h2h_summary = {"ratio": _h2h_points_ratio(h2h_rows, home_api_id)}

    if ENABLE_SOFASCORE_ENRICHMENT and sofascore is not None:
        if include_details and not refresh_live and cache_missing_for_details:
            try:
                sync_info = await sofascore.sync_match_sofascore_bundle(resolved_match_id, force=False)
                if isinstance(sync_info, dict):
                    sofascore_match_id = int(sync_info.get("event_id", 0) or sofascore_match_id)
                    if int(sync_info.get("tournament_id", 0) or 0) > 0:
                        sofascore_tournament_id = int(sync_info.get("tournament_id", 0) or 0)
                    if int(sync_info.get("season_id", 0) or 0) > 0:
                        sofascore_season_id = int(sync_info.get("season_id", 0) or 0)
                cached_sofascore_bundle = _fetch_cached_sofascore_bundle(
                    client,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                )
                team_rows = _fetch_team_rows(client, home_team_id, away_team_id)
                if isinstance(cached_sofascore_bundle.get("season_team_stats"), dict):
                    cached_season_stats = cached_sofascore_bundle.get("season_team_stats", {})
                    if isinstance(cached_season_stats.get("home"), dict):
                        sofascore_season_stats["home"] = cached_season_stats.get("home", {}) or {}
                    if isinstance(cached_season_stats.get("away"), dict):
                        sofascore_season_stats["away"] = cached_season_stats.get("away", {}) or {}
                if isinstance(cached_sofascore_bundle.get("top_players"), dict):
                    cached_players = cached_sofascore_bundle.get("top_players", {})
                    sofascore_top_players["home"] = list(cached_players.get("home") or [])
                    sofascore_top_players["away"] = list(cached_players.get("away") or [])
                if isinstance(cached_sofascore_bundle.get("standings"), list):
                    sofascore_standings = list(cached_sofascore_bundle.get("standings") or [])
                if int(cached_sofascore_bundle.get("tournament_id", 0) or 0) > 0:
                    sofascore_tournament_id = int(cached_sofascore_bundle.get("tournament_id", 0) or 0)
                if int(cached_sofascore_bundle.get("season_id", 0) or 0) > 0:
                    sofascore_season_id = int(cached_sofascore_bundle.get("season_id", 0) or 0)
            except Exception:
                logger.exception("Sofascore cache sync failed. match_id=%s", resolved_match_id)

            should_refresh_enrichment = bool(refresh_live)

        if should_refresh_enrichment:
            if sofascore_match_id > 0:
                sofascore_mapping = await sofascore._resolve_sofascore_team_ids_for_match(resolved_match_id)
                if not isinstance(sofascore_mapping, dict):
                    sofascore_mapping = {"event_id": sofascore_match_id}
            else:
                mapping = await sofascore._resolve_sofascore_team_ids_for_match(resolved_match_id)
                sofascore_match_id = int(mapping.get("event_id", 0) or 0) if isinstance(mapping, dict) else 0
                sofascore_mapping = mapping if isinstance(mapping, dict) else None
        else:
            sofascore_mapping = {
                "event_id": sofascore_match_id,
                "home_sofascore_id": int(team_rows.get(home_team_id, {}).get("sofascore_id", 0) or 0),
                "away_sofascore_id": int(team_rows.get(away_team_id, {}).get("sofascore_id", 0) or 0),
            }

        home_sofascore_id = int((sofascore_mapping or {}).get("home_sofascore_id", 0) or 0)
        away_sofascore_id = int((sofascore_mapping or {}).get("away_sofascore_id", 0) or 0)

        if sofascore_match_id > 0 and should_refresh_enrichment:
            event_detail = await sofascore.get_event_detail(sofascore_match_id, ttl_seconds=600)
            if isinstance(event_detail, dict):
                tournament = event_detail.get("tournament", {}) if isinstance(event_detail.get("tournament"), dict) else {}
                unique_tournament = (
                    tournament.get("uniqueTournament")
                    if isinstance(tournament.get("uniqueTournament"), dict)
                    else {}
                )
                season = event_detail.get("season", {}) if isinstance(event_detail.get("season"), dict) else {}
                tournament_id = int(unique_tournament.get("id", 0) or tournament.get("id", 0) or 0)
                season_id = int(season.get("id", 0) or season.get("year", 0) or 0)
                sofascore_tournament_id = tournament_id
                sofascore_season_id = season_id
                sofascore_event_meta = {
                    "event_id": sofascore_match_id,
                    "tournament_id": tournament_id,
                    "tournament_name": str(unique_tournament.get("name") or tournament.get("name") or ""),
                    "season_id": season_id,
                    "season_name": str(season.get("name") or season.get("year") or ""),
                }
                if tournament_id > 0 and season_id > 0:
                    standings_rows = await sofascore.get_tournament_standings(tournament_id, season_id)
                    if isinstance(standings_rows, list):
                        sofascore_standings = standings_rows
                    if home_sofascore_id > 0:
                        home_season_stats = await sofascore.get_team_season_statistics(
                            home_sofascore_id,
                            tournament_id,
                            season_id,
                        )
                        if isinstance(home_season_stats, dict) and home_season_stats:
                            sofascore_season_stats["home"] = home_season_stats
                    if away_sofascore_id > 0:
                        away_season_stats = await sofascore.get_team_season_statistics(
                            away_sofascore_id,
                            tournament_id,
                            season_id,
                        )
                        if isinstance(away_season_stats, dict) and away_season_stats:
                            sofascore_season_stats["away"] = away_season_stats

                    season_rows = await sofascore.get_tournament_season_overall_statistics(tournament_id, season_id)
                    if isinstance(season_rows, list):
                        by_team = {
                            int(row.get("team_sofascore_id", 0) or 0): row
                            for row in season_rows
                            if isinstance(row, dict)
                        }
                        if home_sofascore_id > 0 and not sofascore_season_stats.get("home"):
                            sofascore_season_stats["home"] = by_team.get(home_sofascore_id, {})
                        if away_sofascore_id > 0 and not sofascore_season_stats.get("away"):
                            sofascore_season_stats["away"] = by_team.get(away_sofascore_id, {})

                    if isinstance(sofascore_standings, list):
                        standing_by_team = {
                            int(row.get("team_sofascore_id", 0) or 0): row
                            for row in sofascore_standings
                            if isinstance(row, dict)
                        }
                        if home_sofascore_id > 0 and not sofascore_season_stats.get("home"):
                            home_row = standing_by_team.get(home_sofascore_id, {})
                            played = int(home_row.get("played", 0) or 0)
                            goals_for = float(home_row.get("goals_for", 0) or 0)
                            goals_against = float(home_row.get("goals_against", 0) or 0)
                            per_match_divisor = float(played) if played > 0 else 1.0
                            sofascore_season_stats["home"] = {
                                "matches_played": played,
                                "goals_for": goals_for,
                                "goals_against": goals_against,
                                "goals_per_match": round(goals_for / per_match_divisor, 3),
                                "goals_conceded_per_match": round(goals_against / per_match_divisor, 3),
                                "clean_sheets": 0,
                                "assists": 0,
                                "expected_goals": round(goals_for / played, 3) if played > 0 else 0.0,
                                "shots_on_target": 0.0,
                                "big_chances": 0.0,
                                "possession": 0.0,
                                "avg_rating": 0.0,
                            }
                        if away_sofascore_id > 0 and not sofascore_season_stats.get("away"):
                            away_row = standing_by_team.get(away_sofascore_id, {})
                            played = int(away_row.get("played", 0) or 0)
                            goals_for = float(away_row.get("goals_for", 0) or 0)
                            goals_against = float(away_row.get("goals_against", 0) or 0)
                            per_match_divisor = float(played) if played > 0 else 1.0
                            sofascore_season_stats["away"] = {
                                "matches_played": played,
                                "goals_for": goals_for,
                                "goals_against": goals_against,
                                "goals_per_match": round(goals_for / per_match_divisor, 3),
                                "goals_conceded_per_match": round(goals_against / per_match_divisor, 3),
                                "clean_sheets": 0,
                                "assists": 0,
                                "expected_goals": round(goals_for / played, 3) if played > 0 else 0.0,
                                "shots_on_target": 0.0,
                                "big_chances": 0.0,
                                "possession": 0.0,
                                "avg_rating": 0.0,
                            }

                    if isinstance(sofascore_standings, list):
                        standing_by_team = {
                            int(row.get("team_sofascore_id", 0) or 0): row
                            for row in sofascore_standings
                            if isinstance(row, dict)
                        }
                        if home_sofascore_id > 0 and isinstance(sofascore_season_stats.get("home"), dict):
                            home_row = standing_by_team.get(home_sofascore_id, {})
                            if home_row:
                                sofascore_season_stats["home"]["position"] = int(home_row.get("position", 0) or 0)
                        if away_sofascore_id > 0 and isinstance(sofascore_season_stats.get("away"), dict):
                            away_row = standing_by_team.get(away_sofascore_id, {})
                            if away_row:
                                sofascore_season_stats["away"]["position"] = int(away_row.get("position", 0) or 0)

            sofa_h2h = await sofascore.get_h2h(sofascore_match_id)
            if isinstance(sofa_h2h, dict):
                if sofa_h2h.get("ratio") is not None:
                    h2h_summary = sofa_h2h
                if isinstance(sofa_h2h.get("matches"), list):
                    h2h_matches = sofa_h2h.get("matches") or []
            sofa_injuries = await sofascore.get_match_injuries(sofascore_match_id)
            if isinstance(sofa_injuries, dict):
                injuries_by_side = {
                    "home": sofa_injuries.get("home", []) or [],
                    "away": sofa_injuries.get("away", []) or [],
                }

        if home_sofascore_id > 0 and should_refresh_enrichment:
            home_recent_form = await sofascore.get_team_recent_matches(home_sofascore_id, limit=6)
            await sofascore.get_team_halftime_statistics(
                team_id=home_team_id,
                sofascore_team_id=home_sofascore_id,
                season=str(match_row.get("season") or ""),
            )
            sofascore_top_players["home"] = await sofascore.get_team_top_players(
                home_sofascore_id,
                limit=5,
                tournament_id=sofascore_tournament_id if sofascore_tournament_id > 0 else None,
                season_id=sofascore_season_id if sofascore_season_id > 0 else None,
            )
        if away_sofascore_id > 0 and should_refresh_enrichment:
            away_recent_form = await sofascore.get_team_recent_matches(away_sofascore_id, limit=6)
            await sofascore.get_team_halftime_statistics(
                team_id=away_team_id,
                sofascore_team_id=away_sofascore_id,
                season=str(match_row.get("season") or ""),
            )
            sofascore_top_players["away"] = await sofascore.get_team_top_players(
                away_sofascore_id,
                limit=5,
                tournament_id=sofascore_tournament_id if sofascore_tournament_id > 0 else None,
                season_id=sofascore_season_id if sofascore_season_id > 0 else None,
            )

        if home_sofascore_id > 0 and away_sofascore_id > 0 and should_refresh_enrichment:
            pair_h2h = await sofascore.get_h2h_matches(home_sofascore_id, away_sofascore_id, limit=5)
            if pair_h2h:
                h2h_matches = pair_h2h
                h2h_rows = [
                    {
                        "match_date": row.get("match_date"),
                        "home_goals": int(row.get("home_goals", 0) or 0),
                        "away_goals": int(row.get("away_goals", 0) or 0),
                        "league": row.get("league"),
                        "is_cup": bool(row.get("is_cup", False)),
                    }
                    for row in pair_h2h
                    if isinstance(row, dict)
                ]
                if not isinstance(h2h_summary, dict):
                    home_wins = len(
                        [r for r in h2h_rows if int(r.get("home_goals", 0) or 0) > int(r.get("away_goals", 0) or 0)]
                    )
                    away_wins = len(
                        [r for r in h2h_rows if int(r.get("home_goals", 0) or 0) < int(r.get("away_goals", 0) or 0)]
                    )
                    draws = len(
                        [r for r in h2h_rows if int(r.get("home_goals", 0) or 0) == int(r.get("away_goals", 0) or 0)]
                    )
                    total = home_wins + away_wins + draws
                    h2h_summary = {
                        "home_wins": home_wins,
                        "away_wins": away_wins,
                        "draws": draws,
                        "ratio": round(home_wins / total, 4) if total > 0 else 0.5,
                    }

        if home_sofascore_id > 0 and away_sofascore_id > 0 and should_refresh_enrichment and not h2h_matches:
            away_name_norm = _normalize_team_name_for_matching(str(team_rows.get(away_team_id, {}).get("name", "")))
            home_name_norm = _normalize_team_name_for_matching(str(team_rows.get(home_team_id, {}).get("name", "")))
            home_history = await sofascore.get_team_recent_matches(home_sofascore_id, limit=120)
            derived: List[Dict[str, Any]] = []
            for item in home_history:
                item_home_id = int(item.get("home_team_id", 0) or 0)
                item_away_id = int(item.get("away_team_id", 0) or 0)
                id_match = (
                    (item_home_id == home_sofascore_id and item_away_id == away_sofascore_id)
                    or (item_home_id == away_sofascore_id and item_away_id == home_sofascore_id)
                )
                item_home = _normalize_team_name_for_matching(str(item.get("home_team_name", "")))
                item_away = _normalize_team_name_for_matching(str(item.get("away_team_name", "")))
                name_match = (
                    ((item_home == away_name_norm) or (item_away == away_name_norm))
                    and ((item_home == home_name_norm) or (item_away == home_name_norm))
                )
                if not (id_match or name_match):
                    continue
                derived.append(item)
            if derived:
                h2h_matches = [
                    {
                        "date": str(row.get("date") or "")[:10],
                        "match_date": row.get("date"),
                        "home_team": row.get("home_team_name"),
                        "away_team": row.get("away_team_name"),
                        "home_goals": int(row.get("home_goals", 0) or 0),
                        "away_goals": int(row.get("away_goals", 0) or 0),
                        "league": row.get("league"),
                        "is_cup": bool(row.get("is_cup", False)),
                        "sofascore_id": int(row.get("event_id", 0) or 0) or None,
                    }
                    for row in derived[:5]
                ]
                h2h_rows = [
                    {
                        "match_date": row.get("match_date"),
                        "home_goals": int(row.get("home_goals", 0) or 0),
                        "away_goals": int(row.get("away_goals", 0) or 0),
                        "league": row.get("league"),
                        "is_cup": bool(row.get("is_cup", False)),
                    }
                    for row in h2h_matches
                ]

        should_backfill_team_stats = (
            not home_stats
            or not away_stats
            or (_avg_stat(home_stats, "xg_for", limit=10) <= 0 and _avg_stat(away_stats, "xg_for", limit=10) <= 0)
        )
        if should_refresh_enrichment and should_backfill_team_stats and home_sofascore_id > 0 and away_sofascore_id > 0:
            await sofascore.populate_team_stats_for_match(resolved_match_id)
            team_stats = _fetch_team_stats(client, [str(match_row["home_team_id"]), str(match_row["away_team_id"])])
            home_stats = [row for row in team_stats if row.get("team_id") == match_row["home_team_id"]]
            away_stats = [row for row in team_stats if row.get("team_id") == match_row["away_team_id"]]

    if not h2h_rows:
        h2h_rows = _fetch_h2h_rows(client, home_team_id, away_team_id, limit=10)
    if not h2h_matches and isinstance(h2h_summary, dict) and isinstance(h2h_summary.get("matches"), list):
        h2h_matches = h2h_summary.get("matches") or []
    if not h2h_matches and h2h_rows:
        h2h_matches = [
            {
                "date": str(row.get("match_date") or "")[:10],
                "match_date": row.get("match_date"),
                "home_team": team_rows.get(home_team_id, {}).get("name", "Home"),
                "away_team": team_rows.get(away_team_id, {}).get("name", "Away"),
                "home_goals": int(row.get("home_goals", 0) or 0),
                "away_goals": int(row.get("away_goals", 0) or 0),
                "league": row.get("league"),
                "is_cup": bool(row.get("is_cup", False)),
                "teams": {
                    "home": {"name": team_rows.get(home_team_id, {}).get("name", "Home")},
                    "away": {"name": team_rows.get(away_team_id, {}).get("name", "Away")},
                },
                "goals": {
                    "home": int(row.get("home_goals", 0) or 0),
                    "away": int(row.get("away_goals", 0) or 0),
                },
            }
            for row in h2h_rows[:5]
        ]

    if not injuries_by_side["home"] and not injuries_by_side["away"]:
        injuries_by_side = _fetch_match_injuries(client, resolved_match_id, home_team_id, away_team_id)

    if injuries_by_side["home"] or injuries_by_side["away"]:
        injuries = _flatten_injuries(
            injuries_by_side,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_team_name=str(team_rows.get(home_team_id, {}).get("name", "Ev Sahibi")),
            away_team_name=str(team_rows.get(away_team_id, {}).get("name", "Deplasman")),
        )

    if refresh_live:
        for team_id in [str(match_row["home_team_id"]), str(match_row["away_team_id"])]:
            row = team_rows.get(team_id, {})
            current_value = float(row.get("market_value", 0) or 0)
            team_name = str(row.get("name", "")).strip()
            if current_value > 0 or not team_name:
                continue
            fetched_value = await transfermarkt_service.get_team_market_value(team_name)
            if fetched_value is not None and fetched_value > 0:
                row["market_value"] = fetched_value
                try:
                    if client:
                        client.table("teams").update({"market_value": fetched_value}).eq("id", team_id).execute()
                except Exception:
                    logger.warning("Market value runtime update failed. team_id=%s", team_id)

    home_team = team_rows.get(str(match_row["home_team_id"]), {})
    away_team = team_rows.get(str(match_row["away_team_id"]), {})
    home_pi = home_team.get("pi_rating")
    away_pi = away_team.get("pi_rating")
    if home_pi is not None and away_pi is not None:
        pi_rating_delta = float(home_pi or 1500) - float(away_pi or 1500)
    else:
        pi_rating_delta = _estimate_pi_rating_delta(
            client,
            str(match_row["home_team_id"]),
            str(match_row["away_team_id"]),
        )

    ht_ratios = _fetch_ht_ratios(
        client,
        home_team_id=str(match_row["home_team_id"]),
        away_team_id=str(match_row["away_team_id"]),
        season=str(match_row.get("season") or ""),
    )
    match_row["ht_home_ratio"] = ht_ratios["home"]
    match_row["ht_away_ratio"] = ht_ratios["away"]

    live_odds = await odds_scraper.get_odds_for_match(resolved_match_id) if refresh_live else {}
    stored_odds = _fetch_odds(client, resolved_match_id)
    odds = {**stored_odds, **live_odds}
    weather_city = str(team_rows.get(match_row["home_team_id"], {}).get("country") or "").strip()
    weather_payload = await weather_service.get_match_weather(weather_city, str(match_row.get("match_date", "")))
    context = _build_match_context(
        match_row,
        team_stats,
        team_rows,
        odds,
        injuries,
        h2h_rows,
        h2h_summary,
        weather_payload,
        pi_rating_delta,
    )
    if home_recent_form:
        context["form_points_last6"] = round(_form_score_from_results([str(item.get("result") or "D") for item in home_recent_form]) * 18.0, 3)
    if away_recent_form:
        away_points = _form_score_from_results([str(item.get("result") or "D") for item in away_recent_form]) * 18.0
        home_points = float(context.get("form_points_last6", 9.0) or 9.0)
        context["standing_pressure"] = max(0.0, min(1.0, 0.5 + ((home_points - away_points) / 36.0)))
    if injuries_by_side["home"] or injuries_by_side["away"]:
        context["missing_players"] = float(len(injuries_by_side["home"]) + len(injuries_by_side["away"]))
        context["key_absences"] = float(
            len(
                [
                    item
                    for side in ["home", "away"]
                    for item in (injuries_by_side.get(side, []) or [])
                    if str(item.get("status", "")).lower() in {"injured", "suspended", "doubtful"}
                ]
            )
        )
    if isinstance(h2h_summary, dict) and h2h_summary.get("ratio") is not None:
        context["h2h_ratio"] = float(h2h_summary.get("ratio", 0.5) or 0.5)
        context["h2h_points_ratio"] = float(h2h_summary.get("ratio", 0.5) or 0.5)
    if h2h_rows:
        context["h2h_matches"] = h2h_rows
    home_form_payload = _build_form_payload(recent_matches=home_recent_form, fallback_stats=home_stats)
    away_form_payload = _build_form_payload(recent_matches=away_recent_form, fallback_stats=away_stats)

    bookmaker_odds = _fetch_bookmaker_odds_entries(client, resolved_match_id)
    if live_odds:
        bookmaker_odds.append(
            {
                "book": "live",
                **{
                    market: float(odd)
                    for market, odd in live_odds.items()
                    if market in SUPPORTED_MARKETS and float(odd) > 1.0
                },
            }
        )

    engine_match_data = _build_engine_match_data(
        match_id=resolved_match_id,
        league=str(match_row.get("league", "") or "default"),
        home_stats=home_stats,
        away_stats=away_stats,
        home_form_payload=home_form_payload,
        away_form_payload=away_form_payload,
        h2h_rows=h2h_rows,
    )
    engine_result = run_prediction_engine(
        match_data=engine_match_data,
        home_stats=engine_match_data.get("home_team_stats", {}),
        away_stats=engine_match_data.get("away_team_stats", {}),
        h2h=engine_match_data.get("h2h", {}),
        bookmakers=bookmaker_odds,
        opening_odds=stored_odds,
    )
    engine_confidence = float(engine_result.get("confidence_score", 0.0) or 0.0)

    probabilities = {
        str(market): float(probability)
        for market, probability in (engine_result.get("probabilities", {}) or {}).items()
    }
    lambda_payload = {
        "home": float((engine_result.get("lambda", {}) or {}).get("home", 0.0) or 0.0),
        "away": float((engine_result.get("lambda", {}) or {}).get("away", 0.0) or 0.0),
        "ht_home": float((engine_result.get("lambda", {}) or {}).get("ht_home", 0.0) or 0.0),
        "ht_away": float((engine_result.get("lambda", {}) or {}).get("ht_away", 0.0) or 0.0),
    }
    odd_map = {
        market: float(odd)
        for market, odd in odds.items()
        if market in SUPPORTED_MARKETS and float(odd) > 0
    }
    ev_result = _build_ev_result_from_engine(
        engine_result=engine_result,
        confidence_threshold=confidence_threshold,
    )
    criteria_scores = _build_criteria_scores_from_context(context)
    criteria_average = round(sum(criteria_scores.values()) / max(len(criteria_scores), 1), 2)
    analysis = {
        "confidence_score": round(engine_confidence, 2),
        "recommended": bool(ev_result.get("recommended", False)),
        "engine": str((engine_result.get("meta", {}) or {}).get("model", "prediction-engine-v3")),
        "criteria_scores": criteria_scores,
        "score_breakdown": criteria_scores,
        "criteria_average": criteria_average,
        "confidence_detail": {},
    }
    _save_market_probabilities(client, resolved_match_id, probabilities, lambda_payload)
    _save_predictions(client, resolved_match_id, ev_result, lambda_payload=lambda_payload)
    odds_scraper.save_ev_rows(match_id=resolved_match_id, ev_result=ev_result)
    best_market = ev_result.get("best_market") or {}
    payload: Dict[str, Any] = {
        "match_id": resolved_match_id,
        "lambda": {
            "home": lambda_payload.get("home", 0.0),
            "away": lambda_payload.get("away", 0.0),
            "ht_home": lambda_payload.get("ht_home", 0.0),
            "ht_away": lambda_payload.get("ht_away", 0.0),
        },
        "confidence_score": round(engine_confidence, 2),
        "analysis": analysis,
        "confidence_detail": engine_result.get("confidence_detail", {}),
        "ev": ev_result,
        "recommended_market": {
            **best_market,
            "market": best_market.get("market") or best_market.get("market_type"),
        }
        if best_market
        else None,
        "meta": engine_result.get("meta", {"model": "prediction-engine-v3"}),
    }
    if include_details:
        home_team = team_rows.get(str(match_row["home_team_id"]), {})
        away_team = team_rows.get(str(match_row["away_team_id"]), {})
        payload["match"] = {
            "id": resolved_match_id,
            "league": match_row.get("league"),
            "match_date": match_row.get("match_date"),
            "status": match_row.get("status"),
            "home_team": {
                "id": match_row.get("home_team_id"),
                "name": home_team.get("name", "Ev Sahibi"),
                "country": home_team.get("country"),
                "logo_url": home_team.get("logo_url"),
            },
            "away_team": {
                "id": match_row.get("away_team_id"),
                "name": away_team.get("name", "Deplasman"),
                "country": away_team.get("country"),
                "logo_url": away_team.get("logo_url"),
            },
        }
        home_attack_xg = _avg_stat(home_stats, "xg_for", limit=10)
        home_defense_xg = _avg_stat(home_stats, "xg_against", limit=10)
        away_attack_xg = _avg_stat(away_stats, "xg_for", limit=10)
        away_defense_xg = _avg_stat(away_stats, "xg_against", limit=10)
        h2h_summary_payload = h2h_summary or {"ratio": context.get("h2h_ratio", 0.5)}
        if isinstance(h2h_summary_payload, dict):
            if "home_win_rate" not in h2h_summary_payload:
                h2h_summary_payload["home_win_rate"] = float(h2h_summary_payload.get("ratio", 0.5) or 0.5)
        h2h_response_matches = h2h_matches[:5] if h2h_matches else []
        payload["form"] = {
            "home": {
                "last6": home_form_payload["last6"],
                "score": home_form_payload["score"],
                "matches": home_form_payload["matches"],
            },
            "away": {
                "last6": away_form_payload["last6"],
                "score": away_form_payload["score"],
                "matches": away_form_payload["matches"],
            },
        }
        payload["form_legacy"] = {
            "home": home_form_payload["legacy"],
            "away": away_form_payload["legacy"],
        }
        payload["injuries"] = injuries_by_side
        payload["injuries_flat"] = injuries
        payload["h2h"] = {
            "summary": h2h_summary_payload,
            "matches": h2h_response_matches,
            "last5": h2h_response_matches,
        }
        payload["xg"] = {
            "home": {
                "attack_xg": home_attack_xg,
                "defense_xg": home_defense_xg,
            },
            "away": {
                "attack_xg": away_attack_xg,
                "defense_xg": away_defense_xg,
            },
            "legacy": {
                "home": home_attack_xg,
                "away": away_attack_xg,
            },
        }
        payload["context"] = context
        payload["market_odds"] = odd_map
        payload["sofascore"] = {
            "enabled": bool(ENABLE_SOFASCORE_ENRICHMENT),
            "event": sofascore_event_meta,
            "standings": sofascore_standings,
            "season_team_stats": sofascore_season_stats,
            "top_players": sofascore_top_players,
        }
    return payload


@app.get("/health")
async def healthcheck() -> Dict[str, Any]:
    supabase_connected = False
    error_message = None
    try:
        client = get_supabase_client()
        client.table("teams").select("id").limit(1).execute()
        supabase_connected = True
    except Exception as exc:
        error_message = str(exc)

    return {
        "status": "healthy" if supabase_connected else "degraded",
        "supabase_connected": supabase_connected,
        "scheduler": scheduler.scheduler_status(),
        "api_football_remaining": scheduler.api_service.requests_remaining,
        "odds_api_remaining": odds_scraper.odds_api.requests_remaining,
        "the_odds_remaining": odds_scraper.odds_api.requests_remaining,
        "odds_provider": "betfair_exchange",
        "sofascore_enrichment_enabled": bool(ENABLE_SOFASCORE_ENRICHMENT),
        "api_keys": {
            "api_football": bool(os.getenv("API_FOOTBALL_KEY")),
            "odds_api_io": bool(os.getenv("ODDS_API_IO_KEY") or os.getenv("THE_ODDS_API_KEY")),
            "the_odds": bool(os.getenv("ODDS_API_IO_KEY") or os.getenv("THE_ODDS_API_KEY")),
            "sofascore_cookie": bool(os.getenv("SOFASCORE_COOKIE")),
            "openweather": bool(os.getenv("OPENWEATHER_API_KEY")) and "BURAYA_" not in str(os.getenv("OPENWEATHER_API_KEY")),
            "supabase_service": bool(os.getenv("SUPABASE_SERVICE_KEY")),
        },
        "error": error_message,
        "time": datetime.now().isoformat(),
    }


@app.post("/admin/backfill/full")
async def start_full_backfill() -> Dict[str, Any]:
    global backfill_task

    if backfill_task is not None and not backfill_task.done():
        return {"status": "running", "message": "Backfill zaten çalışıyor"}

    backfill_task = asyncio.create_task(_run_full_backfill())
    return {"status": "started", "message": "Backfill arka planda çalışıyor"}


@app.get("/admin/backfill/status")
async def get_backfill_status() -> Dict[str, Any]:
    task_running = backfill_task is not None and not backfill_task.done()
    return {
        "status": backfill_state.get("status"),
        "running": backfill_state.get("running") or task_running,
        "started_at": backfill_state.get("started_at"),
        "finished_at": backfill_state.get("finished_at"),
        "last_error": backfill_state.get("last_error"),
        "last_result": backfill_state.get("last_result"),
    }


@app.post("/admin/reset-and-refetch")
async def reset_and_refetch() -> Dict[str, Any]:
    global reset_refetch_task
    if reset_refetch_task is not None and not reset_refetch_task.done():
        return {"status": "running", "message": "Reset/refetch zaten calisiyor"}
    reset_refetch_task = asyncio.create_task(_run_reset_and_refetch())
    return {
        "status": "reset_started",
        "message": "Tum analizler temizlendi, yeni motorla yeniden hesaplama basladi",
    }


@app.get("/admin/stats")
async def admin_stats() -> Dict[str, Any]:
    backfill_running = backfill_task is not None and not backfill_task.done()
    reset_running = reset_refetch_task is not None and not reset_refetch_task.done()
    backtest_running = backtest_task is not None and not backtest_task.done()
    team_profile_running = team_profile_backfill_task is not None and not team_profile_backfill_task.done()
    return {
        "backfill": {
            "status": backfill_state.get("status"),
            "running": backfill_state.get("running") or backfill_running,
            "started_at": backfill_state.get("started_at"),
            "finished_at": backfill_state.get("finished_at"),
            "last_error": backfill_state.get("last_error"),
            "last_result": backfill_state.get("last_result"),
        },
        "reset_refetch": {
            "status": reset_refetch_state.get("status"),
            "running": reset_refetch_state.get("running") or reset_running,
            "started_at": reset_refetch_state.get("started_at"),
            "finished_at": reset_refetch_state.get("finished_at"),
            "processed": reset_refetch_state.get("processed"),
            "total_matches_scanned": reset_refetch_state.get("total_matches_scanned"),
            "success": reset_refetch_state.get("success"),
            "failed": reset_refetch_state.get("failed"),
            "skipped_no_odds": reset_refetch_state.get("skipped_no_odds"),
            "last_error": reset_refetch_state.get("last_error"),
        },
        "backtest": {
            "status": backtest_state.get("status"),
            "running": backtest_state.get("running") or backtest_running,
            "started_at": backtest_state.get("started_at"),
            "finished_at": backtest_state.get("finished_at"),
            "processed": backtest_state.get("processed"),
            "total_matches_scanned": backtest_state.get("total_matches_scanned"),
            "success": backtest_state.get("success"),
            "failed": backtest_state.get("failed"),
            "skipped_no_odds": backtest_state.get("skipped_no_odds"),
            "skipped_no_market": backtest_state.get("skipped_no_market"),
            "summary": backtest_state.get("summary"),
            "last_error": backtest_state.get("last_error"),
        },
        "team_profile_backfill": {
            "status": team_profile_backfill_state.get("status"),
            "running": team_profile_backfill_state.get("running") or team_profile_running,
            "started_at": team_profile_backfill_state.get("started_at"),
            "finished_at": team_profile_backfill_state.get("finished_at"),
            "chunk_size": team_profile_backfill_state.get("chunk_size"),
            "max_chunks": team_profile_backfill_state.get("max_chunks"),
            "force": team_profile_backfill_state.get("force"),
            "chunks_completed": team_profile_backfill_state.get("chunks_completed"),
            "processed": team_profile_backfill_state.get("processed"),
            "updated": team_profile_backfill_state.get("updated"),
            "failed": team_profile_backfill_state.get("failed"),
            "pending_remaining": team_profile_backfill_state.get("pending_remaining"),
            "last_error": team_profile_backfill_state.get("last_error"),
        },
    }


@app.get("/admin/backtest/dataset")
async def get_backtest_dataset(
    days_back: int = Query(default=30, ge=3, le=365),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    league: Optional[str] = Query(default=None),
    max_matches: int = Query(default=300, ge=20, le=1000),
    preview_limit: int = Query(default=100, ge=10, le=300),
) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    window_start, window_end = _resolve_backtest_window(
        start_date=start_date,
        end_date=end_date,
        days_back=days_back,
    )
    matches = _fetch_finished_matches_for_backtest(
        client,
        start_date=window_start,
        end_date=window_end,
        league_filter=league,
        max_matches=max_matches,
    )
    match_ids = [str(item.get("id") or "") for item in matches if item.get("id")]
    odds_match_ids: set[str] = set()
    bookmaker = getattr(odds_scraper, "bookmaker_key", "betfair_exchange")

    if match_ids:
        try:
            rows = (
                client.table("odds_history")
                .select("match_id")
                .in_("match_id", match_ids)
                .eq("bookmaker", bookmaker)
                .limit(5000)
                .execute()
                .data
                or []
            )
            odds_match_ids = {str(row.get("match_id") or "") for row in rows if row.get("match_id")}
        except Exception:
            odds_match_ids = set()

    if len(odds_match_ids) < len(match_ids):
        try:
            rows = (
                client.table("odds")
                .select("match_id")
                .in_("match_id", match_ids)
                .limit(5000)
                .execute()
                .data
                or []
            )
            odds_match_ids.update({str(row.get("match_id") or "") for row in rows if row.get("match_id")})
        except Exception:
            pass

    team_ids = sorted(
        {
            str(item.get("home_team_id") or "")
            for item in matches
            if item.get("home_team_id")
        }
        | {
            str(item.get("away_team_id") or "")
            for item in matches
            if item.get("away_team_id")
        }
    )
    team_map: Dict[str, str] = {}
    if team_ids:
        try:
            teams = client.table("teams").select("id,name").in_("id", team_ids).execute().data or []
            team_map = {str(row.get("id")): str(row.get("name") or "") for row in teams}
        except Exception:
            team_map = {}

    preview: List[Dict[str, Any]] = []
    for row in matches[: max(1, preview_limit)]:
        match_id = str(row.get("id") or "")
        preview.append(
            {
                "match_id": match_id,
                "match_date": row.get("match_date"),
                "league": row.get("league"),
                "home_team": team_map.get(str(row.get("home_team_id") or ""), "Ev Sahibi"),
                "away_team": team_map.get(str(row.get("away_team_id") or ""), "Deplasman"),
                "score": f"{int(row.get('ft_home', 0) or 0)}-{int(row.get('ft_away', 0) or 0)}",
                "has_odds": match_id in odds_match_ids,
            }
        )

    return {
        "window": {
            "start_date": window_start.isoformat(),
            "end_date": window_end.isoformat(),
            "days_back": int(days_back),
        },
        "league_filter": str(league or ""),
        "total_matches_scanned": len(matches),
        "matches_with_odds": len([match_id for match_id in match_ids if match_id in odds_match_ids]),
        "preview_count": len(preview),
        "preview": preview,
    }


@app.post("/admin/backtest/run")
async def start_backtest_run(body: BacktestRunRequest) -> Dict[str, Any]:
    global backtest_task
    if backtest_task is not None and not backtest_task.done():
        return {"status": "running", "message": "Backtest zaten calisiyor"}
    backtest_task = asyncio.create_task(_run_backtest_lab(body))
    return {
        "status": "started",
        "message": "Backtest arka planda baslatildi",
        "params": body.model_dump(),
    }


@app.get("/admin/backtest/status")
async def get_backtest_status() -> Dict[str, Any]:
    task_running = backtest_task is not None and not backtest_task.done()
    return {
        "status": backtest_state.get("status"),
        "running": backtest_state.get("running") or task_running,
        "started_at": backtest_state.get("started_at"),
        "finished_at": backtest_state.get("finished_at"),
        "params": backtest_state.get("params"),
        "processed": backtest_state.get("processed"),
        "total_matches_scanned": backtest_state.get("total_matches_scanned"),
        "success": backtest_state.get("success"),
        "failed": backtest_state.get("failed"),
        "skipped_no_odds": backtest_state.get("skipped_no_odds"),
        "skipped_no_market": backtest_state.get("skipped_no_market"),
        "summary": backtest_state.get("summary"),
        "rows": backtest_state.get("rows") or [],
        "last_error": backtest_state.get("last_error"),
    }


@app.post("/backtest/sofascore")
async def run_sofascore_backtest(
    days_back: int = Query(default=15, ge=1, le=60),
    include_non_recommended: bool = Query(default=False),
    limit_results: int = Query(default=200, ge=10, le=1000),
) -> Dict[str, Any]:
    _ = (days_back, include_non_recommended, limit_results)
    raise HTTPException(
        status_code=410,
        detail="Sofascore backtest devre disi. Sistem yalnizca Betfair/Odds-API ile calisiyor.",
    )


@app.get("/test/fetch-today")
async def test_fetch_today() -> Dict[str, Any]:
    today = datetime.now(scheduler.timezone).date().isoformat()
    result = await scheduler.fetch_specific_dates([today])
    return {"date": today, "fetched_matches": result["total_saved"], "by_date": result["by_date"]}


@app.get("/test/analyze/{match_id}")
async def test_analyze(
    match_id: str,
    confidence_threshold: float = Query(default=60.0, ge=0.0, le=100.0),
    refresh: bool = Query(default=False),
) -> Dict[str, Any]:
    return await _run_match_analysis(match_id, confidence_threshold, refresh_live=refresh)


@app.get("/test/populate-stats/{match_id}")
async def test_populate_stats(match_id: str) -> Dict[str, Any]:
    if not ENABLE_SOFASCORE_ENRICHMENT or sofascore is None:
        raise HTTPException(status_code=410, detail="Sofascore enrichment devre disi.")

    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    resolved_match_id = _resolve_match_id(client, match_id)
    if not resolved_match_id:
        raise HTTPException(status_code=404, detail="Match not found.")
    match_row = _fetch_match_base(client, resolved_match_id)

    home_team_id = str(match_row.get("home_team_id") or "")
    away_team_id = str(match_row.get("away_team_id") or "")
    before = {
        "home_xg_rolling_10": _team_xg_rolling_10(client, home_team_id),
        "away_xg_rolling_10": _team_xg_rolling_10(client, away_team_id),
    }

    populate_result = await sofascore.populate_team_stats_for_match(resolved_match_id)
    if not populate_result:
        return {
            "match_id": resolved_match_id,
            "before": before,
            "after": before,
            "updated": False,
            "detail": "Sofascore team mapping bulunamadi veya veri cekilemedi.",
        }

    after = {
        "home_xg_rolling_10": _team_xg_rolling_10(client, home_team_id),
        "away_xg_rolling_10": _team_xg_rolling_10(client, away_team_id),
    }
    return {
        "match_id": resolved_match_id,
        "before": before,
        "after": after,
        "updated": True,
        "populate_result": populate_result,
    }


@app.get("/test/api-football/odds/{fixture_id}")
async def test_api_football_odds(fixture_id: int) -> Dict[str, Any]:
    rows = await api_football.get_odds(fixture_id)
    return {"fixture_id": fixture_id, "rows_saved_or_updated": len(rows or []), "sample": (rows or [])[:10]}


@app.get("/test/odds/{odds_api_event_id}")
async def test_odds_api_odds(odds_api_event_id: int) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    match_id_before = _resolve_match_id(client, str(odds_api_event_id))
    odds_rows_before = _count_odds_rows(client, match_id_before)
    raw_payload = await odds_scraper.odds_api.get_odds_single(
        odds_api_event_id,
        bookmakers=odds_scraper.bookmaker_name,
        critical=False,
    )
    if isinstance(raw_payload, dict):
        parsed_odds, rejects = odds_scraper._parse_event_odds(raw_payload)
    else:
        parsed_odds, rejects = {}, {}

    match_id_after = _resolve_match_id(client, str(odds_api_event_id))
    if match_id_after and parsed_odds:
        match_status = "scheduled"
        try:
            match_row = (
                client.table("matches")
                .select("status")
                .eq("id", match_id_after)
                .single()
                .execute()
                .data
                or {}
            )
            match_status = str(match_row.get("status") or "scheduled")
        except Exception:
            match_status = "scheduled"
        for market, odd in parsed_odds.items():
            odds_scraper._upsert_odds_history(
                match_id=match_id_after,
                market=market,
                odd=odd,
                is_finished=match_status.lower() == "finished",
            )
            odds_scraper._upsert_odds_snapshot(match_id=match_id_after, market=market, odd=odd, ev=None)

    odds_rows_after = _count_odds_rows(client, match_id_after)
    markets_count = len(parsed_odds)

    return {
        "odds_api_event_id": odds_api_event_id,
        "match_id": match_id_after,
        "raw_received": raw_payload is not None,
        "markets_count": markets_count,
        "rejected": rejects,
        "odds_rows_before": odds_rows_before,
        "odds_rows_after": odds_rows_after,
        "saved_delta": odds_rows_after - odds_rows_before,
        "raw_json": raw_payload,
    }


@app.get("/test/sofascore-debug")
async def test_sofascore_debug() -> Dict[str, Any]:
    if not ENABLE_SOFASCORE_ENRICHMENT or sofascore is None:
        raise HTTPException(status_code=410, detail="Sofascore enrichment devre disi.")
    event_id = 14023997
    raw = await sofascore.get_event_detail(event_id, ttl_seconds=60)
    odds = await sofascore.get_event_odds(event_id)
    return {
        "event_id": event_id,
        "cookie_set": bool(os.getenv("SOFASCORE_COOKIE")),
        "proxy_enabled": bool(sofascore.proxy_pool.enabled),
        "proxy_pool_size": int(sofascore.proxy_pool.size),
        "event_ok": bool(raw),
        "odds_ok": bool(odds),
        "odds_market_count": len((odds or {}).keys()) if isinstance(odds, dict) else 0,
        "sample_event": raw,
    }


@app.get("/test/sofascore/{date}")
async def test_sofascore(date: str) -> Dict[str, Any]:
    if not ENABLE_SOFASCORE_ENRICHMENT or sofascore is None:
        raise HTTPException(status_code=410, detail="Sofascore enrichment devre disi.")

    events = await sofascore.get_scheduled_events(date)
    if events is None:
        return {"date": date, "count": 0, "leagues": {}, "fetch_failed": True}
    items = events
    leagues: Dict[str, int] = {}
    for event in items:
        tournament = event.get("tournament", {}) if isinstance(event.get("tournament"), dict) else {}
        unique_tournament = (
            tournament.get("uniqueTournament")
            if isinstance(tournament.get("uniqueTournament"), dict)
            else {}
        )
        league_name = str(unique_tournament.get("name") or tournament.get("name") or "Unknown")
        leagues[league_name] = leagues.get(league_name, 0) + 1
    return {
        "date": date,
        "count": len(items),
        "leagues": leagues,
        "fetch_failed": False,
    }


@app.get("/test/sofascore/top-players/{team_id}")
async def test_sofascore_top_players(
    team_id: int,
    tournament_id: Optional[int] = Query(default=None),
    season_id: Optional[int] = Query(default=None),
) -> Dict[str, Any]:
    if not ENABLE_SOFASCORE_ENRICHMENT or sofascore is None:
        raise HTTPException(status_code=410, detail="Sofascore enrichment devre disi.")
    parsed = await sofascore.get_team_top_players(
        team_id,
        limit=10,
        tournament_id=tournament_id,
        season_id=season_id,
    )
    raw_season_top = None
    raw_season_stats = None
    if (tournament_id or 0) > 0 and (season_id or 0) > 0:
        raw_season_top = await sofascore._request(
            f"/team/{team_id}/unique-tournament/{int(tournament_id or 0)}/season/{int(season_id or 0)}/top-players/overall",
            ttl_seconds=60,
        )
        raw_season_stats = await sofascore._request(
            f"/team/{team_id}/unique-tournament/{int(tournament_id or 0)}/season/{int(season_id or 0)}/statistics/overall",
            ttl_seconds=60,
        )
    raw_overall = await sofascore._request(f"/team/{team_id}/top-players/overall", ttl_seconds=60)
    raw_top = await sofascore._request(f"/team/{team_id}/top-players", ttl_seconds=60)
    raw_players = await sofascore._request(f"/team/{team_id}/players", ttl_seconds=60)
    return {
        "team_id": team_id,
        "tournament_id": tournament_id,
        "season_id": season_id,
        "parsed_count": len(parsed),
        "parsed": parsed,
        "raw_season_top": raw_season_top,
        "raw_season_stats": raw_season_stats,
        "raw_overall": raw_overall,
        "raw_top": raw_top,
        "raw_players": raw_players,
    }


@app.post("/analyze/{match_id}")
async def analyze_match_endpoint(
    match_id: str,
    body: AnalyzeRequest,
    refresh: bool = Query(default=True),
) -> Dict[str, Any]:
    return await _run_match_analysis(match_id, body.confidence_threshold, refresh_live=refresh)


@app.get("/matches/{match_id}/analysis")
async def get_match_analysis(
    match_id: str,
    confidence_threshold: float = Query(default=60.0, ge=0.0, le=100.0),
    refresh: bool = Query(default=False),
) -> Dict[str, Any]:
    return await _run_match_analysis(
        match_id,
        confidence_threshold,
        include_details=True,
        refresh_live=refresh,
    )


@app.get("/matches/{match_id}/odds")
async def get_match_odds(match_id: str, refresh: bool = Query(default=False)) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    resolved_match_id = _resolve_match_id(client, match_id)
    if not resolved_match_id:
        raise HTTPException(status_code=404, detail="Match not found.")

    live_odds: Dict[str, float] = {}
    if refresh:
        live_odds = await odds_scraper.get_odds_for_match(resolved_match_id)

    stored_odds = _fetch_odds(client, resolved_match_id)
    merged_odds = {**stored_odds, **live_odds}
    return {
        "match_id": resolved_match_id,
        "count": len(merged_odds),
        "odds": dict(sorted(merged_odds.items(), key=lambda item: item[0])),
        "refreshed": refresh,
    }


@app.post("/admin/refresh-odds")
async def admin_refresh_odds() -> Dict[str, Any]:
    await scheduler.sync_oddsapi_events()
    result = await scheduler.refresh_oddsapi_odds()
    return {"status": "ok", **result}


@app.post("/admin/sync/match/{match_id}/sofascore-cache")
async def admin_sync_match_sofascore_cache(
    match_id: str,
    force: bool = Query(default=False),
) -> Dict[str, Any]:
    if not ENABLE_SOFASCORE_ENRICHMENT or sofascore is None:
        raise HTTPException(status_code=410, detail="Sofascore enrichment devre disi.")

    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    resolved_match_id = _resolve_match_id(client, match_id)
    if not resolved_match_id:
        raise HTTPException(status_code=404, detail="Match not found.")
    result = await sofascore.sync_match_sofascore_bundle(resolved_match_id, force=force)
    return {"status": "ok", "match_id": resolved_match_id, **result}


@app.post("/admin/sync/logos")
async def admin_sync_team_logos(
    force: bool = Query(default=False),
    limit: int = Query(default=0, ge=0, le=2000),
) -> Dict[str, Any]:
    if not ENABLE_SOFASCORE_ENRICHMENT or sofascore is None:
        raise HTTPException(status_code=410, detail="Sofascore enrichment devre disi.")
    result = sofascore.refresh_team_logos(force=force, limit=limit)
    return {"status": "ok", **result}


@app.post("/admin/sync/teams/discover")
async def admin_discover_teams(
    scope: str = Query(default="tracked"),
    history_days: int = Query(default=30, ge=0, le=365),
    future_days: int = Query(default=1, ge=0, le=30),
    include_categories: bool = Query(default=True),
    include_history: bool = Query(default=True),
    category_limit: int = Query(default=0, ge=0, le=300),
    tournament_limit: int = Query(default=0, ge=0, le=5000),
) -> Dict[str, Any]:
    if not ENABLE_SOFASCORE_ENRICHMENT or sofascore is None:
        raise HTTPException(status_code=410, detail="Sofascore enrichment devre disi.")
    normalized_scope = str(scope or "tracked").strip().lower()
    if normalized_scope not in {"tracked", "global"}:
        raise HTTPException(status_code=400, detail="scope sadece 'tracked' veya 'global' olabilir.")
    result = await scheduler.discover_sofascore_teams(
        scope=normalized_scope,
        history_days=history_days,
        future_days=future_days,
        include_categories=include_categories,
        include_history=include_history,
        category_limit=category_limit,
        tournament_limit=tournament_limit,
    )
    return {"status": "ok", **result}


@app.post("/admin/sync/teams/profiles")
async def admin_sync_team_profiles(
    force: bool = Query(default=False),
    limit: int = Query(default=0, ge=0, le=2000),
) -> Dict[str, Any]:
    if not ENABLE_SOFASCORE_ENRICHMENT or sofascore is None:
        raise HTTPException(status_code=410, detail="Sofascore enrichment devre disi.")
    result = await scheduler.refresh_sofascore_team_profiles(force=force, limit=limit)
    return {"status": "ok", **result}


@app.post("/admin/sync/teams/profiles/backfill")
async def admin_start_team_profile_backfill(
    chunk_size: int = Query(default=200, ge=1, le=1000),
    max_chunks: int = Query(default=0, ge=0, le=1000),
    force: bool = Query(default=False),
) -> Dict[str, Any]:
    global team_profile_backfill_task
    if not ENABLE_SOFASCORE_ENRICHMENT or sofascore is None:
        raise HTTPException(status_code=410, detail="Sofascore enrichment devre disi.")
    if team_profile_backfill_task is not None and not team_profile_backfill_task.done():
        return {
            "status": "running",
            "message": "Team profile backfill zaten calisiyor",
            "state": team_profile_backfill_state,
        }

    team_profile_backfill_task = asyncio.create_task(
        _run_team_profile_backfill(
            chunk_size=int(chunk_size),
            max_chunks=int(max_chunks),
            force=bool(force),
        )
    )
    return {
        "status": "started",
        "message": "Team profile backfill arka planda basladi",
        "chunk_size": int(chunk_size),
        "max_chunks": int(max_chunks),
        "force": bool(force),
    }


@app.get("/admin/sync/teams/profiles/backfill/status")
async def admin_team_profile_backfill_status() -> Dict[str, Any]:
    running = team_profile_backfill_task is not None and not team_profile_backfill_task.done()
    return {
        "status": "ok",
        "backfill": {
            "status": team_profile_backfill_state.get("status"),
            "running": bool(team_profile_backfill_state.get("running")) or running,
            "started_at": team_profile_backfill_state.get("started_at"),
            "finished_at": team_profile_backfill_state.get("finished_at"),
            "chunk_size": team_profile_backfill_state.get("chunk_size"),
            "max_chunks": team_profile_backfill_state.get("max_chunks"),
            "force": team_profile_backfill_state.get("force"),
            "chunks_completed": team_profile_backfill_state.get("chunks_completed"),
            "processed": team_profile_backfill_state.get("processed"),
            "updated": team_profile_backfill_state.get("updated"),
            "failed": team_profile_backfill_state.get("failed"),
            "pending_remaining": team_profile_backfill_state.get("pending_remaining"),
            "last_result": team_profile_backfill_state.get("last_result"),
            "last_error": team_profile_backfill_state.get("last_error"),
        },
    }


@app.get("/admin/sync/teams/status")
async def admin_team_sync_status() -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    select_columns = "id,sofascore_id"
    for optional_column in ["logo_url", "coach_name", "profile_sync_status", "profile_last_fetched_at"]:
        try:
            client.table("teams").select(optional_column).limit(1).execute()
            select_columns += f",{optional_column}"
        except Exception:
            continue

    try:
        team_rows = (
            client.table("teams")
            .select(select_columns)
            .not_.is_("sofascore_id", "null")
            .limit(5000)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.exception("Team sync status query failed.")
        raise HTTPException(status_code=500, detail="Team sync status failed.") from exc

    total_teams = len(team_rows)
    missing_logo = 0
    missing_coach = 0
    stale_profiles = 0
    pending_profiles = 0
    for row in team_rows:
        if not str(row.get("logo_url") or "").strip():
            missing_logo += 1
        if row.get("coach_name") in (None, ""):
            missing_coach += 1
        if str(row.get("profile_sync_status") or "").strip().lower() in {"", "pending", "stale"}:
            pending_profiles += 1
        if _is_profile_stale(row.get("profile_last_fetched_at")):
            stale_profiles += 1

    cache_count = 0
    try:
        cache_result = client.table("team_profile_cache").select("id", count="exact").limit(1).execute()
        cache_count = int(cache_result.count or 0)
    except Exception:
        cache_count = 0

    return {
        "status": "ok",
        "total_teams": total_teams,
        "team_profile_cache_count": cache_count,
        "missing_logo_count": missing_logo,
        "missing_coach_count": missing_coach,
        "stale_profile_count": stale_profiles,
        "pending_profile_count": pending_profiles,
        "profile_backfill": {
            "status": team_profile_backfill_state.get("status"),
            "running": bool(team_profile_backfill_state.get("running")) or (team_profile_backfill_task is not None and not team_profile_backfill_task.done()),
            "chunk_size": team_profile_backfill_state.get("chunk_size"),
            "chunks_completed": team_profile_backfill_state.get("chunks_completed"),
            "processed": team_profile_backfill_state.get("processed"),
            "updated": team_profile_backfill_state.get("updated"),
            "failed": team_profile_backfill_state.get("failed"),
            "pending_remaining": team_profile_backfill_state.get("pending_remaining"),
        },
        "scheduler": scheduler.scheduler_status(),
    }


@app.get("/admin/sync/status")
async def admin_sync_status() -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    cache_counts: Dict[str, int] = {}
    for table_name in ["team_season_stats_cache", "team_top_players_cache", "league_standings_cache", "team_profile_cache"]:
        try:
            rows = client.table(table_name).select("id", count="exact").limit(1).execute()
            cache_counts[table_name] = int(rows.count or 0)
        except Exception:
            cache_counts[table_name] = 0

    stale_logo_count = 0
    try:
        stale_query = (
            client.table("teams")
            .select("id", count="exact")
            .or_("logo_url.is.null,logo_status.eq.pending")
            .not_.is_("sofascore_id", "null")
            .limit(1)
            .execute()
        )
        stale_logo_count = int(stale_query.count or 0)
    except Exception:
        stale_logo_count = 0

    return {
        "status": "ok",
        "sofascore_enrichment_enabled": bool(ENABLE_SOFASCORE_ENRICHMENT),
        "cache_counts": cache_counts,
        "stale_logo_count": stale_logo_count,
        "scheduler": scheduler.scheduler_status(),
    }


@app.post("/coupons")
async def create_coupon(body: CouponCreateRequest) -> Dict[str, Any]:
    if not body.selections:
        raise HTTPException(status_code=422, detail="Kupon secimleri bos olamaz.")
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    calculated_total = 1.0
    for selection in body.selections:
        calculated_total *= float(selection.odd)
    total_odds = round(float(body.total_odds or calculated_total), 3)
    status_value = body.status if body.status in {"pending", "won", "lost", "partial"} else "pending"

    payload = {
        "selections": [selection.model_dump() for selection in body.selections],
        "total_odds": total_odds,
        "status": status_value,
    }
    try:
        inserted = client.table("coupons").insert(payload).execute().data or []
    except Exception as exc:
        logger.exception("Coupon insert failed.")
        raise HTTPException(status_code=500, detail="Kupon kaydedilemedi.") from exc
    if not inserted:
        raise HTTPException(status_code=500, detail="Kupon kaydedilemedi.")
    return {
        "coupon_id": inserted[0].get("id"),
        "status": status_value,
        "total_odds": total_odds,
        "selections_count": len(body.selections),
    }


@app.get("/coupons")
async def list_coupons(limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        result = client.table("coupons").select("id,created_at,selections,total_odds,status").order("created_at", desc=True).limit(limit).execute()
    except Exception as exc:
        logger.exception("Coupons list failed.")
        raise HTTPException(status_code=500, detail="Kupon listesi alinamadi.") from exc
    rows = result.data or []
    return {"count": len(rows), "coupons": rows}


@app.get("/history")
async def get_history(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    market_type: Optional[str] = Query(default=None),
    correct: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        query = client.table("predictions").select(
            "id,match_id,market_type,predicted_outcome,confidence_score,ev_percentage,recommended,created_at"
        )
        if market_type:
            query = query.eq("market_type", market_type)
        if start_date:
            query = query.gte("created_at", f"{start_date}T00:00:00")
        if end_date:
            query = query.lte("created_at", f"{end_date}T23:59:59")
        predictions = query.order("created_at", desc=True).limit(limit).execute().data or []
    except Exception as exc:
        logger.exception("History predictions query failed.")
        raise HTTPException(status_code=500, detail="Gecmis tahminler alinamadi.") from exc

    prediction_ids = [row.get("id") for row in predictions if row.get("id")]
    match_ids = [row.get("match_id") for row in predictions if row.get("match_id")]

    results_map: Dict[str, Dict[str, Any]] = {}
    if prediction_ids:
        try:
            results = (
                client.table("results_tracker")
                .select("prediction_id,actual_outcome,was_correct,resolved_at")
                .in_("prediction_id", prediction_ids)
                .execute()
                .data
                or []
            )
            results_map = {row["prediction_id"]: row for row in results if row.get("prediction_id")}
        except Exception:
            logger.exception("results_tracker query failed.")

    matches_map: Dict[str, Dict[str, Any]] = {}
    teams_map: Dict[str, str] = {}
    if match_ids:
        try:
            matches = (
                client.table("matches")
                .select("id,match_date,home_team_id,away_team_id")
                .in_("id", match_ids)
                .execute()
                .data
                or []
            )
            matches_map = {row["id"]: row for row in matches if row.get("id")}
            team_ids = list(
                {
                    value
                    for row in matches
                    for value in [row.get("home_team_id"), row.get("away_team_id")]
                    if value
                }
            )
            if team_ids:
                teams = client.table("teams").select("id,name").in_("id", team_ids).execute().data or []
                teams_map = {row["id"]: str(row.get("name", "Takim")) for row in teams if row.get("id")}
        except Exception:
            logger.exception("history matches/teams query failed.")

    correct_filter = _parse_correct_filter(correct)
    items: List[Dict[str, Any]] = []
    for row in predictions:
        prediction_id = row.get("id")
        match_id = row.get("match_id")
        result_row = results_map.get(prediction_id, {})
        was_correct = result_row.get("was_correct")
        if correct_filter is not None and bool(was_correct) is not correct_filter:
            continue
        match_row = matches_map.get(match_id, {})
        home_team = teams_map.get(match_row.get("home_team_id"), "Ev Sahibi")
        away_team = teams_map.get(match_row.get("away_team_id"), "Deplasman")
        items.append(
            {
                "prediction_id": prediction_id,
                "date": row.get("created_at"),
                "match_date": match_row.get("match_date"),
                "match": f"{home_team} vs {away_team}",
                "market_type": row.get("market_type"),
                "predicted_outcome": row.get("predicted_outcome"),
                "actual_outcome": result_row.get("actual_outcome"),
                "was_correct": was_correct,
                "confidence_score": row.get("confidence_score"),
                "ev_percentage": row.get("ev_percentage"),
            }
        )

    resolved_items = [item for item in items if item.get("was_correct") is not None]
    correct_count = len([item for item in resolved_items if item.get("was_correct") is True])
    wrong_count = len([item for item in resolved_items if item.get("was_correct") is False])
    accuracy = round((correct_count / len(resolved_items)) * 100.0, 2) if resolved_items else 0.0

    weekly_start = (datetime.now(scheduler.timezone).date() - timedelta(days=7)).isoformat()
    try:
        weekly_rows = (
            client.table("results_tracker")
            .select("was_correct")
            .gte("resolved_at", f"{weekly_start}T00:00:00")
            .execute()
            .data
            or []
        )
    except Exception:
        weekly_rows = []
    weekly_correct = len([row for row in weekly_rows if row.get("was_correct") is True])
    weekly_total = len([row for row in weekly_rows if row.get("was_correct") is not None])
    weekly_accuracy = round((weekly_correct / weekly_total) * 100.0, 2) if weekly_total else 0.0

    coupons_total = 0
    try:
        coupons_result = client.table("coupons").select("id", count="exact").execute()
        coupons_total = int(coupons_result.count or 0)
    except Exception:
        coupons_total = 0

    return {
        "count": len(items),
        "items": items,
        "summary": {
            "total_predictions": len(items),
            "correct_predictions": correct_count,
            "wrong_predictions": wrong_count,
            "accuracy_percentage": accuracy,
            "weekly_accuracy_percentage": weekly_accuracy,
            "total_coupons": coupons_total,
        },
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "market_type": market_type,
            "correct": correct,
        },
    }


@app.get("/stats/performance")
async def get_performance_stats(
    lookback_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=5000, ge=100, le=10000),
) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    summary = await build_performance_summary(
        supabase=client,
        lookback_days=lookback_days,
        limit=limit,
    )
    return summary


@app.get("/stats/predictions")
async def get_prediction_stats(
    status: str = Query(default="all"),
    market: str = Query(default="all"),
    lookback_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=2000),
) -> Dict[str, Any]:
    normalized_status = str(status or "all").strip().lower()
    if normalized_status not in {"all", "pending", "evaluated"}:
        raise HTTPException(status_code=422, detail="status sadece all|pending|evaluated olabilir.")

    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    items = await list_prediction_results(
        supabase=client,
        status=normalized_status,
        market=market,
        lookback_days=lookback_days,
        limit=limit,
    )
    return {"count": len(items), "items": items}


@app.post("/stats/recalculate")
async def recalculate_prediction_stats(
    batch_size: int = Query(default=500, ge=10, le=2000),
    lookback_days: int = Query(default=30, ge=1, le=365),
) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    reconcile = await process_pending_predictions(
        supabase=client,
        batch_size=batch_size,
        lookback_days=lookback_days,
        timezone_name=getattr(scheduler.timezone, "key", "Europe/Istanbul"),
    )
    summary = await build_performance_summary(
        supabase=client,
        lookback_days=max(lookback_days, 30),
        limit=5000,
    )
    return {"status": "done", "reconcile": reconcile, "performance": summary}


@app.post("/admin/reconcile-results")
async def reconcile_results_now(
    batch_size: int = Query(default=500, ge=10, le=2000),
    lookback_days: int = Query(default=30, ge=1, le=365),
) -> Dict[str, Any]:
    return await recalculate_prediction_stats(batch_size=batch_size, lookback_days=lookback_days)


@app.post("/tasks/fetch-today")
async def trigger_fetch_today() -> Dict[str, Any]:
    today = datetime.now(scheduler.timezone).date().isoformat()
    result = await scheduler.fetch_specific_dates([today])
    return {"status": "ok", "date": today, "result": result}


@app.post("/tasks/update-stats")
async def trigger_update_stats() -> Dict[str, Any]:
    weekly = await scheduler.update_weekly_team_stats()
    daily_stats: Dict[str, Any] = {"processed_matches": 0, "updated_teams": 0, "skipped": True}
    injuries_h2h: Dict[str, Any] = {"processed_matches": 0, "injury_rows": 0, "h2h_rows": 0, "skipped": True}
    if ENABLE_SOFASCORE_ENRICHMENT and sofascore is not None:
        daily_stats = await scheduler.populate_today_team_stats_history()
        injuries_h2h = await scheduler.refresh_today_injuries_and_h2h()
    events_sync = await scheduler.sync_oddsapi_events()
    odds_refresh = await scheduler.refresh_oddsapi_odds()
    reconcile = await scheduler.reconcile_oddsapi_results()
    pi_refresh = await scheduler.refresh_pi_ratings()
    return {
        "status": "ok",
        "weekly": weekly,
        "daily_team_stats": daily_stats,
        "injuries_h2h": injuries_h2h,
        "oddsapi_events_sync": events_sync,
        "odds_refresh": odds_refresh,
        "odds_results_reconcile": reconcile,
        "pi_rating": {
            "processed_matches": pi_refresh.get("processed_matches", 0),
            "updated_teams": pi_refresh.get("updated_teams", 0),
        },
    }


@app.post("/settings")
async def update_settings(_: SettingsUpdateRequest) -> Dict[str, Any]:
    # This endpoint stores no persistent settings yet; frontend keeps local profile.
    return {"status": "ok"}


def _repair_mojibake_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "Ã" not in text and "Ä" not in text:
        return text
    for encoding in ("latin1", "cp1254", "cp1252"):
        try:
            repaired = text.encode(encoding, errors="ignore").decode("utf-8", errors="ignore").strip()
        except Exception:
            continue
        if repaired and repaired != text:
            return repaired
    return text


def _normalize_team_directory_value(value: Any) -> str:
    repaired = _repair_mojibake_text(value).strip().lower()
    normalized = unicodedata.normalize("NFKD", repaired)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    compact = re.sub(r"[^a-z0-9]+", "", ascii_only)
    aliases = {
        "turkey": "turkiye",
        "turkiye": "turkiye",
        "turkiyecumhuriyeti": "turkiye",
        "superlig": "superlig",
    }
    return aliases.get(compact, compact)


def _canonical_country_label(value: Any) -> str:
    repaired = _repair_mojibake_text(value)
    if _normalize_team_directory_value(repaired) == "turkiye":
        return "Türkiye"
    return repaired


@app.get("/teams")
async def list_teams(
    league: Optional[str] = Query(default=None),
    country: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=5000),
) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    select_columns = "id,name,league,country,sofascore_id"
    for optional_column in [
        "logo_url",
        "coach_name",
        "coach_sofascore_id",
        "sofascore_team_url",
        "profile_sync_status",
        "profile_last_fetched_at",
        "slug",
    ]:
        try:
            client.table("teams").select(optional_column).limit(1).execute()
            select_columns += f",{optional_column}"
        except Exception:
            continue

    try:
        query = client.table("teams").select(select_columns, count="exact")
        try:
            query = query.not_.is_("sofascore_id", "null")
        except Exception:
            pass
        result = (
            query.order("league")
            .order("name")
            .range(0, 9999)
            .execute()
        )
    except Exception as exc:
        logger.exception("Teams list query failed.")
        raise HTTPException(status_code=500, detail="Teams list failed.") from exc

    rows = result.data or []
    team_ids = [str(row.get("id") or "") for row in rows if row.get("id")]
    cache_map = _load_team_profile_cache_map(client, team_ids)

    items: List[Dict[str, Any]] = []
    for row in rows:
        team_id = str(row.get("id") or "")
        cache_row = cache_map.get(team_id, {})
        items.append(
            {
                "id": team_id,
                "name": _repair_mojibake_text(row.get("name") or cache_row.get("team_name") or ""),
                "league": _repair_mojibake_text(row.get("league") or ""),
                "country": _canonical_country_label(row.get("country") or cache_row.get("country") or ""),
                "logo_url": row.get("logo_url") or cache_row.get("logo_url"),
                "coach_name": _repair_mojibake_text(row.get("coach_name") or cache_row.get("coach_name")),
                "sofascore_id": row.get("sofascore_id"),
                "coach_sofascore_id": row.get("coach_sofascore_id") or cache_row.get("coach_sofascore_id"),
                "sofascore_team_url": row.get("sofascore_team_url") or cache_row.get("sofascore_url"),
                "profile_sync_status": row.get("profile_sync_status") or ("ready" if cache_row else "pending"),
                "profile_last_fetched_at": row.get("profile_last_fetched_at") or cache_row.get("updated_at"),
            }
        )

    normalized_league = _normalize_team_directory_value(league)
    normalized_country = _normalize_team_directory_value(country)
    normalized_query = _normalize_team_directory_value(q)

    filtered_items = [
        item
        for item in items
        if (
            not normalized_league
            or normalized_league in _normalize_team_directory_value(item.get("league"))
        )
        and (
            not normalized_country
            or normalized_country == _normalize_team_directory_value(item.get("country"))
        )
        and (
            not normalized_query
            or normalized_query in _normalize_team_directory_value(item.get("name"))
        )
    ]

    paged_items = filtered_items[offset : offset + limit]

    return {
        "count": len(filtered_items),
        "items": paged_items,
    }


@app.get("/teams/{team_id}/logo")
async def get_team_logo(team_id: str) -> Response:
    if not ENABLE_SOFASCORE_ENRICHMENT or sofascore is None:
        raise HTTPException(status_code=410, detail="Sofascore enrichment devre disi.")
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    team_row: Dict[str, Any] = {}
    try:
        team_row = (
            client.table("teams")
            .select("id,sofascore_id")
            .eq("id", team_id)
            .limit(1)
            .execute()
            .data
            or [{}]
        )[0]
    except Exception:
        team_row = {}

    sofascore_team_id = int(team_row.get("sofascore_id", 0) or 0)
    if sofascore_team_id <= 0:
        raise HTTPException(status_code=404, detail="Team logo not found.")

    asset = await sofascore.get_team_logo_asset(sofascore_team_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Team logo fetch failed.")

    content, content_type = asset
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"},
    )


@app.get("/matches/today")
async def list_todays_matches(min_confidence: float = Query(default=60, ge=0, le=100)) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    today = datetime.now(scheduler.timezone).date().isoformat()
    tomorrow = (datetime.now(scheduler.timezone).date() + timedelta(days=1)).isoformat()
    try:
        try:
            result = (
                client.table("matches")
                .select("id,league,match_date,status,home_team_id,away_team_id,confidence_score,best_bet")
                .gte("match_date", f"{today}T00:00:00")
                .lte("match_date", f"{tomorrow}T23:59:59")
                .order("match_date")
                .execute()
            )
        except Exception:
            result = (
                client.table("matches")
                .select("id,league,match_date,status,home_team_id,away_team_id")
                .gte("match_date", f"{today}T00:00:00")
                .lte("match_date", f"{tomorrow}T23:59:59")
                .order("match_date")
                .execute()
            )
    except Exception as exc:
        logger.exception("matches/today query failed.")
        raise HTTPException(status_code=500, detail="Failed to list matches.") from exc

    rows = result.data or []
    team_ids = list({value for row in rows for value in [row.get("home_team_id"), row.get("away_team_id")] if value})
    teams_map: Dict[str, Dict[str, Any]] = {}
    if team_ids:
        try:
            try:
                teams = client.table("teams").select("id,name,logo_url").in_("id", team_ids).execute().data or []
            except Exception:
                teams = client.table("teams").select("id,name").in_("id", team_ids).execute().data or []
            teams_map = {row["id"]: row for row in teams if row.get("id")}
        except Exception:
            logger.exception("teams map read failed.")

    prediction_map: Dict[str, Dict[str, Any]] = {}
    match_ids = [str(row.get("id") or "") for row in rows if row.get("id")]
    if match_ids:
        try:
            prediction_rows = (
                client.table("predictions")
                .select("match_id,market_type,confidence_score,ev_percentage,recommended,created_at")
                .in_("match_id", match_ids)
                .order("created_at", desc=True)
                .limit(5000)
                .execute()
                .data
                or []
            )
            for row in prediction_rows:
                match_id = str(row.get("match_id") or "").strip()
                if match_id and match_id not in prediction_map:
                    prediction_map[match_id] = row
        except Exception:
            logger.exception("predictions map read failed.")

    items: List[Dict[str, Any]] = []
    for row in rows:
        match_id = str(row.get("id") or "")
        prediction = prediction_map.get(match_id, {})
        confidence_score = float(
            prediction.get("confidence_score")
            if prediction.get("confidence_score") is not None
            else row.get("confidence_score", 0.0) or 0.0
        )
        market_type = str(
            prediction.get("market_type")
            or row.get("best_bet")
            or "MS1"
        )
        ev_percentage = float(prediction.get("ev_percentage", 0.0) or 0.0)
        recommended_flag = bool(prediction.get("recommended", False)) and confidence_score >= float(min_confidence)
        items.append(
            {
                "match_id": row["id"],
                "league": row["league"],
                "match_date": row["match_date"],
                "status": row["status"],
                "home_team": str((teams_map.get(row["home_team_id"], {}) or {}).get("name", "Home Team")),
                "away_team": str((teams_map.get(row["away_team_id"], {}) or {}).get("name", "Away Team")),
                "home_logo_url": (teams_map.get(row["home_team_id"], {}) or {}).get("logo_url"),
                "away_logo_url": (teams_map.get(row["away_team_id"], {}) or {}).get("logo_url"),
                "confidence_score": round(confidence_score, 2),
                "recommended": recommended_flag,
                "market_type": market_type,
                "ev_percentage": ev_percentage,
            }
        )

    return {"count": len(items), "tracked_leagues": len(TRACKED_LEAGUE_IDS), "matches": items}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
