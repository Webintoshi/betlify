from __future__ import annotations


def predict_xg(features: dict) -> tuple[float, float]:
    """Estimate home/away xG using weighted historical signals."""
    weights = {"goals": 0.40, "home_away": 0.30, "h2h": 0.15, "form": 0.15}

    home_xg = (
        weights["goals"] * (features["home_goals_avg"] + features["away_away_concede"]) / 2
        + weights["home_away"] * (features["home_home_goals"] + features["away_away_concede"]) / 2
        + weights["h2h"] * features["h2h_home_goals"]
        + weights["form"] * features["home_goals_avg"] * (0.5 + features["home_form"])
    )
    away_xg = (
        weights["goals"] * (features["away_goals_avg"] + features["home_home_concede"]) / 2
        + weights["home_away"] * (features["away_away_goals"] + features["home_home_concede"]) / 2
        + weights["h2h"] * features["h2h_away_goals"]
        + weights["form"] * features["away_goals_avg"] * (0.5 + features["away_form"])
    )

    return round(home_xg, 4), round(away_xg, 4)
