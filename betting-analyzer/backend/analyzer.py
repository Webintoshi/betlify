from __future__ import annotations

from typing import Any, Dict, Mapping

CRITERIA_WEIGHTS: Dict[str, float] = {
    "form_last6_xg": 0.22,
    "squad_availability": 0.18,
    "xg_rolling_10": 0.15,
    "market_value": 0.12,
    "odds_movement": 0.10,
    "h2h_recent": 0.08,
    "standing_motivation": 0.07,
    "social_sentiment": 0.05,
    "weather_pitch": 0.02,
    "pi_rating_delta": 0.01,
}


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def normalize_ratio(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return 0.0
    normalized = ((value - minimum) / (maximum - minimum)) * 100.0
    return clamp_score(normalized)


def calculate_weighted_score(criteria_scores: Mapping[str, float]) -> float:
    weighted_total = 0.0
    for key, weight in CRITERIA_WEIGHTS.items():
        score = clamp_score(float(criteria_scores.get(key, 50.0)))
        weighted_total += score * weight
    return round(weighted_total, 2)


def _score_form_last6_xg(data: Mapping[str, Any]) -> float:
    form_points = float(data.get("form_points_last6", 0.0))
    xg_diff = float(data.get("xg_diff_last6", 0.0))
    form_component = normalize_ratio(form_points, 0.0, 18.0)
    xg_component = normalize_ratio(xg_diff, -6.0, 6.0)
    return (form_component * 0.7) + (xg_component * 0.3)


def _score_squad_availability(data: Mapping[str, Any]) -> float:
    missing_players = float(data.get("missing_players", 0.0))
    key_absences = float(data.get("key_absences", 0.0))
    penalty = (missing_players * 6.0) + (key_absences * 12.0)
    return clamp_score(100.0 - penalty)


def _score_xg_rolling(data: Mapping[str, Any]) -> float:
    rolling_xg_diff = float(data.get("xg_rolling_diff_10", 0.0))
    return normalize_ratio(rolling_xg_diff, -1.5, 1.5)


def _score_market_value(data: Mapping[str, Any]) -> float:
    market_value_delta_pct = float(data.get("market_value_delta_pct", 0.0))
    return normalize_ratio(market_value_delta_pct, -100.0, 100.0)


def _score_odds_movement(data: Mapping[str, Any]) -> float:
    opening = data.get("opening_odd")
    closing = data.get("closing_odd")
    if opening is None or closing is None:
        return 50.0

    opening_value = float(opening)
    closing_value = float(closing)
    if opening_value <= 0:
        return 50.0

    drift_pct = ((opening_value - closing_value) / opening_value) * 100.0
    return normalize_ratio(drift_pct, -15.0, 15.0)


def _score_h2h(data: Mapping[str, Any]) -> float:
    h2h_summary = data.get("h2h_summary")
    if isinstance(h2h_summary, dict):
        ratio = float(h2h_summary.get("ratio", 0.5) or 0.5)
        return normalize_ratio(ratio, 0.0, 1.0)

    if "h2h_ratio" in data:
        ratio = float(data.get("h2h_ratio", 0.5) or 0.5)
        return normalize_ratio(ratio, 0.0, 1.0)

    h2h_rows = data.get("h2h_matches")
    if isinstance(h2h_rows, list) and h2h_rows:
        league_scores: list[float] = []
        cup_scores: list[float] = []
        for row in h2h_rows:
            if not isinstance(row, dict):
                continue
            home_goals = float(row.get("home_goals", 0) or 0)
            away_goals = float(row.get("away_goals", 0) or 0)
            if home_goals > away_goals:
                score = 1.0
            elif home_goals == away_goals:
                score = 0.5
            else:
                score = 0.0
            is_cup = bool(row.get("is_cup", False))
            if is_cup:
                cup_scores.append(score)
            else:
                league_scores.append(score)

        league_avg = (sum(league_scores) / len(league_scores)) if league_scores else 0.5
        cup_avg = (sum(cup_scores) / len(cup_scores)) if cup_scores else 0.5
        weighted = (league_avg * 0.7) + (cup_avg * 0.3)
        return normalize_ratio(weighted, 0.0, 1.0)

    h2h_points_ratio = float(data.get("h2h_points_ratio", 0.5))
    return normalize_ratio(h2h_points_ratio, 0.0, 1.0)


def _motivation_multiplier(data: Mapping[str, Any]) -> float:
    competition_type = str(data.get("competition_type", "league")).lower()
    stage = str(data.get("competition_stage", "regular")).lower()
    is_knockout = any(flag in stage for flag in ["quarter", "semi", "final"])
    is_group = "group" in stage
    is_group_last_week = bool(data.get("is_group_last_week", False))
    elimination_risk = bool(data.get("elimination_risk", False))
    leadership_race = bool(data.get("leadership_race", False))

    home_position = int(data.get("home_position", 0) or 0)
    league_size = int(data.get("league_size", 20) or 20)
    points_gap_to_leader = float(data.get("points_gap_to_leader", 99.0) or 99.0)

    if competition_type in {"cup", "uefa", "europe"} and is_knockout:
        return 1.5
    if competition_type in {"cup", "uefa", "europe"} and is_group and is_group_last_week and (elimination_risk or leadership_race):
        return 1.3
    if competition_type in {"cup", "uefa", "europe"} and is_group:
        return 1.0
    if competition_type == "league" and home_position > 0 and home_position >= max(league_size - 2, 1):
        return 1.4
    if competition_type == "league" and home_position > 0 and home_position <= 3 and points_gap_to_leader < 5:
        return 1.3
    return 1.0


def _score_standing_motivation(data: Mapping[str, Any]) -> float:
    standing_pressure = float(data.get("standing_pressure", 0.5))
    multiplier = _motivation_multiplier(data)
    return normalize_ratio(standing_pressure * multiplier, 0.0, 1.5)


def _score_social_sentiment(data: Mapping[str, Any]) -> float:
    sentiment = float(data.get("social_sentiment_score", 0.0))
    return normalize_ratio(sentiment, -1.0, 1.0)


def _score_weather_pitch(data: Mapping[str, Any]) -> float:
    if "weather_score" in data and data.get("weather_score") is not None:
        return clamp_score(float(data.get("weather_score", 50.0) or 50.0))
    weather_impact = float(data.get("weather_impact_score", 0.0))
    return normalize_ratio(weather_impact, -1.0, 1.0)


def _score_pi_rating_delta(data: Mapping[str, Any]) -> float:
    pi_delta = float(data.get("pi_rating_delta", 0.0))
    return normalize_ratio(pi_delta, -50.0, 50.0)


def build_criteria_scores(match_context: Mapping[str, Any]) -> Dict[str, float]:
    scores = {
        "form_last6_xg": _score_form_last6_xg(match_context),
        "squad_availability": _score_squad_availability(match_context),
        "xg_rolling_10": _score_xg_rolling(match_context),
        "market_value": _score_market_value(match_context),
        "odds_movement": _score_odds_movement(match_context),
        "h2h_recent": _score_h2h(match_context),
        "standing_motivation": _score_standing_motivation(match_context),
        "social_sentiment": _score_social_sentiment(match_context),
        "weather_pitch": _score_weather_pitch(match_context),
        "pi_rating_delta": _score_pi_rating_delta(match_context),
    }
    return {key: round(clamp_score(value), 2) for key, value in scores.items()}


def analyze_match(match_context: Mapping[str, Any], confidence_threshold: float = 60.0) -> Dict[str, Any]:
    criteria_scores = build_criteria_scores(match_context)
    confidence_score = calculate_weighted_score(criteria_scores)
    return {
        "confidence_score": confidence_score,
        "recommended": confidence_score >= confidence_threshold,
        "criteria_scores": criteria_scores,
    }
