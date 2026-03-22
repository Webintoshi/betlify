from __future__ import annotations

SHARP_PRIORITY = ["betfair_exchange", "sbobet", "pinnacle"]


def get_best_odd(market: str, bookmakers: list[dict]) -> float | None:
    for preferred in SHARP_PRIORITY:
        for bookmaker in bookmakers:
            book_name = str(bookmaker.get("book", "")).strip().lower()
            odd = bookmaker.get(market)
            if book_name == preferred and odd and float(odd) > 1.0:
                return float(odd)

    all_odds = [
        float(bookmaker[market])
        for bookmaker in bookmakers
        if bookmaker.get(market) and float(bookmaker[market]) > 1.0
    ]
    if not all_odds:
        return None
    top = sorted(all_odds, reverse=True)[:3]
    return round(sum(top) / len(top), 3)


def remove_vig(odds: dict) -> dict:
    groups = [
        ["MS1", "MSX", "MS2"],
        ["IY1", "IYX", "IY2"],
        ["MS_O2.5", "MS_U2.5"],
        ["MS_O1.5", "MS_U1.5"],
        ["KG_VAR", "KG_YOK"],
    ]
    no_vig = {}
    for group in groups:
        present = {key: float(odds[key]) for key in group if key in odds and float(odds[key]) > 1.0}
        if not present:
            continue
        implied = {key: 1.0 / price for key, price in present.items()}
        total = sum(implied.values())
        for key, value in implied.items():
            no_vig[key] = round(value / total, 6)
    return no_vig


def check_line_movement(opening: float | None, current: float | None) -> bool:
    if opening is None or current is None:
        return False
    opening_v = float(opening)
    current_v = float(current)
    if opening_v <= 0 or current_v <= 0:
        return False
    return abs(current_v - opening_v) / opening_v > 0.15
