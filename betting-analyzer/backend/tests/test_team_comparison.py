from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from team_comparison.confidence_service import TeamComparisonConfidenceService
from team_comparison.feature_service import TeamComparisonFeatureService
from team_comparison.models import TeamComparisonRequest
from team_comparison.opponent_adjustment_service import TeamComparisonOpponentAdjustmentService
from team_comparison.robots import ANARobot, BMARobot, GMARobot
from team_comparison.scenario_service import TeamComparisonScenarioService


def build_snapshot() -> dict:
    return {
        "request": {"home_team_id": "home-1", "away_team_id": "away-1", "scope": "primary_current", "data_window": 10},
        "generated_at": "2026-03-24T10:00:00+00:00",
        "home": {
            "team": {"id": "home-1", "name": "Galatasaray", "league": "Trendyol Süper Lig", "country": "Türkiye", "market_value": 210.0},
            "overview_rows": [
                {
                    "tournament_id": 52,
                    "season_id": 61629,
                    "tournament_name": "Trendyol Süper Lig",
                    "season_name": "2025/26",
                    "summary_stats": {"values": {"averageRating": 6.95}},
                    "attack_stats": {"values": {"shotsOnTarget": 5.4, "corners": 5.8}},
                    "passing_stats": {"values": {"accuratePassesPercentage": 84}},
                    "defending_stats": {"values": {"tackles": 16}},
                    "other_stats": {"values": {"yellowCards": 2.3}},
                }
            ],
            "primary_overview": {
                "tournament_id": 52,
                "season_id": 61629,
                "tournament_name": "Trendyol Süper Lig",
                "season_name": "2025/26",
                "summary_stats": {"values": {"averageRating": 6.95}},
                "attack_stats": {"values": {"shotsOnTarget": 5.4, "corners": 5.8}},
                "passing_stats": {"values": {"accuratePassesPercentage": 84}},
                "defending_stats": {"values": {"tackles": 16}},
                "other_stats": {"values": {"yellowCards": 2.3}},
            },
            "season_stats_rows": [],
            "top_players": [
                {"player_name": "A", "rating": 7.4, "minutes_played": 2100},
                {"player_name": "B", "rating": 7.1, "minutes_played": 1800},
            ],
            "standings_rows": [{"position": 1, "played": 28, "points": 71, "goal_diff": 42}],
            "matches": [
                {"match_id": f"h{i}", "match_date": f"2026-03-{24-i:02d}T18:00:00+00:00", "league": "Trendyol Süper Lig", "is_home": i % 2 == 0, "goals_scored": 2 if i < 4 else 1, "goals_conceded": 1 if i % 3 else 0, "xg_for": 1.8 if i < 5 else None, "xg_against": 0.9 if i < 5 else None, "shots": 14, "shots_on_target": 6, "possession": 56, "result": "W" if i < 6 else "D", "ht_goals_scored": 1, "ht_goals_conceded": 0, "second_half_goals_scored": 1, "second_half_goals_conceded": 1 if i % 3 else 0}
                for i in range(1, 11)
            ],
            "recent_matches": [],
            "form_last_ten": {"results": ["W", "W", "D", "W", "W", "W", "D", "W", "L", "W"]},
            "overview_metrics": {"corners": 5.8, "yellow_cards": 2.3, "red_cards": 0.1, "pass_accuracy": 84, "big_chances": 2.2, "counterattacks": 1.6, "average_rating": 6.95, "goals_per_match": 2.0, "possession": 56},
            "injuries": [{"player_name": "Kilit Oyuncu", "status": "injured"}],
            "injury_count": 1,
        },
        "away": {
            "team": {"id": "away-1", "name": "Beşiktaş JK", "league": "Trendyol Süper Lig", "country": "Türkiye", "market_value": 150.0},
            "overview_rows": [
                {
                    "tournament_id": 52,
                    "season_id": 61629,
                    "tournament_name": "Trendyol Süper Lig",
                    "season_name": "2025/26",
                    "summary_stats": {"values": {"averageRating": 6.71}},
                    "attack_stats": {"values": {"corners": 4.8}},
                    "passing_stats": {"values": {"accuratePassesPercentage": 79}},
                    "defending_stats": {"values": {"tackles": 14}},
                    "other_stats": {"values": {"yellowCards": 2.7}},
                }
            ],
            "primary_overview": {
                "tournament_id": 52,
                "season_id": 61629,
                "tournament_name": "Trendyol Süper Lig",
                "season_name": "2025/26",
                "summary_stats": {"values": {"averageRating": 6.71}},
                "attack_stats": {"values": {"corners": 4.8}},
                "passing_stats": {"values": {"accuratePassesPercentage": 79}},
                "defending_stats": {"values": {"tackles": 14}},
                "other_stats": {"values": {"yellowCards": 2.7}},
            },
            "season_stats_rows": [],
            "top_players": [{"player_name": "C", "rating": 7.0, "minutes_played": 1900}],
            "standings_rows": [{"position": 4, "played": 28, "points": 54, "goal_diff": 18}],
            "matches": [
                {"match_id": f"a{i}", "match_date": f"2026-03-{24-i:02d}T18:00:00+00:00", "league": "Trendyol Süper Lig", "is_home": i % 2 == 1, "goals_scored": 1 if i < 6 else 0, "goals_conceded": 1 if i < 7 else 2, "xg_for": None, "xg_against": None, "shots": 10, "shots_on_target": 3, "possession": 49, "result": "W" if i < 4 else "D" if i < 7 else "L", "ht_goals_scored": 0, "ht_goals_conceded": 0, "second_half_goals_scored": 1, "second_half_goals_conceded": 1}
                for i in range(1, 11)
            ],
            "recent_matches": [],
            "form_last_ten": {"results": ["W", "W", "D", "D", "W", "L", "D", "L", "W", "L"]},
            "overview_metrics": {"corners": 4.8, "yellow_cards": 2.7, "red_cards": 0.2, "pass_accuracy": 79, "big_chances": 1.5, "counterattacks": 1.8, "average_rating": 6.71, "goals_per_match": 1.2, "possession": 49},
            "injuries": [],
            "injury_count": 0,
        },
        "h2h": {"matches": [], "summary": {"home_wins": 3, "away_wins": 1, "draws": 1}},
        "fixture_context": {"has_fixture_context": False},
        "common_tournaments": [{"tournament_id": 52, "season_id": 61629, "tournament_name": "Trendyol Süper Lig", "season_name": "2025/26"}],
        "cross_league": False,
        "data_gaps": [],
        "freshness": {
            "home_team_data_last_fetched_at": "2026-03-24T09:00:00+00:00",
            "away_team_data_last_fetched_at": "2026-03-24T09:00:00+00:00",
            "home_profile_last_fetched_at": "2026-03-24T09:00:00+00:00",
            "away_profile_last_fetched_at": "2026-03-24T09:00:00+00:00",
        },
    }


def run_tests() -> None:
    request = TeamComparisonRequest(home_team_id="home-1", away_team_id="away-1")
    request.validate()
    try:
        TeamComparisonRequest(home_team_id="same", away_team_id="same").validate()
        raise AssertionError("same team validation must fail")
    except ValueError:
        pass

    snapshot = build_snapshot()
    features = TeamComparisonFeatureService().build(snapshot, request)
    assert features["away"]["proxy_xg_used"] is True
    assert features["home"]["proxy_xg_used"] is False

    adjusted = TeamComparisonOpponentAdjustmentService().apply(features, snapshot)
    scenarios = TeamComparisonScenarioService().run(snapshot, adjusted, request)
    total_1x2 = scenarios["one_x_two"]["home"] + scenarios["one_x_two"]["draw"] + scenarios["one_x_two"]["away"]
    assert abs(total_1x2 - 1.0) < 0.03

    confidence = TeamComparisonConfidenceService().score(snapshot, adjusted, scenarios)
    assert 0 <= confidence["confidence_score"] <= 100

    robots = [
        ANARobot().render(snapshot, adjusted, scenarios, confidence),
        BMARobot().render(snapshot, adjusted, scenarios, confidence),
        GMARobot().render(snapshot, adjusted, scenarios, confidence),
    ]
    banned = ["kesin", "garanti", "bu bahsi oyna"]
    for robot in robots:
        text = " ".join(block["body"] for block in robot["report_blocks"]).lower()
        for token in banned:
            assert token not in text
        assert robot["methodology"]
        assert len(robot["key_signals"]) >= 2
        assert len(robot["model_breakdown"]) >= 4

    power_differences = {round(robot["summary_card"]["power_difference_pct"], 2) for robot in robots}
    assert len(power_differences) >= 2


if __name__ == "__main__":
    run_tests()
    print("Team comparison tests passed")
