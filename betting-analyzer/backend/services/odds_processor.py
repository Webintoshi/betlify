from __future__ import annotations

from typing import Dict, List, Optional

SHARP_PRIORITY = ["pinnacle", "sbo", "betfair_exchange", "matchbook"]
SOFT_BOOKS = ["bwin", "bet365", "unibet", "interwetten"]


def remove_vig(odds_dict: Dict[str, float]) -> Dict[str, float]:
    implied = {k: 1.0 / v for k, v in odds_dict.items() if v and float(v) > 1.0}
    total = sum(implied.values())
    if total == 0:
        return {}
    return {k: round(v / total, 6) for k, v in implied.items()}


def get_best_odd(market: str, bookmaker_odds: List[Dict[str, float]]) -> Optional[float]:
    for book_name in SHARP_PRIORITY:
        for entry in bookmaker_odds:
            if str(entry.get("book", "")).lower() == book_name and market in entry:
                value = float(entry[market])
                if value > 1.0:
                    return value
    all_odds = [float(entry[market]) for entry in bookmaker_odds if market in entry and float(entry[market]) > 1.0]
    if not all_odds:
        return None
    top3 = sorted(all_odds, reverse=True)[:3]
    return round(sum(top3) / len(top3), 3)


def validate_odd(_: str, odd: float, cfg: Dict[str, float]) -> bool:
    return float(cfg.get("min_odd", 1.0)) <= float(odd) <= float(cfg.get("max_odd", 99.0))


def validate_prob(_: str, prob: float, cfg: Dict[str, float]) -> bool:
    return float(cfg.get("min_prob", 0.0)) <= float(prob) <= float(cfg.get("max_prob", 1.0))
