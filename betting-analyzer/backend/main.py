from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import Client, create_client

from analyzer import analyze_match
from api_football import get_service as get_api_service
from config import TRACKED_LEAGUE_IDS
from ev_calculator import SUPPORTED_MARKETS, evaluate_markets
from pi_rating import calculate_pi_ratings
from proxy_pool import ProxyPool, mask_proxy
from scheduler import BettingScheduler
from services.odds_scraper import get_service as get_odds_scraper_service
from sofascore import get_service as get_sofascore_service, stable_uuid
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
sofascore = get_sofascore_service()
transfermarkt_service = get_transfermarkt_service()
weather_service = get_weather_service()
backfill_task: Optional[asyncio.Task[Any]] = None
backfill_state: Dict[str, Any] = {
    "status": "idle",
    "running": False,
    "started_at": None,
    "finished_at": None,
    "last_result": None,
    "last_error": None,
}


@asynccontextmanager
async def lifespan(_: FastAPI):
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

        sofascore_total = 0
        sofascore_by_date: Dict[str, int] = {}
        for date_str in [now.isoformat(), (now + timedelta(days=1)).isoformat()]:
            rows = await sofascore.get_scheduled_events(date_str)
            count = len(rows or [])
            sofascore_total += count
            sofascore_by_date[date_str] = count

        daily_stats_result = await scheduler.populate_today_team_stats_history()
        odds_refresh_result = await scheduler.refresh_sofascore_odds()
        weekly_stats_result = await scheduler.update_weekly_team_stats()
        pi_rating_result = await scheduler.refresh_pi_ratings()

        result_payload = {
            "fixtures": fixtures_result,
            "sofascore": {"total_saved": sofascore_total, "by_date": sofascore_by_date},
            "daily_team_stats": daily_stats_result,
            "odds_refresh": odds_refresh_result,
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
        "id,api_match_id,sofascore_id,home_team_id,away_team_id,league,match_date,status,season,ht_home,ht_away,ft_home,ft_away"
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
    full_select = "id,name,market_value,api_team_id,pi_rating,country,sofascore_id"
    fallback_select = "id,name,market_value,api_team_id,country"
    try:
        try:
            result = client.table("teams").select(full_select).in_("id", [home_team_id, away_team_id]).execute()
        except Exception:
            result = client.table("teams").select(fallback_select).in_("id", [home_team_id, away_team_id]).execute()
        return {row["id"]: row for row in (result.data or []) if row.get("id")}
    except Exception:
        logger.exception("Team rows read failed.")
        return {}


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


def _resolve_sofascore_match_id(client: Client, sofascore_event_id: int) -> Optional[str]:
    try:
        by_sofascore = (
            client.table("matches")
            .select("id")
            .eq("sofascore_id", sofascore_event_id)
            .limit(1)
            .execute()
        )
        if by_sofascore.data:
            return by_sofascore.data[0].get("id")
    except Exception:
        pass

    fallback_match_id = stable_uuid("sofascore-event", sofascore_event_id)
    try:
        by_id = (
            client.table("matches")
            .select("id")
            .eq("id", fallback_match_id)
            .limit(1)
            .execute()
        )
        if by_id.data:
            return by_id.data[0].get("id")
    except Exception:
        return None
    return None


def _count_odds_rows(client: Client, match_id: Optional[str]) -> int:
    if not match_id:
        return 0
    try:
        result = (
            client.table("odds_history")
            .select("id", count="exact")
            .eq("match_id", match_id)
            .eq("bookmaker", "sofascore")
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


def _fetch_odds(client: Client, match_id: str) -> Dict[str, float]:
    try:
        odds_result = (
            client.table("odds_history")
            .select("market_type,current_odd,closing_odd,opening_odd,recorded_at")
            .eq("match_id", match_id)
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
    return mapped


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
                token in str(row.get("reason", "")).lower()
                for token in ["susp", "ceza", "kirmizi", "yellow suspension"]
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

    return {
        "form_points_last6": max(0.0, min(18.0, home_form * 18.0)),
        "xg_diff_last6": (home_xg_for - home_xg_against) - (away_xg_for - away_xg_against),
        "missing_players": float(missing_players),
        "key_absences": float(key_absences),
        "xg_rolling_diff_10": home_xg_for - away_xg_for,
        "market_value_delta_pct": market_value_delta_pct,
        "opening_odd": odds.get("MS1"),
        "closing_odd": odds.get("MS1"),
        "h2h_points_ratio": h2h_ratio,
        "h2h_ratio": h2h_ratio,
        "h2h_summary": h2h_summary or {"ratio": h2h_ratio},
        "h2h_matches": [
            {
                "home_goals": row.get("goals", {}).get("home", 0) if isinstance(row.get("goals"), dict) else 0,
                "away_goals": row.get("goals", {}).get("away", 0) if isinstance(row.get("goals"), dict) else 0,
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


def _build_market_probabilities(confidence_score: float, context: Dict[str, Any]) -> Dict[str, float]:
    base_prob = max(0.2, min(0.75, confidence_score / 100.0))
    draw_prob = max(0.1, min(0.35, 1.0 - base_prob))
    away_prob = max(0.1, 1.0 - (base_prob + draw_prob))
    over25 = max(0.2, min(0.8, 0.5 + (float(context.get("xg_diff_last6", 0.0)) / 10.0)))
    btts_yes = max(0.2, min(0.8, 0.45 + (float(context.get("xg_rolling_diff_10", 0.0)) / 8.0)))

    probabilities = {
        "MS1": base_prob,
        "MSX": draw_prob,
        "MS2": away_prob,
        "IY1": max(0.15, base_prob - 0.1),
        "IYX": max(0.15, draw_prob),
        "IY2": max(0.1, away_prob - 0.05),
        "MS_O2.5": over25,
        "MS_U2.5": 1.0 - over25,
        "KG_VAR": btts_yes,
        "KG_YOK": 1.0 - btts_yes,
        "HCP_-1": max(0.1, base_prob - 0.12),
        "HCP_-1.5": max(0.05, base_prob - 0.18),
        "HCP_+1": max(0.3, 1.0 - away_prob),
        "HCP_+1.5": max(0.35, 1.0 - away_prob + 0.05),
    }
    for line in ["0.5", "1.5", "2.5", "3.5"]:
        over_key_ft = f"MS_O{line}"
        under_key_ft = f"MS_U{line}"
        over_key_ht = f"IY_O{line}"
        under_key_ht = f"IY_U{line}"
        if over_key_ft not in probabilities:
            base = max(0.15, min(0.85, over25 - (float(line) - 2.5) * 0.12))
            probabilities[over_key_ft] = base
            probabilities[under_key_ft] = 1.0 - base
        ht_base = max(0.1, min(0.8, probabilities[over_key_ft] - 0.18))
        probabilities[over_key_ht] = ht_base
        probabilities[under_key_ht] = 1.0 - ht_base
    return {market: probabilities.get(market, 0.5) for market in SUPPORTED_MARKETS}


def _save_predictions(client: Client, match_id: str, ev_result: Dict[str, Any]) -> None:
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
    }
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
    injuries = []
    h2h_rows: List[Dict[str, Any]] = []
    h2h_summary: Optional[Dict[str, Any]] = None
    if api_match_id > 0:
        await api_football.get_odds(api_match_id)
        await api_football.get_predictions(api_match_id)
        injuries = await api_football.get_injuries(api_match_id) or []

        home_api_id = int(team_rows.get(match_row["home_team_id"], {}).get("api_team_id", 0) or 0)
        away_api_id = int(team_rows.get(match_row["away_team_id"], {}).get("api_team_id", 0) or 0)
        if home_api_id > 0 and away_api_id > 0:
            h2h_rows = await api_football.get_head_to_head(home_api_id, away_api_id) or []
            h2h_summary = {"ratio": _h2h_points_ratio(h2h_rows, home_api_id)}

    if sofascore_match_id > 0:
        sofa_h2h = await sofascore.get_h2h(sofascore_match_id)
        if isinstance(sofa_h2h, dict) and sofa_h2h.get("ratio") is not None:
            h2h_summary = sofa_h2h
    else:
        mapping = await sofascore._resolve_sofascore_team_ids_for_match(resolved_match_id)
        sofascore_match_id = int(mapping.get("event_id", 0) or 0) if isinstance(mapping, dict) else 0
        if sofascore_match_id > 0:
            sofa_h2h = await sofascore.get_h2h(sofascore_match_id)
            if isinstance(sofa_h2h, dict) and sofa_h2h.get("ratio") is not None:
                h2h_summary = sofa_h2h

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

    live_odds = await odds_scraper.get_odds_for_match(resolved_match_id)
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
    analysis = analyze_match(context, confidence_threshold=confidence_threshold)

    probabilities = _build_market_probabilities(analysis["confidence_score"], context)
    odd_map = {
        market: float(odd)
        for market, odd in odds.items()
        if market in SUPPORTED_MARKETS and float(odd) > 0
    }
    ev_result = evaluate_markets(
        market_probabilities=probabilities,
        market_odds=odd_map,
        confidence_score=analysis["confidence_score"],
        confidence_threshold=confidence_threshold,
    )
    _save_predictions(client, resolved_match_id, ev_result)
    odds_scraper.save_ev_rows(match_id=resolved_match_id, ev_result=ev_result)
    payload: Dict[str, Any] = {
        "match_id": resolved_match_id,
        "analysis": analysis,
        "ev": ev_result,
        "recommended_market": ev_result.get("best_market"),
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
            },
            "away_team": {
                "id": match_row.get("away_team_id"),
                "name": away_team.get("name", "Deplasman"),
                "country": away_team.get("country"),
            },
        }
        payload["form"] = {
            "home": _team_form_sequence(home_stats, limit=6),
            "away": _team_form_sequence(away_stats, limit=6),
        }
        payload["injuries"] = injuries
        payload["h2h"] = {
            "summary": h2h_summary or {"ratio": context.get("h2h_ratio", 0.5)},
            "last5": (h2h_rows or [])[:5],
        }
        payload["xg"] = {
            "home": round(sum(float(row.get("xg_for", 0) or 0) for row in home_stats[:10]) / max(1, len(home_stats[:10])), 3)
            if home_stats
            else 0.0,
            "away": round(sum(float(row.get("xg_for", 0) or 0) for row in away_stats[:10]) / max(1, len(away_stats[:10])), 3)
            if away_stats
            else 0.0,
        }
        payload["context"] = context
        payload["market_odds"] = odd_map
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
        "the_odds_remaining": scheduler.odds_tracker.requests_remaining,
        "api_keys": {
            "api_football": bool(os.getenv("API_FOOTBALL_KEY")),
            "the_odds": bool(os.getenv("THE_ODDS_API_KEY")),
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


@app.get("/test/fetch-today")
async def test_fetch_today() -> Dict[str, Any]:
    today = datetime.now(scheduler.timezone).date().isoformat()
    result = await scheduler.fetch_specific_dates([today])
    return {"date": today, "fetched_matches": result["total_saved"], "by_date": result["by_date"]}


@app.get("/test/analyze/{match_id}")
async def test_analyze(
    match_id: str,
    confidence_threshold: float = Query(default=60.0, ge=0.0, le=100.0),
) -> Dict[str, Any]:
    return await _run_match_analysis(match_id, confidence_threshold)


@app.get("/test/populate-stats/{match_id}")
async def test_populate_stats(match_id: str) -> Dict[str, Any]:
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


@app.get("/test/odds/{sofascore_event_id}")
async def test_sofascore_odds(sofascore_event_id: int) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    match_id_before = _resolve_sofascore_match_id(client, sofascore_event_id)
    odds_rows_before = _count_odds_rows(client, match_id_before)
    raw_payload = await sofascore.get_event_odds(sofascore_event_id)
    match_id_after = _resolve_sofascore_match_id(client, sofascore_event_id)
    odds_rows_after = _count_odds_rows(client, match_id_after)

    markets_count = 0
    if isinstance(raw_payload, dict) and isinstance(raw_payload.get("markets"), list):
        markets_count = len(raw_payload["markets"])

    return {
        "sofascore_event_id": sofascore_event_id,
        "match_id": match_id_after,
        "raw_received": raw_payload is not None,
        "markets_count": markets_count,
        "odds_rows_before": odds_rows_before,
        "odds_rows_after": odds_rows_after,
        "saved_delta": odds_rows_after - odds_rows_before,
        "raw_json": raw_payload,
    }


@app.get("/test/sofascore-debug")
async def test_sofascore_debug() -> Dict[str, Any]:
    cookie = os.getenv("SOFASCORE_COOKIE", "")
    proxy_pool = ProxyPool.from_env()
    proxy = proxy_pool.next()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.sofascore.com/",
        "Accept": "application/json",
    }
    if cookie:
        headers["Cookie"] = cookie

    try:
        async with httpx.AsyncClient(timeout=10.0, proxy=proxy) as client:
            response = await client.get(
                "https://www.sofascore.com/api/v1/event/13981717/odds/1/all",
                headers=headers,
            )
            return {
                "cookie_set": bool(cookie),
                "cookie_length": len(cookie),
                "proxy_enabled": proxy_pool.enabled,
                "proxy_pool_size": proxy_pool.size,
                "proxy_used": mask_proxy(proxy),
                "http_status": response.status_code,
                "response_size": len(response.text),
                "response_preview": response.text[:300],
            }
    except Exception as exc:
        return {
            "error": str(exc),
            "cookie_set": bool(cookie),
            "proxy_enabled": proxy_pool.enabled,
            "proxy_pool_size": proxy_pool.size,
            "proxy_used": mask_proxy(proxy),
        }


@app.get("/test/sofascore/{date}")
async def test_sofascore(date: str) -> Dict[str, Any]:
    events = await sofascore.get_scheduled_events(date)
    if events is None:
        return {"date": date, "count": 0, "leagues": {}, "fetch_failed": True}
    items = events
    leagues: Dict[str, int] = {}
    for event in items:
        tournament = event.get("tournament", {}) if isinstance(event.get("tournament"), dict) else {}
        unique_tournament = tournament.get("uniqueTournament", {}) if isinstance(tournament.get("uniqueTournament"), dict) else {}
        league_name = str(unique_tournament.get("name") or tournament.get("name") or "Unknown")
        leagues[league_name] = leagues.get(league_name, 0) + 1
    return {
        "date": date,
        "count": len(items),
        "leagues": leagues,
        "fetch_failed": False,
    }


@app.post("/analyze/{match_id}")
async def analyze_match_endpoint(match_id: str, body: AnalyzeRequest) -> Dict[str, Any]:
    return await _run_match_analysis(match_id, body.confidence_threshold)


@app.get("/matches/{match_id}/analysis")
async def get_match_analysis(
    match_id: str,
    confidence_threshold: float = Query(default=60.0, ge=0.0, le=100.0),
) -> Dict[str, Any]:
    return await _run_match_analysis(match_id, confidence_threshold, include_details=True)


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
    result = await scheduler.refresh_sofascore_odds()
    return {"status": "ok", **result}


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


@app.post("/tasks/fetch-today")
async def trigger_fetch_today() -> Dict[str, Any]:
    today = datetime.now(scheduler.timezone).date().isoformat()
    result = await scheduler.fetch_specific_dates([today])
    return {"status": "ok", "date": today, "result": result}


@app.post("/tasks/update-stats")
async def trigger_update_stats() -> Dict[str, Any]:
    weekly = await scheduler.update_weekly_team_stats()
    daily_stats = await scheduler.populate_today_team_stats_history()
    pi_refresh = await scheduler.refresh_pi_ratings()
    return {
        "status": "ok",
        "weekly": weekly,
        "daily_team_stats": daily_stats,
        "pi_rating": {
            "processed_matches": pi_refresh.get("processed_matches", 0),
            "updated_teams": pi_refresh.get("updated_teams", 0),
        },
    }


@app.post("/settings")
async def update_settings(_: SettingsUpdateRequest) -> Dict[str, Any]:
    # This endpoint stores no persistent settings yet; frontend keeps local profile.
    return {"status": "ok"}


@app.get("/matches/today")
async def list_todays_matches(min_confidence: float = Query(default=60, ge=0, le=100)) -> Dict[str, Any]:
    try:
        client = get_supabase_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    today = datetime.now(scheduler.timezone).date().isoformat()
    tomorrow = (datetime.now(scheduler.timezone).date() + timedelta(days=1)).isoformat()
    try:
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
    teams_map: Dict[str, str] = {}
    if team_ids:
        try:
            teams = client.table("teams").select("id,name").in_("id", team_ids).execute().data or []
            teams_map = {row["id"]: row.get("name", "Unknown Team") for row in teams}
        except Exception:
            logger.exception("teams map read failed.")

    items: List[Dict[str, Any]] = []
    for row in rows:
        odds = _fetch_odds(client, str(row["id"]))
        context = {
            "form_points_last6": 9.0,
            "xg_diff_last6": 0.0,
            "missing_players": 0.0,
            "key_absences": 0.0,
            "xg_rolling_diff_10": 0.0,
            "market_value_delta_pct": 0.0,
            "opening_odd": odds.get("MS1"),
            "closing_odd": odds.get("MS1"),
            "h2h_points_ratio": 0.5,
            "h2h_matches": [],
            "standing_pressure": 0.5,
            "competition_type": "league",
            "competition_stage": "regular",
            "social_sentiment_score": 0.0,
            "weather_impact_score": 0.0,
            "pi_rating_delta": 0.0,
        }
        analysis = analyze_match(context, confidence_threshold=min_confidence)
        probabilities = _build_market_probabilities(analysis["confidence_score"], context)
        market_odds = {
            market: float(odd)
            for market, odd in odds.items()
            if market in SUPPORTED_MARKETS and float(odd) > 0
        }
        ev = evaluate_markets(
            market_probabilities=probabilities,
            market_odds=market_odds,
            confidence_score=analysis["confidence_score"],
            confidence_threshold=min_confidence,
        )
        best_market = ev.get("best_market") or {}
        recommended_flag = bool(best_market.get("recommended", ev.get("recommended", False)))
        items.append(
            {
                "match_id": row["id"],
                "league": row["league"],
                "match_date": row["match_date"],
                "status": row["status"],
                "home_team": teams_map.get(row["home_team_id"], "Home Team"),
                "away_team": teams_map.get(row["away_team_id"], "Away Team"),
                "confidence_score": analysis["confidence_score"],
                "recommended": recommended_flag,
                "market_type": best_market.get("market_type", "MS1"),
                "ev_percentage": best_market.get("ev_percentage", 0.0),
            }
        )

    return {"count": len(items), "tracked_leagues": len(TRACKED_LEAGUE_IDS), "matches": items}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
