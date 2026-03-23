from __future__ import annotations

import math
import re
import unicodedata
from datetime import date
from typing import Any, Dict, List, Optional

from .models import TeamComparisonRequest


class TeamComparisonFeatureService:
    @staticmethod
    def _safe_float(value: Any, fallback: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return fallback
            if isinstance(value, str):
                text = value.strip().replace("%", "").replace(",", ".")
                if "/" in text:
                    text = text.split("/", 1)[0]
                return float(text)
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _safe_int(value: Any, fallback: int = 0) -> int:
        try:
            if value is None or value == "":
                return fallback
            return int(float(value))
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _avg(values: List[float], fallback: float = 0.0) -> float:
        cleaned = [float(value) for value in values if value is not None]
        return sum(cleaned) / len(cleaned) if cleaned else fallback

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
    def _normalize_key(cls, value: Any) -> str:
        repaired = cls._repair_text(value).lower()
        normalized = unicodedata.normalize("NFKD", repaired)
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", "", ascii_only)

    def _overview_value(self, overview_row: Dict[str, Any], *keys: str) -> Optional[float]:
        if not isinstance(overview_row, dict):
            return None
        for group_name in ("summary_stats", "attack_stats", "passing_stats", "defending_stats", "other_stats"):
            group = overview_row.get(group_name)
            values = group.get("values") if isinstance(group, dict) else None
            if not isinstance(values, dict):
                continue
            normalized = {self._normalize_key(key): raw_value for key, raw_value in values.items()}
            for key in keys:
                candidate = normalized.get(self._normalize_key(key))
                if candidate is None:
                    continue
                parsed = self._safe_float(candidate, math.nan)
                if not math.isnan(parsed):
                    return parsed
        return None

    def _resolve_selected_tournament(self, snapshot: Dict[str, Any], request: TeamComparisonRequest) -> Optional[Dict[str, Any]]:
        if request.scope == "common_tournament":
            target_tournament_id = self._safe_int(request.tournament_id)
            target_season_id = self._safe_int(request.season_id)
            common_rows = snapshot.get("common_tournaments") or []
            if target_tournament_id > 0 and target_season_id > 0:
                for row in common_rows:
                    if self._safe_int(row.get("tournament_id")) == target_tournament_id and self._safe_int(row.get("season_id")) == target_season_id:
                        return row
            return common_rows[0] if common_rows else None

        if request.tournament_id and request.season_id:
            return {
                "tournament_id": self._safe_int(request.tournament_id),
                "season_id": self._safe_int(request.season_id),
            }

        home_primary = snapshot.get("home", {}).get("primary_overview") or {}
        if home_primary:
            return {
                "tournament_id": self._safe_int(home_primary.get("tournament_id")),
                "season_id": self._safe_int(home_primary.get("season_id")),
                "tournament_name": self._repair_text(home_primary.get("tournament_name")),
                "season_name": self._repair_text(home_primary.get("season_name")),
            }
        return None

    def _select_team_overview(self, team_payload: Dict[str, Any], selected_tournament: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        overview_rows = team_payload.get("overview_rows") or []
        if not isinstance(overview_rows, list):
            return team_payload.get("primary_overview") or {}
        tournament_id = self._safe_int((selected_tournament or {}).get("tournament_id"))
        season_id = self._safe_int((selected_tournament or {}).get("season_id"))
        if tournament_id > 0 and season_id > 0:
            for row in overview_rows:
                if self._safe_int(row.get("tournament_id")) == tournament_id and self._safe_int(row.get("season_id")) == season_id:
                    return row
        primary = team_payload.get("primary_overview") or {}
        return primary if isinstance(primary, dict) else {}

    def _within_date_range(self, match_date: str, date_from: Optional[str], date_to: Optional[str]) -> bool:
        raw = str(match_date or "").strip()
        if not raw:
            return True
        try:
            match_day = date.fromisoformat(raw[:10])
        except ValueError:
            return True
        if date_from:
            try:
                if match_day < date.fromisoformat(date_from):
                    return False
            except ValueError:
                pass
        if date_to:
            try:
                if match_day > date.fromisoformat(date_to):
                    return False
            except ValueError:
                pass
        return True

    def _filter_matches(self, matches: List[Dict[str, Any]], team_payload: Dict[str, Any], request: TeamComparisonRequest, selected_overview: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(matches, list):
            return []
        normalized_team_league = self._normalize_key(team_payload.get("team", {}).get("league"))
        normalized_selected_tournament = self._normalize_key(selected_overview.get("tournament_name") or selected_overview.get("resolved_tournament_name"))
        filtered: List[Dict[str, Any]] = []
        for row in matches:
            if not isinstance(row, dict):
                continue
            if not self._within_date_range(str(row.get("match_date") or ""), request.date_from, request.date_to):
                continue
            normalized_match_league = self._normalize_key(row.get("league"))
            if request.scope == "all_competitions":
                filtered.append(row)
                continue
            if request.scope == "common_tournament":
                if normalized_selected_tournament and normalized_match_league == normalized_selected_tournament:
                    filtered.append(row)
                continue
            if normalized_selected_tournament and normalized_match_league == normalized_selected_tournament:
                filtered.append(row)
                continue
            if normalized_team_league and normalized_match_league == normalized_team_league:
                filtered.append(row)
        if len(filtered) >= max(3, int(request.data_window) // 2):
            return filtered
        return [row for row in matches if isinstance(row, dict) and self._within_date_range(str(row.get("match_date") or ""), request.date_from, request.date_to)]

    def _window(self, matches: List[Dict[str, Any]], size: int, *, venue: Optional[bool] = None) -> List[Dict[str, Any]]:
        subset = matches
        if venue is not None:
            subset = [row for row in matches if bool(row.get("is_home")) is venue]
        return subset[:size]

    def _weighted_form_score(self, matches: List[Dict[str, Any]]) -> float:
        if not matches:
            return 0.0
        first = matches[:3]
        second = matches[3:6]
        third = matches[6:10]

        def ppg(rows: List[Dict[str, Any]]) -> float:
            if not rows:
                return 0.0
            points = sum(3 if str(row.get("result") or "") == "W" else 1 if str(row.get("result") or "") == "D" else 0 for row in rows)
            return points / (len(rows) * 3)

        weighted = 0.5 * ppg(first) + 0.3 * ppg(second) + 0.2 * ppg(third)
        return self._clamp(weighted * 100.0)

    def _trend_label(self, matches: List[Dict[str, Any]]) -> str:
        if len(matches) < 4:
            return "stabil"
        recent = matches[:3]
        older = matches[3:6]
        recent_points = sum(3 if row.get("result") == "W" else 1 if row.get("result") == "D" else 0 for row in recent)
        older_points = sum(3 if row.get("result") == "W" else 1 if row.get("result") == "D" else 0 for row in older)
        if recent_points >= older_points + 2:
            return "yukselen"
        if older_points >= recent_points + 2:
            return "dusen"
        return "stabil"

    def _compute_proxy_xg(self, *, shots: float, shots_on_target: float, big_chances: float, corners: float, possession: float) -> float:
        box_entry = 0.6 * shots_on_target + 0.3 * corners + 0.1 * ((possession - 50.0) / 10.0)
        transition_rating = (shots_on_target + max(big_chances, 0.0)) / 2.0 if big_chances > 0 else max(shots_on_target * 0.75, 0.0)
        return max(0.2, 0.04 * shots + 0.16 * shots_on_target + 0.22 * big_chances + 0.06 * corners + 0.10 * box_entry + 0.08 * transition_rating)

    def _ppg(self, matches: List[Dict[str, Any]]) -> float:
        if not matches:
            return 0.0
        total = sum(3 if row.get("result") == "W" else 1 if row.get("result") == "D" else 0 for row in matches)
        return total / len(matches)

    def _goal_diff_pg(self, matches: List[Dict[str, Any]]) -> float:
        if not matches:
            return 0.0
        return self._avg([self._safe_float(row.get("goals_scored")) - self._safe_float(row.get("goals_conceded")) for row in matches])

    def _compute_team_metrics(self, team_payload: Dict[str, Any], *, selected_overview: Dict[str, Any], filtered_matches: List[Dict[str, Any]], venue_role: str) -> Dict[str, Any]:
        recent5 = self._window(filtered_matches, 5)
        recent10 = self._window(filtered_matches, 10)
        recent20 = self._window(filtered_matches, 20)
        venue_matches = self._window(filtered_matches, 5, venue=(venue_role == "home"))
        matches_for_core = recent10 or filtered_matches[:10]
        matches_for_extended = recent20 or filtered_matches

        shots_pg = self._avg([self._safe_float(row.get("shots")) for row in matches_for_core])
        shots_on_target_pg = self._avg([self._safe_float(row.get("shots_on_target")) for row in matches_for_core])
        possession_pg = self._avg([self._safe_float(row.get("possession")) for row in matches_for_core], self._safe_float(team_payload.get("overview_metrics", {}).get("possession"), 50.0))
        goals_pg = self._avg([self._safe_float(row.get("goals_scored")) for row in matches_for_core])
        conceded_pg = self._avg([self._safe_float(row.get("goals_conceded")) for row in matches_for_core])
        clean_sheet_rate = self._avg([1.0 if self._safe_int(row.get("goals_conceded")) == 0 else 0.0 for row in matches_for_core])
        failed_to_score_rate = self._avg([1.0 if self._safe_int(row.get("goals_scored")) == 0 else 0.0 for row in matches_for_core])
        over25_rate = self._avg([1.0 if (self._safe_int(row.get("goals_scored")) + self._safe_int(row.get("goals_conceded"))) > 2 else 0.0 for row in matches_for_extended[:10]])
        btts_rate = self._avg([1.0 if self._safe_int(row.get("goals_scored")) > 0 and self._safe_int(row.get("goals_conceded")) > 0 else 0.0 for row in matches_for_extended[:10]])

        xg_for_values = [self._safe_float(row.get("xg_for"), math.nan) for row in matches_for_core]
        xg_for_values = [value for value in xg_for_values if not math.isnan(value) and value > 0]
        xg_against_values = [self._safe_float(row.get("xg_against"), math.nan) for row in matches_for_core]
        xg_against_values = [value for value in xg_against_values if not math.isnan(value) and value > 0]

        corners_pg = self._safe_float(team_payload.get("overview_metrics", {}).get("corners"))
        yellow_cards_pg = self._safe_float(team_payload.get("overview_metrics", {}).get("yellow_cards"))
        red_cards_pg = self._safe_float(team_payload.get("overview_metrics", {}).get("red_cards"))
        pass_accuracy = self._safe_float(team_payload.get("overview_metrics", {}).get("pass_accuracy"))
        big_chances = self._safe_float(team_payload.get("overview_metrics", {}).get("big_chances"))
        counterattacks = self._safe_float(team_payload.get("overview_metrics", {}).get("counterattacks"))
        average_rating = self._safe_float(team_payload.get("overview_metrics", {}).get("average_rating"))

        proxy_xg = self._compute_proxy_xg(shots=shots_pg, shots_on_target=shots_on_target_pg, big_chances=big_chances, corners=corners_pg, possession=possession_pg)
        xg_for_pg = self._avg(xg_for_values, proxy_xg)
        xg_against_pg = self._avg(xg_against_values, max(0.25, conceded_pg * 0.92))
        proxy_xg_used = not bool(xg_for_values)

        first_half_goals = sum(self._safe_float(row.get("ht_goals_scored")) for row in matches_for_core)
        second_half_goals = sum(self._safe_float(row.get("second_half_goals_scored")) for row in matches_for_core)
        total_goals = max(1.0, first_half_goals + second_half_goals)
        first_half_goal_ratio = first_half_goals / total_goals
        second_half_goal_ratio = second_half_goals / total_goals
        late_goal_conceded_ratio = self._avg([1.0 if self._safe_float(row.get("second_half_goals_conceded")) > self._safe_float(row.get("ht_goals_conceded")) else 0.0 for row in matches_for_core])
        conversion_rate = (goals_pg / shots_pg) if shots_pg > 0 else 0.0
        venue_ppg = self._ppg(venue_matches)
        venue_goal_diff_pg = self._goal_diff_pg(venue_matches)
        weighted_form = self._weighted_form_score(matches_for_extended[:10])
        trend = self._trend_label(matches_for_extended[:10])

        header_goals = self._overview_value(selected_overview, "headedGoals", "goalsfromhead") or 0.0
        freekick_goals = self._overview_value(selected_overview, "freeKickGoals", "freekickgoals") or 0.0
        avg_rating_score = self._clamp((average_rating - 5.5) * 20.0)

        attack_score = self._clamp(goals_pg * 22 + xg_for_pg * 16 + shots_on_target_pg * 5 + conversion_rate * 110 + second_half_goal_ratio * 14 + big_chances * 3)
        defense_score = self._clamp(100 - conceded_pg * 24 - xg_against_pg * 14 + clean_sheet_rate * 26 - late_goal_conceded_ratio * 12 + avg_rating_score * 0.15)
        form_score = self._clamp(weighted_form)
        home_away_score = self._clamp(venue_ppg * 24 + venue_goal_diff_pg * 18 + (8 if venue_role == "home" else 4))
        tempo_score = self._clamp(shots_pg * 4 + shots_on_target_pg * 6 + corners_pg * 4 + over25_rate * 32)
        set_piece_score = self._clamp(corners_pg * 8 + header_goals * 4 + freekick_goals * 10)
        transition_score = self._clamp(counterattacks * 6 + shots_on_target_pg * 7 + big_chances * 7)
        resilience_score = self._clamp(second_half_goal_ratio * 44 + clean_sheet_rate * 24 + (1.0 - late_goal_conceded_ratio) * 20 + form_score * 0.12)

        top_players = team_payload.get("top_players") or []
        top_rating_avg = self._avg([self._safe_float(player.get("rating")) for player in top_players[:5]])
        injury_count = self._safe_int(team_payload.get("injury_count"))
        missing_key_players = min(injury_count, max(1, len(top_players[:3]))) if top_players else injury_count
        squad_penalty = injury_count * 4.0 + missing_key_players * 3.0
        squad_score = self._clamp(45 + (top_rating_avg - 6.0) * 18 + math.log1p(max(self._safe_float(team_payload.get("team", {}).get("market_value")), 0.0)) * 3 - squad_penalty)

        standings_rows = team_payload.get("standings_rows") or []
        standings = standings_rows[0] if standings_rows else {}
        position = self._safe_int(standings.get("position"))
        played = max(1, self._safe_int(standings.get("played")))
        points = self._safe_int(standings.get("points"))
        goal_diff = self._safe_int(standings.get("goal_diff"))
        points_per_game = points / played
        position_bonus = max(0.0, 25.0 - max(position - 1, 0) * 1.2) if position > 0 else 8.0
        context_score = self._clamp(position_bonus + points_per_game * 18 + goal_diff / played * 9 + avg_rating_score * 0.2)

        first_half_pressure_score = self._clamp(first_half_goal_ratio * 60 + shots_on_target_pg * 4 + form_score * 0.15)
        score_protection_score = self._clamp(clean_sheet_rate * 42 + defense_score * 0.45 + (1.0 - late_goal_conceded_ratio) * 22)
        comeback_score = self._clamp(second_half_goal_ratio * 40 + attack_score * 0.25 + form_score * 0.18 - failed_to_score_rate * 24)
        goal_expectation_score = self._clamp(xg_for_pg * 22 + goals_pg * 16 + over25_rate * 25)

        stat_source_count = 0
        stat_source_count += 1 if matches_for_core else 0
        stat_source_count += 1 if team_payload.get("primary_overview") else 0
        stat_source_count += 1 if standings_rows else 0
        stat_source_count += 1 if top_players else 0
        data_reliability_score = self._clamp(len(matches_for_extended[:10]) * 6 + stat_source_count * 12)

        primary_overview_form = (team_payload.get("form_last_ten") or {}).get("results") or []
        recent5_form = list(primary_overview_form[:5]) if (not recent5 and primary_overview_form) else [str(row.get("result") or "") for row in recent5]

        return {
            "team": team_payload.get("team") or {},
            "selected_tournament_name": self._repair_text(selected_overview.get("tournament_name") or selected_overview.get("resolved_tournament_name") or team_payload.get("team", {}).get("league")),
            "selected_tournament_id": self._safe_int(selected_overview.get("tournament_id")),
            "selected_season_id": self._safe_int(selected_overview.get("season_id")),
            "matches_used": len(matches_for_extended[:20]),
            "match_ids_used": [str(row.get("match_id") or "") for row in matches_for_extended[:20] if row.get("match_id")],
            "recent5_form": recent5_form,
            "recent10_form": [str(row.get("result") or "") for row in matches_for_extended[:10]] or list(primary_overview_form),
            "goals_per_match": round(goals_pg, 3),
            "goals_conceded_per_match": round(conceded_pg, 3),
            "xg_for": round(xg_for_pg, 3),
            "xg_against": round(xg_against_pg, 3),
            "proxy_xg": round(proxy_xg, 3),
            "proxy_xg_used": proxy_xg_used,
            "shots_per_match": round(shots_pg, 3),
            "shots_on_target_per_match": round(shots_on_target_pg, 3),
            "conversion_rate": round(conversion_rate, 4),
            "possession": round(possession_pg, 3),
            "pass_accuracy": round(pass_accuracy, 3),
            "corners_per_match": round(corners_pg, 3),
            "yellow_cards_per_match": round(yellow_cards_pg, 3),
            "red_cards_per_match": round(red_cards_pg, 3),
            "clean_sheet_rate": round(clean_sheet_rate, 4),
            "failed_to_score_rate": round(failed_to_score_rate, 4),
            "over25_rate": round(over25_rate, 4),
            "btts_rate": round(btts_rate, 4),
            "first_half_goal_ratio": round(first_half_goal_ratio, 4),
            "second_half_goal_ratio": round(second_half_goal_ratio, 4),
            "late_goal_conceded_ratio": round(late_goal_conceded_ratio, 4),
            "venue_ppg": round(venue_ppg, 4),
            "venue_goal_diff_pg": round(venue_goal_diff_pg, 4),
            "weighted_form": round(weighted_form, 3),
            "trend": trend,
            "average_rating": round(average_rating, 3),
            "position": position,
            "points": points,
            "played": played,
            "goal_diff": goal_diff,
            "points_per_game": round(points_per_game, 4),
            "market_value": round(self._safe_float(team_payload.get("team", {}).get("market_value")), 2),
            "injury_count": injury_count,
            "missing_key_players": missing_key_players,
            "attack_score": round(attack_score, 2),
            "defense_score": round(defense_score, 2),
            "form_score": round(form_score, 2),
            "home_away_score": round(home_away_score, 2),
            "tempo_score": round(tempo_score, 2),
            "set_piece_score": round(set_piece_score, 2),
            "transition_score": round(transition_score, 2),
            "resilience_score": round(resilience_score, 2),
            "squad_score": round(squad_score, 2),
            "context_score": round(context_score, 2),
            "first_half_pressure_score": round(first_half_pressure_score, 2),
            "score_protection_score": round(score_protection_score, 2),
            "comeback_score": round(comeback_score, 2),
            "goal_expectation_score": round(goal_expectation_score, 2),
            "data_reliability_score": round(data_reliability_score, 2),
            "top_players": top_players[:5],
            "injuries": team_payload.get("injuries") or [],
        }

    def build(self, snapshot: Dict[str, Any], request: TeamComparisonRequest) -> Dict[str, Any]:
        selected_tournament = self._resolve_selected_tournament(snapshot, request)
        home_selected_overview = self._select_team_overview(snapshot.get("home") or {}, selected_tournament)
        away_selected_overview = self._select_team_overview(snapshot.get("away") or {}, selected_tournament)
        home_filtered_matches = self._filter_matches(snapshot.get("home", {}).get("matches") or [], snapshot.get("home") or {}, request, home_selected_overview)
        away_filtered_matches = self._filter_matches(snapshot.get("away", {}).get("matches") or [], snapshot.get("away") or {}, request, away_selected_overview)
        home_metrics = self._compute_team_metrics(snapshot.get("home") or {}, selected_overview=home_selected_overview, filtered_matches=home_filtered_matches, venue_role="home")
        away_metrics = self._compute_team_metrics(snapshot.get("away") or {}, selected_overview=away_selected_overview, filtered_matches=away_filtered_matches, venue_role="away")
        included_match_ids = list(dict.fromkeys(home_metrics.get("match_ids_used", []) + away_metrics.get("match_ids_used", [])))
        league_context = self._repair_text((selected_tournament or {}).get("tournament_name") or snapshot.get("fixture_context", {}).get("league") or home_metrics.get("selected_tournament_name") or home_metrics.get("team", {}).get("league") or away_metrics.get("team", {}).get("league"))
        feature_sources = {
            "home_xg": "proxy_xg" if home_metrics.get("proxy_xg_used") else "team_stats",
            "away_xg": "proxy_xg" if away_metrics.get("proxy_xg_used") else "team_stats",
            "home_pass_accuracy": "team_overview_cache" if self._safe_float(home_metrics.get("pass_accuracy")) > 0 else "unavailable",
            "away_pass_accuracy": "team_overview_cache" if self._safe_float(away_metrics.get("pass_accuracy")) > 0 else "unavailable",
            "selected_scope": request.scope,
        }
        return {
            "home": home_metrics,
            "away": away_metrics,
            "selected_tournament": selected_tournament,
            "league_context": league_context,
            "cross_league": bool(snapshot.get("cross_league")),
            "included_match_ids": included_match_ids,
            "feature_sources": feature_sources,
        }
