from __future__ import annotations

from math import isfinite
from typing import Any, Dict, Mapping, Optional, Tuple

import numpy as np
from scipy.stats import poisson

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

CONFIDENCE_WEIGHTS: Dict[str, float] = {
    "pi_rating": 0.25,
    "form": 0.15,
    "xg_attack": 0.20,
    "xg_defense": 0.10,
    "odds_movement": 0.15,
    "squad": 0.10,
    "h2h": 0.05,
}


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def normalize_ratio(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return 0.0
    normalized = ((float(value) - minimum) / (maximum - minimum)) * 100.0
    return clamp_score(normalized)


def _clamp_probability(value: float) -> float:
    if not isfinite(float(value)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def dixon_coles_correction(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    rho: float = -0.1,
) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - (lambda_home * lambda_away * rho)
    if home_goals == 0 and away_goals == 1:
        return 1.0 + (lambda_home * rho)
    if home_goals == 1 and away_goals == 0:
        return 1.0 + (lambda_away * rho)
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def build_score_matrix(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 8,
    rho: float = -0.1,
) -> np.ndarray:
    max_goals = max(4, int(max_goals))
    lam_home = max(0.05, float(lambda_home))
    lam_away = max(0.05, float(lambda_away))
    matrix = np.zeros((max_goals + 1, max_goals + 1), dtype=float)

    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            probability = poisson.pmf(i, lam_home) * poisson.pmf(j, lam_away)
            probability *= dixon_coles_correction(i, j, lam_home, lam_away, rho=rho)
            matrix[i, j] = max(0.0, float(probability))

    total = float(matrix.sum())
    if total <= 0:
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                matrix[i, j] = poisson.pmf(i, lam_home) * poisson.pmf(j, lam_away)
        total = float(matrix.sum())
    if total > 0:
        matrix /= total
    return matrix


def calculate_lambdas(
    home_attack: float,
    home_defense: float,
    away_attack: float,
    away_defense: float,
    league_avg_goals: float = 1.35,
    home_advantage: float = 1.15,
    home_xg: Optional[float] = None,
    away_xg: Optional[float] = None,
    xg_weight: float = 0.4,
) -> Tuple[float, float]:
    league_avg = max(0.2, float(league_avg_goals))
    stat_lambda_home = (
        (max(0.05, float(home_attack)) / league_avg)
        * (max(0.05, float(away_defense)) / league_avg)
        * league_avg
        * max(0.8, float(home_advantage))
    )
    stat_lambda_away = (
        (max(0.05, float(away_attack)) / league_avg)
        * (max(0.05, float(home_defense)) / league_avg)
        * league_avg
    )

    lambda_home = stat_lambda_home
    lambda_away = stat_lambda_away
    if home_xg is not None and away_xg is not None:
        weight = _clamp_probability(xg_weight)
        lambda_home = ((1.0 - weight) * stat_lambda_home) + (weight * max(0.05, float(home_xg)))
        lambda_away = ((1.0 - weight) * stat_lambda_away) + (weight * max(0.05, float(away_xg)))

    return round(max(0.05, lambda_home), 4), round(max(0.05, lambda_away), 4)


def calculate_halftime_lambdas(
    lambda_home_full: float,
    lambda_away_full: float,
    ht_home_ratio: float = 0.42,
    ht_away_ratio: float = 0.40,
) -> Tuple[float, float]:
    home_ratio = max(0.25, min(0.6, float(ht_home_ratio)))
    away_ratio = max(0.25, min(0.6, float(ht_away_ratio)))
    return (
        round(max(0.03, float(lambda_home_full) * home_ratio), 4),
        round(max(0.03, float(lambda_away_full) * away_ratio), 4),
    )


def rho_fit(_: Optional[list[dict[str, Any]]] = None, initial_rho: float = -0.1) -> float:
    # Placeholder for future historical fit. For now keep fixed as requested.
    return float(initial_rho)


def _sum_market(matrix: np.ndarray, predicate: Any) -> float:
    total = 0.0
    rows, cols = matrix.shape
    for i in range(rows):
        for j in range(cols):
            if predicate(i, j):
                total += float(matrix[i, j])
    return _clamp_probability(total)


def calculate_all_market_probabilities(
    lambda_home: float,
    lambda_away: float,
    ht_lambda_home: float,
    ht_lambda_away: float,
    rho: float = -0.1,
    max_goals: int = 8,
) -> Dict[str, float]:
    ft_matrix = build_score_matrix(lambda_home, lambda_away, max_goals=max_goals, rho=rho)
    ht_matrix = build_score_matrix(ht_lambda_home, ht_lambda_away, max_goals=max_goals, rho=rho)

    probabilities: Dict[str, float] = {}

    probabilities["MS1"] = _sum_market(ft_matrix, lambda i, j: i > j)
    probabilities["MSX"] = _sum_market(ft_matrix, lambda i, j: i == j)
    probabilities["MS2"] = _sum_market(ft_matrix, lambda i, j: i < j)

    probabilities["IY1"] = _sum_market(ht_matrix, lambda i, j: i > j)
    probabilities["IYX"] = _sum_market(ht_matrix, lambda i, j: i == j)
    probabilities["IY2"] = _sum_market(ht_matrix, lambda i, j: i < j)

    for threshold in [0.5, 1.5, 2.5, 3.5, 4.5]:
        over_prob = _sum_market(ft_matrix, lambda i, j, t=threshold: (i + j) > t)
        probabilities[f"MS_O{threshold}"] = over_prob
        probabilities[f"MS_U{threshold}"] = _clamp_probability(1.0 - over_prob)

    for threshold in [0.5, 1.5, 2.5]:
        over_prob = _sum_market(ht_matrix, lambda i, j, t=threshold: (i + j) > t)
        probabilities[f"IY_O{threshold}"] = over_prob
        probabilities[f"IY_U{threshold}"] = _clamp_probability(1.0 - over_prob)

    home_zero = _sum_market(ft_matrix, lambda i, j: i == 0)
    away_zero = _sum_market(ft_matrix, lambda i, j: j == 0)
    p_home_scores = _clamp_probability(1.0 - home_zero)
    p_away_scores = _clamp_probability(1.0 - away_zero)
    probabilities["KG_VAR"] = _clamp_probability(p_home_scores * p_away_scores)
    probabilities["KG_YOK"] = _clamp_probability(1.0 - probabilities["KG_VAR"])

    probabilities["HCP_-1"] = _sum_market(ft_matrix, lambda i, j: (i - j) >= 2)
    probabilities["HCP_-0.5"] = probabilities["MS1"]
    probabilities["HCP_+0.5"] = _sum_market(ft_matrix, lambda i, j: i <= j)
    probabilities["HCP_+1"] = _sum_market(ft_matrix, lambda i, j: (j - i) <= 1)
    probabilities["HCP_+1.5"] = _sum_market(ft_matrix, lambda i, j: (j - i) < 2)
    probabilities["HCP_+2"] = _sum_market(ft_matrix, lambda i, j: (j - i) <= 2)
    probabilities["HCP_+2.5"] = _sum_market(ft_matrix, lambda i, j: (j - i) < 3)

    return {key: round(_clamp_probability(value), 6) for key, value in probabilities.items()}


def calculate_confidence_score(
    pi_rating_delta: float,
    form_home: float,
    form_away: float,
    xg_home: float,
    xg_away: float,
    xga_home: float,
    xga_away: float,
    odds_movement: float,
    squad_availability: float,
    h2h_score: float,
    market_type: str,
) -> float:
    _ = market_type
    pi_score = _clamp_probability((float(pi_rating_delta) + 1.0) / 2.0)
    form_score = _clamp_probability((float(form_home) + (1.0 - float(form_away))) / 2.0)
    xg_attack_score = _clamp_probability(float(xg_home) / 2.5)
    xg_defense_score = _clamp_probability(1.0 - (float(xga_home) / 2.5))
    odds_score = _clamp_probability((float(odds_movement) + 1.0) / 2.0)
    squad_score = _clamp_probability(float(squad_availability))
    h2h_component = _clamp_probability(float(h2h_score))

    raw_score = (
        (CONFIDENCE_WEIGHTS["pi_rating"] * pi_score)
        + (CONFIDENCE_WEIGHTS["form"] * form_score)
        + (CONFIDENCE_WEIGHTS["xg_attack"] * xg_attack_score)
        + (CONFIDENCE_WEIGHTS["xg_defense"] * xg_defense_score)
        + (CONFIDENCE_WEIGHTS["odds_movement"] * odds_score)
        + (CONFIDENCE_WEIGHTS["squad"] * squad_score)
        + (CONFIDENCE_WEIGHTS["h2h"] * h2h_component)
    )
    return round(raw_score * 100.0, 2)


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


def build_criteria_scores(match_context: Mapping[str, Any]) -> Dict[str, float]:
    form_home = _clamp_probability(_safe_float(match_context.get("home_form_score"), _safe_float(match_context.get("form_points_last6"), 9.0) / 18.0))
    form_away = _clamp_probability(_safe_float(match_context.get("away_form_score"), 0.5))
    xg_home = max(0.0, _safe_float(match_context.get("home_attack_xg"), 0.0))
    xga_home = max(0.0, _safe_float(match_context.get("home_defense_xg"), 0.0))
    xg_away = max(0.0, _safe_float(match_context.get("away_attack_xg"), 0.0))
    xga_away = max(0.0, _safe_float(match_context.get("away_defense_xg"), 0.0))

    odds_movement = _safe_float(match_context.get("odds_movement"), 0.0)
    market_value_delta_pct = _safe_float(match_context.get("market_value_delta_pct"), 0.0)
    h2h_ratio = _safe_float(match_context.get("h2h_ratio"), 0.5)
    standing_pressure = _safe_float(match_context.get("standing_pressure"), 0.5)
    social_sentiment = _safe_float(match_context.get("social_sentiment_score"), 0.0)
    weather_score = _safe_float(match_context.get("weather_score"), 50.0)
    pi_delta = _safe_float(match_context.get("pi_rating_delta"), 0.0)
    squad_availability = _safe_float(match_context.get("squad_availability"), 1.0)

    if squad_availability > 1:
        squad_availability = _clamp_probability(squad_availability / 100.0)
    else:
        squad_availability = _clamp_probability(squad_availability)

    xg_roll_diff = _safe_float(match_context.get("xg_rolling_diff_10"), xg_home - xg_away)
    motivation_score = normalize_ratio(standing_pressure * _motivation_multiplier(match_context), 0.0, 1.5)

    criteria = {
        "form_last6_xg": clamp_score(((form_home + (1.0 - form_away)) * 50.0) + normalize_ratio((xg_home - xga_home) - (xg_away - xga_away), -3.0, 3.0) * 0.5),
        "squad_availability": clamp_score(squad_availability * 100.0),
        "xg_rolling_10": normalize_ratio(xg_roll_diff, -2.0, 2.0),
        "market_value": normalize_ratio(market_value_delta_pct, -100.0, 100.0),
        "odds_movement": normalize_ratio(odds_movement, -1.0, 1.0),
        "h2h_recent": normalize_ratio(h2h_ratio, 0.0, 1.0),
        "standing_motivation": motivation_score,
        "social_sentiment": normalize_ratio(social_sentiment, -1.0, 1.0),
        "weather_pitch": clamp_score(weather_score),
        "pi_rating_delta": normalize_ratio(pi_delta, -120.0, 120.0),
    }
    return {key: round(clamp_score(value), 2) for key, value in criteria.items()}


def _extract_odds_movement_score(context: Mapping[str, Any]) -> float:
    explicit = context.get("odds_movement")
    if explicit is not None:
        return max(-1.0, min(1.0, _safe_float(explicit)))
    opening = _safe_float(context.get("opening_odd"), 0.0)
    closing = _safe_float(context.get("closing_odd"), 0.0)
    if opening <= 0 or closing <= 0:
        return 0.0
    movement_pct = ((opening - closing) / opening) * 100.0
    return max(-1.0, min(1.0, movement_pct / 20.0))


def analyze_match(match_context: Mapping[str, Any], confidence_threshold: float = 60.0) -> Dict[str, Any]:
    criteria_scores = build_criteria_scores(match_context)

    pi_delta_raw = _safe_float(match_context.get("pi_rating_delta"), 0.0)
    pi_delta_norm = max(-1.0, min(1.0, pi_delta_raw / 200.0))
    form_home = _clamp_probability(
        _safe_float(match_context.get("home_form_score"), _safe_float(match_context.get("form_points_last6"), 9.0) / 18.0)
    )
    form_away = _clamp_probability(_safe_float(match_context.get("away_form_score"), 0.5))

    xg_home = max(0.0, _safe_float(match_context.get("home_attack_xg"), 1.2))
    xg_away = max(0.0, _safe_float(match_context.get("away_attack_xg"), 1.1))
    xga_home = max(0.0, _safe_float(match_context.get("home_defense_xg"), 1.2))
    xga_away = max(0.0, _safe_float(match_context.get("away_defense_xg"), 1.2))

    odds_movement = _extract_odds_movement_score(match_context)
    squad_availability = _safe_float(match_context.get("squad_availability"), 1.0)
    if squad_availability > 1:
        squad_availability = _clamp_probability(squad_availability / 100.0)
    else:
        squad_availability = _clamp_probability(squad_availability)
    h2h_score = _clamp_probability(_safe_float(match_context.get("h2h_ratio"), 0.5))

    confidence_score = calculate_confidence_score(
        pi_rating_delta=pi_delta_norm,
        form_home=form_home,
        form_away=form_away,
        xg_home=xg_home,
        xg_away=xg_away,
        xga_home=xga_home,
        xga_away=xga_away,
        odds_movement=odds_movement,
        squad_availability=squad_availability,
        h2h_score=h2h_score,
        market_type=str(match_context.get("market_type") or "MS1"),
    )

    weighted_legacy_score = 0.0
    for key, weight in CRITERIA_WEIGHTS.items():
        weighted_legacy_score += clamp_score(float(criteria_scores.get(key, 50.0))) * weight
    weighted_legacy_score = round(weighted_legacy_score, 2)

    return {
        "confidence_score": confidence_score,
        "recommended": confidence_score >= confidence_threshold,
        "criteria_scores": criteria_scores,
        "confidence_breakdown": {
            "pi_rating_delta_norm": round(pi_delta_norm, 4),
            "form_home": round(form_home, 4),
            "form_away": round(form_away, 4),
            "xg_home": round(xg_home, 4),
            "xg_away": round(xg_away, 4),
            "xga_home": round(xga_home, 4),
            "xga_away": round(xga_away, 4),
            "odds_movement": round(odds_movement, 4),
            "squad_availability": round(squad_availability, 4),
            "h2h_score": round(h2h_score, 4),
            "legacy_weighted_score": weighted_legacy_score,
        },
    }
