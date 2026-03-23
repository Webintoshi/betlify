from __future__ import annotations

from prediction_engine.config.settings import LEAGUE_TRUST, MIN_CONFIDENCE, resolve_league_settings_key


def compute_confidence(
    home_stats: dict,
    away_stats: dict,
    h2h: dict,
    probs: dict,
    bookmakers: list,
    league: str,
    lam: float,
    mu: float,
) -> float:
    resolved_league = resolve_league_settings_key(league)
    score = 0.0

    home_last6 = home_stats.get("last6", []) or []
    away_last6 = away_stats.get("last6", []) or []

    score += min(len(home_last6), 6) * 2.5
    score += min(len(away_last6), 6) * 2.5
    score += 5 if home_stats.get("avg_xg_for") else 0
    score += 5 if away_stats.get("avg_xg_for") else 0
    score += min(len(h2h.get("matches", []) or []), 5)

    ms_drift = abs(float(probs.get("MS1", 0)) + float(probs.get("MSX", 0)) + float(probs.get("MS2", 0)) - 1.0)
    iy_drift = abs(float(probs.get("IY1", 0)) + float(probs.get("IYX", 0)) + float(probs.get("IY2", 0)) - 1.0)
    score += max(0, 10 - ms_drift * 100)
    score += max(0, 7 - iy_drift * 100)
    score += 3 if (0.5 <= float(lam) <= 3.5 and 0.5 <= float(mu) <= 3.0) else 0

    book_count = len(bookmakers)
    score += 20 if book_count >= 8 else 15 if book_count >= 5 else 10 if book_count >= 3 else 5 if book_count >= 1 else 0
    score += 5 if any(str(book.get("book", "")).lower() in {"betfair_exchange", "sbobet", "pinnacle"} for book in bookmakers) else 0

    score *= LEAGUE_TRUST.get(resolved_league, LEAGUE_TRUST["default"])

    if len(home_last6) < 3:
        score -= 10
    if len(away_last6) < 3:
        score -= 10
    if book_count == 0:
        score -= 25

    return round(max(0.0, min(score, 100.0)), 1)


def apply_filters(
    market: str,
    prob: float,
    odd: float,
    drift_info: dict,
    line_suspicious: bool,
    confidence: float,
    cfg: dict,
) -> str | None:
    if not drift_info.get("valid", True):
        return str(drift_info.get("reason") or "Drift check failed")
    if line_suspicious:
        return "Suspicious line movement"
    if not (float(cfg["min_prob"]) <= float(prob) <= float(cfg["max_prob"])):
        return "Probability out of range"
    if not (float(cfg["min_odd"]) <= float(odd) <= float(cfg["max_odd"])):
        return "Odd out of valid range"
    if float(confidence) < MIN_CONFIDENCE:
        return f"Confidence too low ({confidence})"
    return None
