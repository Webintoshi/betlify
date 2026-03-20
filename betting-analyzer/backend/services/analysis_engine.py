from __future__ import annotations

from typing import Any, Dict, List, Tuple

from config_markets import MIN_CONFIDENCE_SCORE, VALID_MARKETS
from services.dixon_coles import compute_ht_probs, compute_match_probs
from services.ev_engine import evaluate_market
from services.odds_processor import get_best_odd

W_FORM = 0.25
W_H2H = 0.15
W_HOME_AWAY = 0.20
W_XG = 0.20
W_POISSON = 0.20


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def build_lambda(match_data: Dict[str, Any]) -> Tuple[float, float, float, float]:
    home = match_data.get("home_team_stats", {}) or {}
    away = match_data.get("away_team_stats", {}) or {}

    def form_score(results: List[str]) -> float:
        mapping = {"W": 3, "D": 1, "L": 0}
        points = [mapping.get(str(item).upper(), 0) for item in (results or [])]
        return (sum(points) / (len(points) * 3)) if points else 0.5

    home_form = form_score(home.get("last6", []))
    away_form = form_score(away.get("last6", []))

    xg_home = _safe_float(home.get("avg_xg_for"), 1.4)
    xg_away = _safe_float(away.get("avg_xg_for"), 1.1)
    xg_def_h = _safe_float(home.get("avg_xg_against"), 1.2)
    xg_def_a = _safe_float(away.get("avg_xg_against"), 1.3)

    lam_xg_home = (xg_home + xg_def_a) / 2.0
    lam_xg_away = (xg_away + xg_def_h) / 2.0

    goal_home = _safe_float(home.get("avg_goals_for"), 1.5)
    goal_away = _safe_float(away.get("avg_goals_for"), 1.1)
    goal_def_h = _safe_float(home.get("avg_goals_against"), 1.2)
    goal_def_a = _safe_float(away.get("avg_goals_against"), 1.4)

    lam_goal_home = (goal_home + goal_def_a) / 2.0
    lam_goal_away = (goal_away + goal_def_h) / 2.0

    h2h = match_data.get("h2h", {}) or {}
    h2h_home = _safe_float(h2h.get("avg_home_goals"), lam_goal_home)
    h2h_away = _safe_float(h2h.get("avg_away_goals"), lam_goal_away)

    home_advantage = 1.08
    lam_home = home_advantage * (
        (W_XG * lam_xg_home)
        + (W_POISSON * lam_goal_home)
        + (W_H2H * h2h_home)
        + (W_FORM * (lam_goal_home * (0.5 + home_form)))
        + (W_HOME_AWAY * _safe_float(home.get("home_avg_goals_for"), lam_goal_home))
    )
    lam_away = (
        (W_XG * lam_xg_away)
        + (W_POISSON * lam_goal_away)
        + (W_H2H * h2h_away)
        + (W_FORM * (lam_goal_away * (0.5 + away_form)))
        + (W_HOME_AWAY * _safe_float(away.get("away_avg_goals_for"), lam_goal_away))
    )

    lam_home = max(0.3, min(lam_home, 4.5))
    lam_away = max(0.3, min(lam_away, 4.0))
    ht_lam_home = round(lam_home * 0.42, 4)
    ht_lam_away = round(lam_away * 0.42, 4)
    return round(lam_home, 4), round(lam_away, 4), ht_lam_home, ht_lam_away


def confidence_score(match_data: Dict[str, Any], probabilities: Dict[str, float], bookmaker_odds: List[Dict[str, Any]]) -> float:
    score = 50.0

    home_stats = match_data.get("home_team_stats", {}) or {}
    away_stats = match_data.get("away_team_stats", {}) or {}

    if len(home_stats.get("last6", [])) >= 5:
        score += 8
    if len(away_stats.get("last6", [])) >= 5:
        score += 8
    if (match_data.get("h2h", {}) or {}).get("matches"):
        score += 5
    if home_stats.get("avg_xg_for"):
        score += 7
    if away_stats.get("avg_xg_for"):
        score += 7

    if len(bookmaker_odds) >= 3:
        score += 5
    if len(bookmaker_odds) >= 6:
        score += 5

    ms_total = (
        _safe_float(probabilities.get("MS1"))
        + _safe_float(probabilities.get("MSX"))
        + _safe_float(probabilities.get("MS2"))
    )
    drift = abs(ms_total - 1.0)
    score -= drift * 30.0

    return round(max(0.0, min(score, 100.0)), 1)


def run_analysis(match_data: Dict[str, Any], bookmaker_odds: List[Dict[str, Any]]) -> Dict[str, Any]:
    lam_h, lam_a, ht_lam_h, ht_lam_a = build_lambda(match_data)
    ft_probs = compute_match_probs(lam_h, lam_a)
    ht_probs = compute_ht_probs(ht_lam_h, ht_lam_a)
    all_probs = {**ft_probs, **ht_probs}

    conf = confidence_score(match_data, all_probs, bookmaker_odds)

    results: List[Dict[str, Any]] = []
    for market in VALID_MARKETS:
        our_prob = all_probs.get(market)
        if our_prob is None:
            continue
        best_odd = get_best_odd(market, bookmaker_odds)
        if best_odd is None:
            continue
        evaluated = evaluate_market(market, float(our_prob), float(best_odd))
        results.append(evaluated)

    recommended = [item for item in results if bool(item.get("recommended"))]
    best = None
    if recommended and conf >= MIN_CONFIDENCE_SCORE:
        best = max(
            recommended,
            key=lambda row: _safe_float(row.get("ev")) * _safe_float(row.get("kelly_pct")),
        )

    if conf < MIN_CONFIDENCE_SCORE:
        for row in results:
            row["recommended"] = False
            row["reject_reason"] = f"Confidence too low ({conf})"
        best = None

    return {
        "match_id": match_data.get("match_id"),
        "confidence_score": conf,
        "lambda": {
            "home": lam_h,
            "away": lam_a,
            "ht_home": ht_lam_h,
            "ht_away": ht_lam_a,
        },
        "recommended_market": best,
        "ev": {"all_markets": results},
        "probabilities": all_probs,
        "meta": {
            "model": "Dixon-Coles v2.0",
            "kelly_fraction": 0.25,
            "bookmakers_used": len(bookmaker_odds),
            "markets_analyzed": len(results),
            "markets_valid": len(recommended),
        },
    }
