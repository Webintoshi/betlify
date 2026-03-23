from __future__ import annotations

from prediction_engine.config.settings import LEAGUE_TRUST, resolve_league_settings_key


def build_features(home_stats: dict, away_stats: dict, h2h: dict, league: str) -> dict:
    resolved_league = resolve_league_settings_key(league)

    def form_score(results: list) -> float:
        mapping = {"W": 3, "D": 1, "L": 0}
        cleaned = [str(item).upper() for item in (results or [])]
        weights = [0.9**idx for idx in range(len(cleaned))]
        points = [mapping.get(item, 0) * weight for item, weight in zip(cleaned, weights)]
        max_points = sum(3 * weight for weight in weights)
        return round(sum(points) / max_points, 4) if max_points > 0 else 0.5

    return {
        "home_form": form_score(home_stats.get("last6", [])),
        "away_form": form_score(away_stats.get("last6", [])),
        "home_goals_avg": float(home_stats.get("avg_goals_for", 1.4) or 1.4),
        "away_goals_avg": float(away_stats.get("avg_goals_for", 1.1) or 1.1),
        "home_concede_avg": float(home_stats.get("avg_goals_against", 1.2) or 1.2),
        "away_concede_avg": float(away_stats.get("avg_goals_against", 1.3) or 1.3),
        "home_home_goals": float(home_stats.get("home_avg_goals_for", 1.5) or 1.5),
        "away_away_goals": float(away_stats.get("away_avg_goals_for", 1.0) or 1.0),
        "home_home_concede": float(home_stats.get("home_avg_goals_against", 1.1) or 1.1),
        "away_away_concede": float(away_stats.get("away_avg_goals_against", 1.4) or 1.4),
        "h2h_home_goals": float(h2h.get("avg_home_goals", 1.4) or 1.4),
        "h2h_away_goals": float(h2h.get("avg_away_goals", 1.1) or 1.1),
        "h2h_count": len(h2h.get("matches", [])),
        "league_trust": LEAGUE_TRUST.get(resolved_league, LEAGUE_TRUST["default"]),
        "league": resolved_league,
    }
