from __future__ import annotations

import logging
import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from supabase import Client

from team_comparison.models import TeamComparisonRequest

logger = logging.getLogger(__name__)


class TeamComparisonDataService:
    def __init__(self, supabase: Client) -> None:
        self.supabase = supabase

    @staticmethod
    def _repair_text(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if "\\u" in text:
            try:
                text = text.encode("utf-8").decode("unicode_escape")
            except Exception:
                pass
        if any(token in text for token in ("Ã", "Ä", "Å", "Ð", "Þ")):
            try:
                text = text.encode("latin1").decode("utf-8")
            except Exception:
                pass
        return text.strip()

    @classmethod
    def _normalize_name(cls, value: Any) -> str:
        repaired = cls._repair_text(value).lower()
        normalized = unicodedata.normalize("NFKD", repaired)
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", "", ascii_only)

    @staticmethod
    def _safe_int(value: Any, fallback: int = 0) -> int:
        try:
            if value is None:
                return fallback
            return int(float(value))
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _safe_float(value: Any, fallback: float = 0.0) -> float:
        try:
            if value is None:
                return fallback
            if isinstance(value, str):
                cleaned = value.strip().replace("%", "")
                if "/" in cleaned:
                    left, *_ = cleaned.split("/", 1)
                    cleaned = left
                cleaned = cleaned.replace(",", ".")
                if not cleaned:
                    return fallback
                return float(cleaned)
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _fetch_single(self, table: str, select_columns: str, field: str, value: Any) -> Dict[str, Any]:
        try:
            rows = (
                self.supabase.table(table)
                .select(select_columns)
                .eq(field, value)
                .limit(1)
                .execute()
                .data
                or []
            )
            return rows[0] if rows else {}
        except Exception:
            logger.exception("%s single fetch failed. %s=%s", table, field, value)
            return {}

    def _fetch_many(self, table: str, select_columns: str, field: str, value: Any, *, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            return (
                self.supabase.table(table)
                .select(select_columns)
                .eq(field, value)
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("%s list fetch failed. %s=%s", table, field, value)
            return []

    def _fetch_team(self, team_id: str) -> Dict[str, Any]:
        return self._fetch_single(
            "teams",
            "id,name,league,country,market_value,sofascore_id,logo_url,coach_name,profile_last_fetched_at,team_data_last_fetched_at,team_data_sync_status,profile_sync_status",
            "id",
            team_id,
        )

    def _fetch_overviews(self, team_id: str) -> List[Dict[str, Any]]:
        try:
            rows = (
                self.supabase.table("team_overview_cache")
                .select("*")
                .eq("team_id", team_id)
                .order("updated_at", desc=True)
                .limit(20)
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("team_overview_cache fetch failed. team_id=%s", team_id)
            return []
        valid = [row for row in rows if str(row.get("tournament_name") or "").strip()]
        return valid or rows

    def _fetch_season_stats(self, team_id: str) -> List[Dict[str, Any]]:
        return self._fetch_many("team_season_stats_cache", "*", "team_id", team_id, limit=12)

    def _fetch_top_players(self, team_id: str) -> List[Dict[str, Any]]:
        rows = self._fetch_many(
            "team_top_players_cache",
            "player_name,position,rating,minutes_played,tournament_id,season_id,updated_at",
            "team_id",
            team_id,
            limit=30,
        )
        rows.sort(key=lambda item: (-self._safe_float(item.get("rating")), -self._safe_int(item.get("minutes_played"))))
        return rows[:8]

    def _fetch_standings(self, team_id: str) -> List[Dict[str, Any]]:
        return self._fetch_many(
            "league_standings_cache",
            "team_id,tournament_id,season_id,team_name,position,played,wins,draws,losses,points,goals_for,goals_against,goal_diff,form,updated_at",
            "team_id",
            team_id,
            limit=12,
        )

    def _fetch_match_rows_map(self, match_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not match_ids:
            return {}
        rows: List[Dict[str, Any]] = []
        for start in range(0, len(match_ids), 200):
            chunk = match_ids[start : start + 200]
            try:
                rows.extend(
                    self.supabase.table("matches")
                    .select("id,league,match_date,status,home_team_id,away_team_id,ht_home,ht_away,ft_home,ft_away")
                    .in_("id", chunk)
                    .execute()
                    .data
                    or []
                )
            except Exception:
                logger.exception("matches map fetch failed.")
        return {str(row.get("id") or ""): row for row in rows if row.get("id")}

    def _fetch_team_stats_matches(self, team_id: str, *, limit: int = 60) -> List[Dict[str, Any]]:
        try:
            stats_rows = (
                self.supabase.table("team_stats")
                .select("team_id,match_id,goals_scored,goals_conceded,xg_for,xg_against,shots,shots_on_target,possession,updated_at")
                .eq("team_id", team_id)
                .order("updated_at", desc=True)
                .limit(max(80, limit * 2))
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("team_stats fetch failed. team_id=%s", team_id)
            return []
        match_map = self._fetch_match_rows_map([str(row.get("match_id") or "") for row in stats_rows if row.get("match_id")])
        enriched: List[Dict[str, Any]] = []
        for row in stats_rows:
            match_id = str(row.get("match_id") or "")
            match_row = match_map.get(match_id) or {}
            match_date = str(match_row.get("match_date") or row.get("updated_at") or "")
            if not match_date:
                continue
            home_team_id = str(match_row.get("home_team_id") or "")
            away_team_id = str(match_row.get("away_team_id") or "")
            is_home = home_team_id == team_id
            opponent_team_id = away_team_id if is_home else home_team_id
            ht_for = self._safe_int(match_row.get("ht_home" if is_home else "ht_away"))
            ht_against = self._safe_int(match_row.get("ht_away" if is_home else "ht_home"))
            ft_for = self._safe_int(match_row.get("ft_home" if is_home else "ft_away"), self._safe_int(row.get("goals_scored")))
            ft_against = self._safe_int(match_row.get("ft_away" if is_home else "ft_home"), self._safe_int(row.get("goals_conceded")))
            result = "W" if ft_for > ft_against else "D" if ft_for == ft_against else "L"
            enriched.append(
                {
                    "match_id": match_id,
                    "match_date": match_date,
                    "league": self._repair_text(match_row.get("league") or ""),
                    "status": self._repair_text(match_row.get("status") or ""),
                    "is_home": is_home,
                    "opponent_team_id": opponent_team_id,
                    "goals_scored": self._safe_int(row.get("goals_scored"), ft_for),
                    "goals_conceded": self._safe_int(row.get("goals_conceded"), ft_against),
                    "xg_for": self._safe_float(row.get("xg_for")),
                    "xg_against": self._safe_float(row.get("xg_against")),
                    "shots": self._safe_int(row.get("shots")),
                    "shots_on_target": self._safe_int(row.get("shots_on_target")),
                    "possession": self._safe_float(row.get("possession")),
                    "result": result,
                    "ht_goals_scored": ht_for,
                    "ht_goals_conceded": ht_against,
                    "second_half_goals_scored": max(0, ft_for - ht_for),
                    "second_half_goals_conceded": max(0, ft_against - ht_against),
                }
            )
        enriched.sort(key=lambda item: str(item.get("match_date") or ""), reverse=True)
        return enriched[:limit]

    def _fetch_h2h(self, home_team_id: str, away_team_id: str, *, limit: int = 10) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        try:
            direct = (
                self.supabase.table("h2h")
                .select("match_date,home_goals,away_goals,league,is_cup,home_team_id,away_team_id")
                .eq("home_team_id", home_team_id)
                .eq("away_team_id", away_team_id)
                .order("match_date", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            )
            reverse = (
                self.supabase.table("h2h")
                .select("match_date,home_goals,away_goals,league,is_cup,home_team_id,away_team_id")
                .eq("home_team_id", away_team_id)
                .eq("away_team_id", home_team_id)
                .order("match_date", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            )
            rows = list(direct) + list(reverse)
        except Exception:
            logger.exception("h2h fetch failed. %s %s", home_team_id, away_team_id)
            return []
        rows.sort(key=lambda item: str(item.get("match_date") or ""), reverse=True)
        return rows[:limit]

    def _fetch_injuries(self, team_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            rows = (
                self.supabase.table("match_injuries")
                .select("match_id,player_name,position,status,reason,expected_return,created_at")
                .eq("team_id", team_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("match_injuries fetch failed. team_id=%s", team_id)
            return []
        deduped: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            player_name = self._repair_text(row.get("player_name"))
            if not player_name or player_name.lower() in seen:
                continue
            seen.add(player_name.lower())
            deduped.append(
                {
                    "player_name": player_name,
                    "position": self._repair_text(row.get("position")),
                    "status": self._repair_text(row.get("status")),
                    "reason": self._repair_text(row.get("reason")),
                    "expected_return": self._repair_text(row.get("expected_return")),
                    "created_at": str(row.get("created_at") or ""),
                }
            )
        return deduped[:10]

    def _find_fixture_context(self, home_team_id: str, away_team_id: str) -> Dict[str, Any]:
        try:
            candidates = (
                self.supabase.table("matches")
                .select("id,league,match_date,status,home_team_id,away_team_id")
                .or_(f"and(home_team_id.eq.{home_team_id},away_team_id.eq.{away_team_id}),and(home_team_id.eq.{away_team_id},away_team_id.eq.{home_team_id})")
                .order("match_date")
                .limit(10)
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("fixture context fetch failed. %s %s", home_team_id, away_team_id)
            return {"has_fixture_context": False}
        if not candidates:
            return {"has_fixture_context": False}
        now = datetime.now(timezone.utc)
        def weight(row: Dict[str, Any]) -> Tuple[int, float]:
            match_date = str(row.get("match_date") or "")
            try:
                parsed = datetime.fromisoformat(match_date.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                parsed = now
            return (0 if parsed >= now else 1, abs((parsed - now).total_seconds()))
        best = sorted(candidates, key=weight)[0]
        return {
            "has_fixture_context": True,
            "match_id": str(best.get("id") or ""),
            "match_date": str(best.get("match_date") or ""),
            "league": self._repair_text(best.get("league")),
            "status": self._repair_text(best.get("status")),
        }

    def _parse_stat_value(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = self._repair_text(value)
        if not text:
            return None
        text = text.replace("%", "").replace(",", ".")
        if "/" in text:
            left, *_ = text.split("/", 1)
            text = left
        try:
            return float(text)
        except ValueError:
            return None

    def _overview_value(self, overview_row: Dict[str, Any], *keys: str) -> Optional[float]:
        for group_name in ("summary_stats", "attack_stats", "passing_stats", "defending_stats", "other_stats"):
            group = overview_row.get(group_name)
            values = group.get("values") if isinstance(group, dict) else None
            if not isinstance(values, dict):
                continue
            normalized = {self._normalize_name(key): value for key, value in values.items()}
            for key in keys:
                raw = normalized.get(self._normalize_name(key))
                parsed = self._parse_stat_value(raw)
                if parsed is not None:
                    return parsed
        return None

    def _build_team_payload(self, team_row: Dict[str, Any], overview_rows: List[Dict[str, Any]], request: TeamComparisonRequest) -> Dict[str, Any]:
        team_id = str(team_row.get("id") or "")
        team_league = self._repair_text(team_row.get("league"))
        primary_overview = self._select_primary_overview(overview_rows, team_league, request)
        season_stats_rows = self._fetch_season_stats(team_id)
        top_players = self._fetch_top_players(team_id)
        standings_rows = self._fetch_standings(team_id)
        match_rows = self._fetch_team_stats_matches(team_id)
        injuries = self._fetch_injuries(team_id)
        return {
            "team": {
                "id": team_id,
                "name": self._repair_text(team_row.get("name")),
                "league": team_league,
                "country": self._repair_text(team_row.get("country")),
                "market_value": self._safe_float(team_row.get("market_value")),
                "sofascore_id": self._safe_int(team_row.get("sofascore_id")),
                "logo_url": team_row.get("logo_url"),
                "coach_name": self._repair_text(team_row.get("coach_name")),
                "team_data_last_fetched_at": str(team_row.get("team_data_last_fetched_at") or ""),
                "profile_last_fetched_at": str(team_row.get("profile_last_fetched_at") or ""),
                "team_data_sync_status": self._repair_text(team_row.get("team_data_sync_status")),
                "profile_sync_status": self._repair_text(team_row.get("profile_sync_status")),
            },
            "overview_rows": overview_rows,
            "primary_overview": primary_overview,
            "season_stats_rows": season_stats_rows,
            "top_players": top_players,
            "standings_rows": standings_rows,
            "matches": match_rows,
            "recent_matches": list(primary_overview.get("last_five_matches") or []),
            "form_last_ten": primary_overview.get("form_last_ten") or {"results": [], "points": 0, "wins": 0, "draws": 0, "losses": 0, "score_pct": 0},
            "overview_metrics": {
                "corners": self._overview_value(primary_overview, "corners", "cornerspermatch"),
                "yellow_cards": self._overview_value(primary_overview, "yellowcards", "yellowcardspermatch"),
                "red_cards": self._overview_value(primary_overview, "redcards", "redcardspermatch"),
                "pass_accuracy": self._overview_value(primary_overview, "accuratepassespercentage", "passaccuracy", "accuratepassespct"),
                "big_chances": self._overview_value(primary_overview, "bigchances", "bigchancescreated"),
                "counterattacks": self._overview_value(primary_overview, "counterattacks"),
                "average_rating": self._overview_value(primary_overview, "averageRating", "avgRating", "rating"),
                "goals_per_match": self._overview_value(primary_overview, "goalspermatch"),
                "possession": self._overview_value(primary_overview, "ballpossession", "possession"),
            },
            "injuries": injuries,
            "injury_count": len(injuries),
        }

    def _select_primary_overview(self, overview_rows: List[Dict[str, Any]], team_league: str, request: TeamComparisonRequest) -> Dict[str, Any]:
        if not overview_rows:
            return {}
        if request.tournament_id and request.season_id:
            for row in overview_rows:
                if self._safe_int(row.get("tournament_id")) == int(request.tournament_id) and self._safe_int(row.get("season_id")) == int(request.season_id):
                    return row
        normalized_league = self._normalize_name(team_league)
        for row in overview_rows:
            if self._normalize_name(row.get("tournament_name")) == normalized_league:
                return row
        return overview_rows[0]

    def _build_h2h_summary(self, rows: List[Dict[str, Any]], home_team_id: str, away_team_id: str) -> Dict[str, Any]:
        home_wins = 0
        away_wins = 0
        draws = 0
        for row in rows[:10]:
            row_home_team_id = str(row.get("home_team_id") or "")
            row_home_goals = self._safe_int(row.get("home_goals"))
            row_away_goals = self._safe_int(row.get("away_goals"))
            if row_home_goals == row_away_goals:
                draws += 1
            elif row_home_team_id == home_team_id:
                if row_home_goals > row_away_goals:
                    home_wins += 1
                else:
                    away_wins += 1
            else:
                if row_home_goals > row_away_goals:
                    away_wins += 1
                else:
                    home_wins += 1
        total = max(1, min(len(rows), 10))
        return {
            "home_wins": home_wins,
            "away_wins": away_wins,
            "draws": draws,
            "home_win_rate": round(home_wins / total, 4),
            "away_win_rate": round(away_wins / total, 4),
            "draw_rate": round(draws / total, 4),
        }

    def _collect_common_tournaments(self, home_overviews: List[Dict[str, Any]], away_overviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        away_map = {
            (self._safe_int(row.get("tournament_id")), self._safe_int(row.get("season_id"))): row
            for row in away_overviews
        }
        common: List[Dict[str, Any]] = []
        seen: set[Tuple[int, int]] = set()
        for row in home_overviews:
            key = (self._safe_int(row.get("tournament_id")), self._safe_int(row.get("season_id")))
            if key in seen or key not in away_map:
                continue
            seen.add(key)
            common.append(
                {
                    "tournament_id": key[0],
                    "season_id": key[1],
                    "tournament_name": self._repair_text(row.get("tournament_name") or away_map[key].get("tournament_name") or ""),
                    "season_name": self._repair_text(row.get("season_name") or away_map[key].get("season_name") or ""),
                }
            )
        return common

    def build_source_freshness(self, request: TeamComparisonRequest) -> Dict[str, Any]:
        def latest_team_stats_stamp(team_id: str) -> str:
            try:
                rows = (
                    self.supabase.table("team_stats")
                    .select("updated_at")
                    .eq("team_id", team_id)
                    .order("updated_at", desc=True)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                return str((rows[0] or {}).get("updated_at") or "") if rows else ""
            except Exception:
                logger.exception("team_stats freshness fetch failed. team_id=%s", team_id)
                return ""

        home_team = self._fetch_team(request.home_team_id)
        away_team = self._fetch_team(request.away_team_id)
        return {
            "home_team_data_last_fetched_at": str(home_team.get("team_data_last_fetched_at") or ""),
            "away_team_data_last_fetched_at": str(away_team.get("team_data_last_fetched_at") or ""),
            "home_profile_last_fetched_at": str(home_team.get("profile_last_fetched_at") or ""),
            "away_profile_last_fetched_at": str(away_team.get("profile_last_fetched_at") or ""),
            "home_team_stats_updated_at": latest_team_stats_stamp(request.home_team_id),
            "away_team_stats_updated_at": latest_team_stats_stamp(request.away_team_id),
        }

    def collect(self, request: TeamComparisonRequest) -> Dict[str, Any]:
        home_team = self._fetch_team(request.home_team_id)
        away_team = self._fetch_team(request.away_team_id)
        if not home_team or not away_team:
            raise ValueError("Takimlardan biri sistemde bulunamadi.")

        home_overviews = self._fetch_overviews(request.home_team_id)
        away_overviews = self._fetch_overviews(request.away_team_id)
        home_payload = self._build_team_payload(home_team, home_overviews, request)
        away_payload = self._build_team_payload(away_team, away_overviews, request)
        h2h_rows = self._fetch_h2h(request.home_team_id, request.away_team_id, limit=10)
        fixture_context = self._find_fixture_context(request.home_team_id, request.away_team_id)
        common_tournaments = self._collect_common_tournaments(home_overviews, away_overviews)
        data_gaps: List[str] = []
        if not home_overviews:
            data_gaps.append(f"{home_payload['team']['name']} için overview cache eksik.")
        if not away_overviews:
            data_gaps.append(f"{away_payload['team']['name']} için overview cache eksik.")
        if not h2h_rows:
            data_gaps.append("Kafa kafaya geçmiş verisi sınırlı veya yok.")
        if not home_payload.get("matches") or not away_payload.get("matches"):
            data_gaps.append("Takımlardan biri için yeterli maç bazlı team_stats verisi yok.")
        cross_league = self._normalize_name(home_payload["team"].get("league")) != self._normalize_name(away_payload["team"].get("league"))
        return {
            "request": request.to_payload(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "home": home_payload,
            "away": away_payload,
            "h2h": {
                "matches": h2h_rows,
                "summary": self._build_h2h_summary(h2h_rows, request.home_team_id, request.away_team_id),
            },
            "fixture_context": fixture_context,
            "common_tournaments": common_tournaments,
            "cross_league": cross_league,
            "data_gaps": data_gaps,
            "freshness": {
                "home_team_data_last_fetched_at": home_payload["team"].get("team_data_last_fetched_at"),
                "away_team_data_last_fetched_at": away_payload["team"].get("team_data_last_fetched_at"),
                "home_profile_last_fetched_at": home_payload["team"].get("profile_last_fetched_at"),
                "away_profile_last_fetched_at": away_payload["team"].get("profile_last_fetched_at"),
                "home_latest_match_date": (home_payload.get("matches") or [{}])[0].get("match_date"),
                "away_latest_match_date": (away_payload.get("matches") or [{}])[0].get("match_date"),
            },
        }
