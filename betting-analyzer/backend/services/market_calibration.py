from __future__ import annotations

from typing import Dict

MAX_DRIFT: Dict[str, float] = {
    "MS1": 0.15,
    "MSX": 0.18,
    "MS2": 0.15,
    "MS_O2.5": 0.18,
    "MS_U2.5": 0.18,
    "MS_O1.5": 0.16,
    "KG_VAR": 0.18,
    "KG_YOK": 0.18,
    "IY1": 0.18,
    "IYX": 0.18,
    "IY2": 0.18,
}


def remove_vig(odds_dict: Dict[str, float]) -> Dict[str, float]:
    """Remove bookmaker margin and return no-vig probabilities."""
    groups = [
        ["MS1", "MSX", "MS2"],
        ["IY1", "IYX", "IY2"],
        ["MS_O2.5", "MS_U2.5"],
        ["MS_O1.5", "MS_U1.5"],
        ["KG_VAR", "KG_YOK"],
    ]

    no_vig: Dict[str, float] = {}
    for group in groups:
        present = {key: float(odds_dict[key]) for key in group if key in odds_dict and float(odds_dict[key]) > 1.0}
        if not present:
            continue

        implied = {key: 1.0 / value for key, value in present.items()}
        total = sum(implied.values())
        if total <= 0:
            continue

        for key, value in implied.items():
            no_vig[key] = round(value / total, 6)

    return no_vig


def is_trustworthy(market: str, model_prob: float, market_no_vig_prob: float) -> Dict[str, object]:
    """Validate model-market drift for a single market."""
    drift = abs(float(model_prob) - float(market_no_vig_prob))
    max_drift = MAX_DRIFT.get(market, 0.18)
    valid = drift <= max_drift

    return {
        "valid": valid,
        "model_prob": round(float(model_prob), 4),
        "market_prob": round(float(market_no_vig_prob), 4),
        "drift": round(drift, 4),
        "drift_pct": f"{round(drift * 100, 1)}%",
        "reject_reason": None
        if valid
        else (
            f"Drift {round(drift * 100, 1)}% > max {round(max_drift * 100, 1)}% "
            f"(model:{round(float(model_prob) * 100, 1)}% != market:{round(float(market_no_vig_prob) * 100, 1)}%)"
        ),
    }


def validate_all(model_probs: Dict[str, float], bookmaker_odds: Dict[str, float]) -> Dict[str, Dict[str, object]]:
    """Validate all markets. Calibration is only a trust filter; it does not change EV probabilities."""
    no_vig = remove_vig(bookmaker_odds)
    results: Dict[str, Dict[str, object]] = {}

    for market, model_prob in model_probs.items():
        market_prob = no_vig.get(market)

        if market_prob is None:
            results[market] = {
                "valid": True,
                "model_prob": round(float(model_prob), 4),
                "market_prob": None,
                "drift": None,
                "drift_pct": None,
                "reject_reason": None,
                "note": "No market odds available",
            }
            continue

        results[market] = is_trustworthy(market, float(model_prob), float(market_prob))

    return results
