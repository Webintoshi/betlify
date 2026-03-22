from __future__ import annotations

from prediction_engine.config.settings import MAX_BANKROLL_PCT


def kelly_stake(prob: float, odd: float, confidence: float) -> float:
    b = float(odd) - 1.0
    if b <= 0 or float(prob) <= 0:
        return 0.0

    full_kelly = (b * float(prob) - (1 - float(prob))) / b
    fraction = 0.30 if confidence >= 75 else 0.25 if confidence >= 65 else 0.15
    return round(max(0.0, full_kelly * fraction * 100), 2)


def final_stake(kelly_pct: float, confidence: float, bankroll: float = 1000.0) -> dict:
    kelly_stake_amount = bankroll * (float(kelly_pct) / 100)
    max_pct = MAX_BANKROLL_PCT * (float(confidence) / 70)
    final = round(min(kelly_stake_amount, bankroll * max_pct), 2)
    return {
        "units": round(final / (bankroll * 0.01), 2),
        "final_stake": final,
        "stake_pct": round(final / bankroll * 100, 2),
    }
