from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

SUPPORTED_MARKETS = [
    "MS1",
    "MSX",
    "MS2",
    "IY1",
    "IYX",
    "IY2",
    "MS_O0.5",
    "MS_O1.5",
    "MS_O2.5",
    "MS_O3.5",
    "MS_O4.5",
    "MS_U0.5",
    "MS_U1.5",
    "MS_U2.5",
    "MS_U3.5",
    "IY_O0.5",
    "IY_O1.5",
    "IY_O2.5",
    "IY_U0.5",
    "IY_U1.5",
    "IY_U2.5",
    "KG_VAR",
    "KG_YOK",
    "HCP_-1",
    "HCP_-0.5",
    "HCP_+0.5",
    "HCP_+1",
    "HCP_+1.5",
    "HCP_+2",
    "HCP_+2.5",
]

HT_ODD_FROM_FT_MAP: Dict[str, str] = {
    "IY1": "MS1",
    "IYX": "MSX",
    "IY2": "MS2",
    "IY_O0.5": "MS_O1.5",
    "IY_O1.5": "MS_O2.5",
    "IY_O2.5": "MS_O3.5",
    "IY_U0.5": "MS_U1.5",
    "IY_U1.5": "MS_U2.5",
    "IY_U2.5": "MS_U3.5",
}


def _normalize_probability(probability: float) -> float:
    value = float(probability)
    if value > 1:
        value /= 100.0
    return max(0.0, min(1.0, value))


def calculate_ev(market_probability: float, bookmaker_odd: float) -> float:
    probability = _normalize_probability(market_probability)
    odd = float(bookmaker_odd)
    if odd <= 0:
        return -1.0
    return round((probability * odd) - 1.0, 4)


def kelly_criterion(probability: float, odd: float, fraction: float = 0.25) -> float:
    p = _normalize_probability(probability)
    decimal_odd = float(odd)
    if decimal_odd <= 1.0:
        return 0.0
    b = decimal_odd - 1.0
    q = 1.0 - p
    full_kelly = ((b * p) - q) / b
    if full_kelly <= 0:
        return 0.0
    return round(full_kelly * max(0.01, min(1.0, fraction)) * 100.0, 2)


def estimate_ht_odd_from_ft(ft_probability: float, market_type: str) -> float:
    _ = market_type
    probability = _normalize_probability(ft_probability)
    if probability <= 0:
        return -1.0
    fair_odd = 1.0 / probability
    estimated = fair_odd * 1.08
    return round(estimated, 2)


def _resolve_market_odd(
    market: str,
    market_probabilities: Mapping[str, float],
    market_odds: Mapping[str, float],
) -> tuple[Optional[float], str]:
    if market in market_odds and float(market_odds[market]) > 0:
        return float(market_odds[market]), "bookmaker"

    if market.startswith("IY"):
        ft_market = HT_ODD_FROM_FT_MAP.get(market)
        if ft_market:
            ft_probability = market_probabilities.get(ft_market, market_probabilities.get(market, 0.0))
            estimated_odd = estimate_ht_odd_from_ft(float(ft_probability or 0.0), market)
            if estimated_odd > 0:
                return estimated_odd, "estimated"

    return None, "missing"


def evaluate_markets(
    market_probabilities: Mapping[str, float],
    market_odds: Mapping[str, float],
    confidence_score: float,
    confidence_threshold: float = 60.0,
) -> Dict[str, Any]:
    market_results = []
    for market in SUPPORTED_MARKETS:
        probability = market_probabilities.get(market)
        if probability is None:
            continue
        odd, odd_source = _resolve_market_odd(market, market_probabilities, market_odds)
        if odd is None:
            continue

        probability_norm = _normalize_probability(float(probability))
        ev = calculate_ev(probability_norm, odd)
        recommended = ev > 0.05
        high_ev_flag = ev > 0.80
        kelly_pct = kelly_criterion(probability_norm, odd, fraction=0.25) if recommended else 0.0
        market_results.append(
            {
                "market": market,
                "market_type": market,
                "predicted_outcome": market,
                "probability": round(probability_norm, 6),
                "odd": round(float(odd), 4),
                "odd_source": odd_source,
                "ev": round(ev, 4),
                "ev_percentage": round(ev * 100.0, 2),
                "recommended": bool(recommended),
                "suspicious_high_ev": bool(high_ev_flag),
                "kelly_pct": float(kelly_pct),
                "kelly_note": f"Bankroll'unun %{kelly_pct} kadarini oynayin" if kelly_pct > 0 else "Oynama",
            }
        )

    sorted_results = sorted(market_results, key=lambda item: item["ev"], reverse=True)
    best_market = sorted_results[0] if sorted_results else None
    any_recommended = any(bool(item.get("recommended")) for item in sorted_results)
    effective_recommended = any_recommended and (confidence_score >= confidence_threshold)

    if best_market is not None:
        best_market = {
            **best_market,
            "recommended": bool(best_market.get("recommended", False)),
            "confidence_gate_passed": bool(confidence_score >= confidence_threshold),
        }

    return {
        "confidence_score": round(float(confidence_score), 2),
        "confidence_threshold": float(confidence_threshold),
        "recommended": bool(effective_recommended),
        "recommended_by_ev_only": bool(any_recommended),
        "best_market": best_market,
        "all_markets": sorted_results,
    }
