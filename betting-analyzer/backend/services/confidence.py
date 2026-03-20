from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def confidence_score(
    match_data: Dict[str, Any],
    probabilities: Dict[str, float],
    bookmaker_odds: List[Dict[str, Any]],
) -> Tuple[float, Dict[str, float]]:
    score = 0.0
    reasons: Dict[str, float] = {}

    home = match_data.get("home_team_stats", {}) or {}
    away = match_data.get("away_team_stats", {}) or {}
    h2h = match_data.get("h2h", {}) or {}

    home_last6 = home.get("last6", []) or []
    away_last6 = away.get("last6", []) or []

    home_form_pts = min(len(home_last6), 6) * (30.0 / 12.0)
    away_form_pts = min(len(away_last6), 6) * (30.0 / 12.0)
    score += home_form_pts + away_form_pts
    reasons["form_data"] = round(home_form_pts + away_form_pts, 1)

    has_xg_home = bool(home.get("avg_xg_for") and home.get("avg_xg_against"))
    has_xg_away = bool(away.get("avg_xg_for") and away.get("avg_xg_against"))
    xg_bonus = (5.0 if has_xg_home else 0.0) + (5.0 if has_xg_away else 0.0)
    score += xg_bonus
    reasons["xg_data"] = round(xg_bonus, 1)

    h2h_matches = h2h.get("matches", []) or []
    h2h_pts = min(len(h2h_matches), 5) * 1.0
    score += h2h_pts
    reasons["h2h_data"] = round(h2h_pts, 1)

    ms1 = _safe_float(probabilities.get("MS1"))
    msx = _safe_float(probabilities.get("MSX"))
    ms2 = _safe_float(probabilities.get("MS2"))
    ms_drift = abs((ms1 + msx + ms2) - 1.0)
    ms_consistency = max(0.0, 10.0 - ms_drift * 100.0)
    score += ms_consistency
    reasons["ms_consistency"] = round(ms_consistency, 1)

    iy1 = _safe_float(probabilities.get("IY1"))
    iyx = _safe_float(probabilities.get("IYX"))
    iy2 = _safe_float(probabilities.get("IY2"))
    iy_drift = abs((iy1 + iyx + iy2) - 1.0)
    iy_consistency = max(0.0, 8.0 - iy_drift * 100.0)
    score += iy_consistency
    reasons["iy_consistency"] = round(iy_consistency, 1)

    lam_h = _safe_float(match_data.get("_lambda_home"), 1.5)
    lam_a = _safe_float(match_data.get("_lambda_away"), 1.2)
    lam_valid = (0.5 <= lam_h <= 3.5) and (0.5 <= lam_a <= 3.0)
    lambda_pts = 7.0 if lam_valid else 0.0
    score += lambda_pts
    reasons["lambda_valid"] = round(lambda_pts, 1)

    n_books = len(bookmaker_odds)
    if n_books >= 8:
        book_pts = 20.0
    elif n_books >= 5:
        book_pts = 15.0
    elif n_books >= 3:
        book_pts = 10.0
    elif n_books >= 1:
        book_pts = 5.0
    else:
        book_pts = 0.0
    score += book_pts
    reasons["bookmaker_depth"] = round(book_pts, 1)

    has_sharp = any(
        str(item.get("book", "")).lower() in {"pinnacle", "sbo", "betfair_exchange"}
        for item in bookmaker_odds
    )
    sharp_bonus = 5.0 if has_sharp else 0.0
    score += sharp_bonus
    reasons["sharp_book"] = round(sharp_bonus, 1)

    def form_variance(results: List[str]) -> float:
        mapping = {"W": 3, "D": 1, "L": 0}
        pts = [mapping.get(str(result).upper(), 0) for result in results]
        if len(pts) < 2:
            return 3.0
        mean = sum(pts) / len(pts)
        return sum((point - mean) ** 2 for point in pts) / len(pts)

    home_var = form_variance(home_last6)
    away_var = form_variance(away_last6)
    avg_var = (home_var + away_var) / 2.0
    form_consistency_pts = max(0.0, 15.0 - avg_var * 1.67)
    score += form_consistency_pts
    reasons["form_consistency"] = round(form_consistency_pts, 1)

    if not home.get("avg_goals_for"):
        score -= 5.0
    if not away.get("avg_goals_for"):
        score -= 5.0
    if len(home_last6) < 3:
        score -= 8.0
    if len(away_last6) < 3:
        score -= 8.0
    if n_books == 0:
        score -= 20.0

    final = round(max(0.0, min(score, 100.0)), 1)
    return final, reasons
