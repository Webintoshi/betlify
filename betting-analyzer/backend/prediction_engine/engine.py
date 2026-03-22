from __future__ import annotations

from typing import Any, Dict, Optional

from prediction_engine.config.markets import SUPPORTED_MARKETS, VALID_MARKETS
from prediction_engine.steps.step1_features import build_features
from prediction_engine.steps.step2_xg import predict_xg
from prediction_engine.steps.step3_dixon_coles import compute_probabilities
from prediction_engine.steps.step4_ml import ensemble
from prediction_engine.steps.step5_odds import check_line_movement, get_best_odd, remove_vig
from prediction_engine.steps.step6_drift import validate_drift
from prediction_engine.steps.step7_filters import apply_filters, compute_confidence
from prediction_engine.steps.step8_ev import compute_ev, ev_valid
from prediction_engine.steps.step9_stake import final_stake, kelly_stake


def run(
    match_data: Dict[str, Any],
    home_stats: Dict[str, Any],
    away_stats: Dict[str, Any],
    h2h: Dict[str, Any],
    bookmakers: list[dict],
    ml_probs: Optional[dict] = None,
    opening_odds: Optional[dict] = None,
) -> Dict[str, Any]:
    league = str(match_data.get("league", "default") or "default")

    features = build_features(home_stats, away_stats, h2h, league)
    home_xg, away_xg = predict_xg(features)

    dc_probs, lambdas = compute_probabilities(home_xg, away_xg, league)
    final_probs = ensemble(dc_probs, ml_probs)

    best_odds = {market: get_best_odd(market, bookmakers) for market in SUPPORTED_MARKETS}
    best_odds = {market: odd for market, odd in best_odds.items() if odd}
    no_vig = remove_vig(best_odds)

    drift_map = validate_drift(final_probs, no_vig)
    confidence = compute_confidence(
        home_stats,
        away_stats,
        h2h,
        final_probs,
        bookmakers,
        league,
        lambdas["home"],
        lambdas["away"],
    )

    results = []
    for market, cfg in VALID_MARKETS.items():
        prob = final_probs.get(market)
        odd = best_odds.get(market)
        if prob is None or odd is None:
            continue

        line_suspicious = check_line_movement(opening_odds.get(market) if opening_odds else None, odd)
        reject_reason = apply_filters(
            market,
            float(prob),
            float(odd),
            drift_map.get(market, {"valid": True, "reason": None}),
            line_suspicious,
            confidence,
            cfg,
        )

        ev = compute_ev(float(prob), float(odd))
        if reject_reason is None:
            ev_ok, ev_reason = ev_valid(market, ev)
            if not ev_ok:
                reject_reason = ev_reason

        kelly_pct = kelly_stake(float(prob), float(odd), confidence) if reject_reason is None else 0.0
        stake = final_stake(kelly_pct, confidence) if reject_reason is None else None

        results.append(
            {
                "market": market,
                "probability": round(float(prob), 4),
                "odd": round(float(odd), 3),
                "ev": ev,
                "ev_pct": f"+{round(ev * 100, 1)}%" if ev > 0 else f"{round(ev * 100, 1)}%",
                "kelly_pct": kelly_pct,
                "stake": stake,
                "recommended": reject_reason is None,
                "reject_reason": reject_reason,
                "drift": drift_map.get(market, {}).get("drift"),
                "drift_reason": drift_map.get(market, {}).get("reason"),
                "market_prob": no_vig.get(market),
                "suspicious_high_ev": ev > 0.80,
            }
        )

    recommended = [row for row in results if row["recommended"]]
    best_market = max(recommended, key=lambda row: row["ev"] * row["kelly_pct"]) if recommended else None

    return {
        "confidence_score": confidence,
        "lambda": lambdas,
        "recommended_market": best_market,
        "all_markets": sorted(results, key=lambda row: row["ev"], reverse=True),
        "probabilities": final_probs,
        "meta": {
            "ml_active": ml_probs is not None,
            "model": "Dixon-Coles v3" + (" + ML" if ml_probs else ""),
        },
    }
