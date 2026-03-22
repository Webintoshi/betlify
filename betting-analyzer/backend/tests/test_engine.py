from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from prediction_engine.engine import run

MOCK_MATCH = {
    "match_id": "test-001",
    "league": "Premier League",
}

HOME_STATS = {
    "last6": ["W", "W", "D", "W", "L", "W"],
    "avg_xg_for": 1.72,
    "avg_xg_against": 1.10,
    "avg_goals_for": 1.80,
    "avg_goals_against": 1.05,
    "home_avg_goals_for": 2.10,
    "home_avg_goals_against": 1.0,
}

AWAY_STATS = {
    "last6": ["L", "D", "L", "W", "L", "D"],
    "avg_xg_for": 0.98,
    "avg_xg_against": 1.55,
    "avg_goals_for": 1.05,
    "avg_goals_against": 1.70,
    "away_avg_goals_for": 0.90,
    "away_avg_goals_against": 1.65,
}

H2H = {
    "avg_home_goals": 1.9,
    "avg_away_goals": 0.8,
    "matches": [{"home": 2, "away": 0}, {"home": 1, "away": 1}],
}

BOOKMAKERS = [
    {
        "book": "betfair_exchange",
        "MS1": 1.92,
        "MSX": 3.55,
        "MS2": 4.80,
        "MS_O2.5": 1.85,
        "MS_U2.5": 1.97,
        "MS_O1.5": 1.28,
        "KG_VAR": 1.75,
        "KG_YOK": 2.10,
        "IY1": 2.20,
        "IYX": 2.50,
        "IY2": 4.20,
    }
]


if __name__ == "__main__":
    result = run(
        match_data=MOCK_MATCH,
        home_stats=HOME_STATS,
        away_stats=AWAY_STATS,
        h2h=H2H,
        bookmakers=BOOKMAKERS,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    probs = result["probabilities"]
    ms_sum = probs["MS1"] + probs["MSX"] + probs["MS2"]
    iy_sum = probs["IY1"] + probs["IYX"] + probs["IY2"]

    assert abs(ms_sum - 1.0) < 0.01, f"MS toplam hata: {ms_sum}"
    assert abs(iy_sum - 1.0) < 0.01, f"IY toplam hata: {iy_sum}"

    for row in result["all_markets"]:
        if row["recommended"]:
            assert row["ev"] <= 0.22, f"EV cok yuksek: {row['market']} {row['ev']}"

    print("\nTum testler gecti")
    print(f"Confidence: {result['confidence_score']}")
    print(f"Oneri: {result['recommended_market']}")
