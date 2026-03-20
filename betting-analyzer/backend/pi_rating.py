from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

from supabase import Client

logger = logging.getLogger("pi_rating")

INITIAL_RATING = 1500.0
K_FACTOR = 0.1


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def expected_score(home_rating: float, away_rating: float) -> float:
    return 1.0 / (1.0 + 10 ** ((away_rating - home_rating) / 400.0))


def _has_column(supabase: Client, table_name: str, column_name: str) -> bool:
    try:
        supabase.table(table_name).select(column_name).limit(1).execute()
        return True
    except Exception:
        return False


def calculate_pi_ratings(
    matches: Iterable[Dict[str, Any]],
    *,
    initial_rating: float = INITIAL_RATING,
    k_factor: float = K_FACTOR,
) -> Dict[str, float]:
    ratings: Dict[str, float] = {}

    for row in matches:
        home_team = str(row.get("home_team_id") or "")
        away_team = str(row.get("away_team_id") or "")
        if not home_team or not away_team:
            continue

        ft_home = _safe_int(row.get("ft_home"), fallback=-999)
        ft_away = _safe_int(row.get("ft_away"), fallback=-999)
        if ft_home == -999 or ft_away == -999:
            continue

        home_rating = ratings.get(home_team, initial_rating)
        away_rating = ratings.get(away_team, initial_rating)
        home_expected = expected_score(home_rating, away_rating)
        away_expected = 1.0 - home_expected

        if ft_home > ft_away:
            home_actual = 1.0
            away_actual = 0.0
        elif ft_home < ft_away:
            home_actual = 0.0
            away_actual = 1.0
        else:
            home_actual = 0.5
            away_actual = 0.5

        home_new = home_rating + (k_factor * (home_actual - home_expected))
        away_new = away_rating + (k_factor * (away_actual - away_expected))
        ratings[home_team] = round(home_new, 2)
        ratings[away_team] = round(away_new, 2)

    return ratings


def update_team_pi_ratings(supabase: Client) -> Dict[str, Any]:
    try:
        result = (
            supabase.table("matches")
            .select("home_team_id,away_team_id,ft_home,ft_away,status,match_date")
            .eq("status", "finished")
            .not_.is_("ft_home", "null")
            .not_.is_("ft_away", "null")
            .order("match_date")
            .execute()
        )
    except Exception:
        logger.exception("Finished matches could not be loaded for pi-rating.")
        return {"processed_matches": 0, "updated_teams": 0}

    matches: List[Dict[str, Any]] = result.data or []
    ratings = calculate_pi_ratings(matches)
    if not _has_column(supabase, "teams", "pi_rating"):
        logger.warning("teams.pi_rating kolonu yok, sadece runtime ratings hesaplandi.")
        return {"processed_matches": len(matches), "updated_teams": 0, "ratings": ratings}

    updated = 0
    for team_id, rating in ratings.items():
        try:
            supabase.table("teams").update({"pi_rating": rating}).eq("id", team_id).execute()
            updated += 1
        except Exception:
            logger.exception("pi_rating update failed. team_id=%s", team_id)

    logger.info("Pi-rating guncellendi. mac=%s takim=%s", len(matches), updated)
    return {"processed_matches": len(matches), "updated_teams": updated, "ratings": ratings}
