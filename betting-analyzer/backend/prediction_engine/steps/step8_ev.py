from __future__ import annotations

from prediction_engine.config.markets import EV_THRESHOLDS
from prediction_engine.config.settings import MIN_EDGE


def compute_ev(prob: float, odd: float) -> float:
    return round(float(prob) * float(odd) - 1.0, 5)


def ev_valid(market: str, ev: float) -> tuple[bool, str | None]:
    threshold = EV_THRESHOLDS.get(market, {"min": 0.05, "max": 0.22})
    min_ev = float(threshold["min"])
    max_ev = float(threshold["max"])

    if ev < min_ev:
        return False, f"EV {round(ev * 100, 1)}% < min {round(min_ev * 100, 1)}%"
    if ev > max_ev:
        return False, f"EV {round(ev * 100, 1)}% > max {round(max_ev * 100, 1)}%"
    if ev < MIN_EDGE:
        return False, f"Edge {round(ev * 100, 1)}% < min {MIN_EDGE * 100}%"
    return True, None
