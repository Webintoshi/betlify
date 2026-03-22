from __future__ import annotations

FRACTIONAL_KELLY = 0.25
MAX_BANKROLL_PCT = 0.015
MIN_CONFIDENCE = 58.0
MIN_EDGE = 0.05
MIN_KELLY = 1.5
MAX_ODD = 8.0
MIN_ODD = 1.35
HOME_ADVANTAGE = 1.08
HT_LAMBDA_RATIO = 0.42

LEAGUE_TRUST = {
    "Premier League": 1.00,
    "La Liga": 1.00,
    "Bundesliga": 0.98,
    "Serie A": 0.97,
    "Ligue 1": 0.95,
    "Super Lig": 0.90,
    "default": 0.75,
}

RHO_BY_LEAGUE = {
    "Serie A": -0.18,
    "Ligue 1": -0.16,
    "Premier League": -0.13,
    "La Liga": -0.13,
    "Bundesliga": -0.10,
    "Eredivisie": -0.08,
    "default": -0.13,
}
