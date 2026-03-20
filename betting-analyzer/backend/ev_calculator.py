from __future__ import annotations

from typing import Dict, Mapping, Any

SUPPORTED_MARKETS = [
    "MS1",
    "MSX",
    "MS2",
    "IY1",
    "IYX",
    "IY2",
    "IY_U0.5",
    "IY_O0.5",
    "IY_U1.5",
    "IY_O1.5",
    "IY_U2.5",
    "IY_O2.5",
    "IY_U3.5",
    "IY_O3.5",
    "MS_U0.5",
    "MS_O0.5",
    "MS_U1.5",
    "MS_O1.5",
    "MS_U2.5",
    "MS_O2.5",
    "MS_U3.5",
    "MS_O3.5",
    "KG_VAR",
    "KG_YOK",
    "HCP_-1",
    "HCP_-1.5",
    "HCP_+1",
    "HCP_+1.5",
]


def _normalize_probability(probability: float) -> float:
    value = float(probability)
    if value > 1:
        value /= 100.0
    return max(0.0, min(1.0, value))


def calculate_ev(probability: float, odd: float) -> float:
    normalized_probability = _normalize_probability(probability)
    odd_value = float(odd)
    if odd_value <= 0:
        return -1.0
    return (normalized_probability * odd_value) - 1.0


def evaluate_markets(
    market_probabilities: Mapping[str, float],
    market_odds: Mapping[str, float],
    confidence_score: float,
    confidence_threshold: float = 60.0,
) -> Dict[str, Any]:
    market_results = []
    can_recommend = confidence_score >= confidence_threshold

    for market in SUPPORTED_MARKETS:
        probability = market_probabilities.get(market)
        odd = market_odds.get(market)
        if probability is None or odd is None:
            continue

        ev = calculate_ev(probability=probability, odd=odd)
        market_results.append(
            {
                "market_type": market,
                "predicted_outcome": market,
                "probability": round(_normalize_probability(probability), 4),
                "odd": float(odd),
                "ev": round(ev, 4),
                "ev_percentage": round(ev * 100.0, 2),
                "recommended": bool(can_recommend and ev > 0),
            }
        )

    sorted_results = sorted(market_results, key=lambda item: item["ev"], reverse=True)
    best_market = sorted_results[0] if sorted_results else None

    if best_market and not can_recommend:
        best_market = {**best_market, "recommended": False}

    return {
        "confidence_score": round(confidence_score, 2),
        "confidence_threshold": confidence_threshold,
        "recommended": can_recommend and bool(best_market and best_market["ev"] > 0),
        "best_market": best_market,
        "all_markets": sorted_results,
    }
