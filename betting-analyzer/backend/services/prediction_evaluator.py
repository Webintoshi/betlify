from __future__ import annotations

from typing import Any, Optional


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return fallback


def _normalize_market(market: str) -> str:
    value = str(market or "").strip().upper()
    aliases = {
        "H": "MS1",
        "D": "MSX",
        "A": "MS2",
        "SHARP_HOME": "MS1",
        "SOFASCORE_HOME_EDGE": "MS1",
        "SOFASCORE_AWAY_EDGE": "MS2",
        "SOFASCORE_BALANCED": "MSX",
    }
    return aliases.get(value, value)


def _extract_threshold(market: str, prefix: str) -> Optional[float]:
    if not market.startswith(prefix):
        return None
    token = market[len(prefix) :]
    token = token.replace("_", ".")
    return _safe_float(token, fallback=-1.0) if token else None


def evaluate_prediction(market: str, result: dict[str, Any]) -> Optional[bool]:
    market_norm = _normalize_market(market)
    if not market_norm:
        return None

    home_score = _safe_int(result.get("home_score"))
    away_score = _safe_int(result.get("away_score"))
    ht_home = _safe_int(result.get("ht_home"))
    ht_away = _safe_int(result.get("ht_away"))
    total = home_score + away_score

    ft_result = "H" if home_score > away_score else "A" if home_score < away_score else "D"
    ht_result = "H" if ht_home > ht_away else "A" if ht_home < ht_away else "D"

    if market_norm == "MS1":
        return ft_result == "H"
    if market_norm == "MSX":
        return ft_result == "D"
    if market_norm == "MS2":
        return ft_result == "A"

    if market_norm == "IY1":
        return ht_result == "H"
    if market_norm == "IYX":
        return ht_result == "D"
    if market_norm == "IY2":
        return ht_result == "A"

    if market_norm == "KG_VAR":
        return home_score > 0 and away_score > 0
    if market_norm == "KG_YOK":
        return home_score == 0 or away_score == 0

    ms_over = _extract_threshold(market_norm, "MS_O")
    if ms_over is not None and ms_over >= 0:
        return float(total) > ms_over
    ms_under = _extract_threshold(market_norm, "MS_U")
    if ms_under is not None and ms_under >= 0:
        return float(total) < ms_under

    ht_total = ht_home + ht_away
    iy_over = _extract_threshold(market_norm, "IY_O")
    if iy_over is not None and iy_over >= 0:
        return float(ht_total) > iy_over
    iy_under = _extract_threshold(market_norm, "IY_U")
    if iy_under is not None and iy_under >= 0:
        return float(ht_total) < iy_under

    if market_norm.startswith("HCP_"):
        handicap = _safe_float(market_norm.replace("HCP_", ""), fallback=999.0)
        if handicap == 999.0:
            return None
        if handicap < 0:
            return float(home_score) + handicap > float(away_score)
        return float(away_score) + handicap >= float(home_score)

    return None

