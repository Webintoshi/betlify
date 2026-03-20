from __future__ import annotations

from typing import Dict

from config_markets import EV_THRESHOLDS, FRACTIONAL_KELLY, MIN_KELLY_PCT, VALID_MARKETS
from services.odds_processor import validate_odd, validate_prob


def fractional_kelly(prob: float, odd: float, fraction: float = FRACTIONAL_KELLY) -> float:
    b = float(odd) - 1.0
    if b <= 0 or float(prob) <= 0:
        return 0.0
    q = 1.0 - float(prob)
    full_kelly = (b * float(prob) - q) / b
    return round(max(0.0, full_kelly * float(fraction) * 100.0), 2)


def compute_ev(prob: float, odd: float) -> float:
    return round(float(prob) * float(odd) - 1.0, 5)


def is_suspicious_ev(market: str, ev: float) -> bool:
    threshold = EV_THRESHOLDS.get(market, {"min": 0.03, "max": 0.25})
    return not (float(threshold["min"]) <= float(ev) <= float(threshold["max"]))


def _reject(market: str, prob: float, odd: float, reason: str) -> Dict[str, object]:
    return {
        "market": market,
        "market_type": market,
        "probability": round(float(prob), 4),
        "odd": round(float(odd), 3) if odd else None,
        "ev": compute_ev(float(prob), float(odd)) if odd else None,
        "ev_pct": None,
        "kelly_pct": 0.0,
        "recommended": False,
        "suspicious_high_ev": True,
        "reject_reason": reason,
    }


def evaluate_market(
    market: str,
    our_prob: float,
    best_odd: float,
) -> Dict[str, object]:
    cfg = VALID_MARKETS.get(market, {})

    if not validate_prob(market, our_prob, cfg):
        return _reject(market, our_prob, best_odd, "Probability out of expected range")
    if not validate_odd(market, best_odd, cfg):
        return _reject(market, our_prob, best_odd, "Odd out of valid range")

    ev = compute_ev(our_prob, best_odd)
    if is_suspicious_ev(market, ev):
        threshold = EV_THRESHOLDS.get(market, {"min": 0.03, "max": 0.25})
        return _reject(
            market,
            our_prob,
            best_odd,
            (
                f"EV {round(ev * 100, 1)}% outside realistic range "
                f"[{round(float(threshold['min']) * 100, 1)}% - "
                f"{round(float(threshold['max']) * 100, 1)}%]"
            ),
        )

    kelly = fractional_kelly(our_prob, best_odd)
    if kelly < MIN_KELLY_PCT:
        return _reject(market, our_prob, best_odd, f"Kelly too low ({kelly}%)")

    return {
        "market": market,
        "market_type": market,
        "probability": round(float(our_prob), 4),
        "odd": round(float(best_odd), 3),
        "ev": ev,
        "ev_pct": f"+{round(ev * 100, 1)}%",
        "kelly_pct": kelly,
        "recommended": True,
        "suspicious_high_ev": False,
        "reject_reason": None,
    }
