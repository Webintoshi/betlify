from __future__ import annotations

from prediction_engine.config.markets import MAX_DRIFT


def validate_drift(model_probs: dict, no_vig_probs: dict) -> dict:
    result = {}
    for market, model_prob in model_probs.items():
        market_prob = no_vig_probs.get(market)
        if market_prob is None:
            result[market] = {"valid": True, "reason": None}
            continue

        drift = abs(float(model_prob) - float(market_prob))
        max_drift = float(MAX_DRIFT.get(market, 0.18))
        valid = drift <= max_drift
        result[market] = {
            "valid": valid,
            "drift": round(drift, 4),
            "reason": None if valid else f"Drift {round(drift * 100, 1)}% > max {round(max_drift * 100, 1)}%",
        }
    return result
