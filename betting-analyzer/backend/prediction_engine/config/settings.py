from __future__ import annotations

import re
import unicodedata

ENGINE_NAME = "Dixon"
ENGINE_MODEL_LABEL = "Dixon-Coles v3"
TRENDYOL_SUPER_LIG = "Trendyol S\u00fcper Lig"

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
    TRENDYOL_SUPER_LIG: 0.90,
    "default": 0.75,
}

RHO_BY_LEAGUE = {
    "Serie A": -0.18,
    "Ligue 1": -0.16,
    "Premier League": -0.13,
    "La Liga": -0.13,
    "Bundesliga": -0.10,
    "Eredivisie": -0.08,
    TRENDYOL_SUPER_LIG: -0.13,
    "default": -0.13,
}


def _repair_league_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "\\u" in text:
        try:
            text = text.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass
    if any(token in text for token in ("Ã", "Ä", "Å", "Ð", "Þ")):
        try:
            text = text.encode("latin1").decode("utf-8")
        except Exception:
            pass
    return text


def _compact_league_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", _repair_league_text(value).lower())
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_only)


_LEAGUE_KEY_ALIASES = {
    "premierleague": "Premier League",
    "laliga": "La Liga",
    "bundesliga": "Bundesliga",
    "seriea": "Serie A",
    "ligue1": "Ligue 1",
    "eredivisie": "Eredivisie",
    "trendyolsuperlig": TRENDYOL_SUPER_LIG,
    "superlig": TRENDYOL_SUPER_LIG,
    "turkiyesuperlig": TRENDYOL_SUPER_LIG,
    "turkeysuperlig": TRENDYOL_SUPER_LIG,
    "turkeysuperleague": TRENDYOL_SUPER_LIG,
    "superleagueturkey": TRENDYOL_SUPER_LIG,
}


def resolve_league_settings_key(league: str) -> str:
    text = _repair_league_text(league)
    if not text:
        return "default"
    compact = _compact_league_key(text)
    return _LEAGUE_KEY_ALIASES.get(compact, text)
