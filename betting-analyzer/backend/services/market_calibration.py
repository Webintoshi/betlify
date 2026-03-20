from __future__ import annotations

from typing import Any, Dict, List, Optional

MARKET_TRUST: Dict[str, float] = {
    "MS1": 0.60,
    "MSX": 0.55,
    "MS2": 0.60,
    "MS_O2.5": 0.50,
    "MS_U2.5": 0.50,
    "MS_O1.5": 0.45,
    "KG_VAR": 0.50,
    "KG_YOK": 0.50,
    "IY1": 0.55,
    "IYX": 0.55,
    "IY2": 0.55,
}

MAX_DRIFT: Dict[str, float] = {
    "MS1": 0.18,
    "MSX": 0.20,
    "MS2": 0.18,
    "MS_O2.5": 0.20,
    "MS_U2.5": 0.20,
    "MS_O1.5": 0.18,
    "KG_VAR": 0.20,
    "KG_YOK": 0.20,
    "IY1": 0.20,
    "IYX": 0.20,
    "IY2": 0.20,
}


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def remove_vig_single(odds_dict: Dict[str, float]) -> Dict[str, float]:
    groups: List[List[str]] = [
        ["MS1", "MSX", "MS2"],
        ["IY1", "IYX", "IY2"],
        ["MS_O2.5", "MS_U2.5"],
        ["MS_O1.5", "MS_U1.5"],
        ["KG_VAR", "KG_YOK"],
    ]
    no_vig: Dict[str, float] = {}
    for group in groups:
        present = {key: _safe_float(odds_dict[key], -1.0) for key in group if key in odds_dict and _safe_float(odds_dict[key], -1.0) > 1.0}
        if not present:
            continue
        implied = {key: (1.0 / odd) for key, odd in present.items()}
        total = sum(implied.values())
        if total <= 0:
            continue
        for key, value in implied.items():
            no_vig[key] = round(value / total, 6)
    return no_vig


def calibrate(market: str, model_prob: float, market_prob: float) -> Dict[str, Any]:
    trust = _safe_float(MARKET_TRUST.get(market), 0.55)
    drift = abs(_safe_float(model_prob) - _safe_float(market_prob))
    max_drift = _safe_float(MAX_DRIFT.get(market), 0.20)

    if drift > max_drift:
        return {
            "calibrated_prob": None,
            "model_prob": round(_safe_float(model_prob), 4),
            "market_prob": round(_safe_float(market_prob), 4),
            "drift": round(drift, 4),
            "is_valid": False,
            "reject_reason": (
                f"Model-market drift too high: "
                f"model={round(_safe_float(model_prob) * 100, 1)}% "
                f"market={round(_safe_float(market_prob) * 100, 1)}% "
                f"drift={round(drift * 100, 1)}% > max {round(max_drift * 100, 1)}%"
            ),
        }

    calibrated = ((1.0 - trust) * _safe_float(model_prob)) + (trust * _safe_float(market_prob))
    return {
        "calibrated_prob": round(calibrated, 5),
        "model_prob": round(_safe_float(model_prob), 4),
        "market_prob": round(_safe_float(market_prob), 4),
        "drift": round(drift, 4),
        "is_valid": True,
        "reject_reason": None,
    }


def calibrate_all(model_probs: Dict[str, float], bookmaker_odds: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    no_vig = remove_vig_single(bookmaker_odds)
    results: Dict[str, Dict[str, Any]] = {}

    for market, model_prob_raw in model_probs.items():
        model_prob = _safe_float(model_prob_raw)
        market_prob: Optional[float] = no_vig.get(market)
        if market_prob is None:
            results[market] = {
                "calibrated_prob": round(model_prob, 5),
                "model_prob": round(model_prob, 4),
                "market_prob": None,
                "drift": None,
                "is_valid": True,
                "reject_reason": None,
                "note": "No market odds — model only",
            }
            continue
        results[market] = calibrate(market, model_prob, _safe_float(market_prob))

    return results
