from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sofascore import SofaScoreService


class DummyTournamentService(SofaScoreService):
    def __init__(self) -> None:
        super().__init__(supabase_client=None)
        self.supabase = None

    def _get_cached_team_profile_row(self, *, team_id: str = "", sofascore_team_id: int = 0):  # type: ignore[override]
        return {
            "updated_at": "2026-03-23T00:00:00+00:00",
            "payload": {
                "team": {
                    "primaryUniqueTournament": {
                        "id": 17,
                        "name": "Premier League",
                    }
                }
            },
        }

    async def get_latest_tournament_season_id(self, tournament_id: int):  # type: ignore[override]
        return 61627 if tournament_id > 0 else None

    async def _request(self, endpoint: str, params=None, ttl_seconds: int = 600):  # type: ignore[override]
        if endpoint.endswith("/events/last/0"):
            return {
                "events": [
                    {
                        "id": 1,
                        "startTimestamp": 1774224000,
                        "tournament": {"uniqueTournament": {"id": 17, "name": "Premier League"}},
                        "season": {"id": 61627, "year": "2025/26"},
                    },
                    {
                        "id": 2,
                        "startTimestamp": 1774137600,
                        "tournament": {"uniqueTournament": {"id": 679, "name": "UEFA Europa League"}},
                        "season": {"id": 61628, "year": "2025/26"},
                    },
                ]
            }
        if endpoint.endswith("/events/next/0"):
            return {
                "events": [
                    {
                        "id": 3,
                        "startTimestamp": 1774828800,
                        "tournament": {"uniqueTournament": {"id": 52, "name": "Trendyol Süper Lig"}},
                        "season": {"id": 61629, "year": "2025/26"},
                    },
                    {
                        "id": 4,
                        "startTimestamp": 1774915200,
                        "tournament": {"uniqueTournament": {"id": 8, "name": "La Liga"}},
                        "season": {"id": 61630, "year": "2025/26"},
                    },
                ]
            }
        return None


def run_team_overview_tests() -> None:
    service = SofaScoreService(supabase_client=None)
    form = service.build_team_form(
        [
            {"result": "W"},
            {"result": "D"},
            {"result": "L"},
            {"result": "W"},
            {"result": "W"},
        ]
    )
    assert form["results"] == ["W", "D", "L", "W", "W"]
    assert form["points"] == 10
    assert form["wins"] == 3
    assert 0 <= form["score_pct"] <= 1

    categorized = service._categorize_team_overview_statistics(
        {
            "averageRating": 6.82,
            "goalsScored": 42,
            "shotsOnTarget": 4.4,
            "accuratePasses": 412,
            "tackles": 16,
            "yellowCards": 2,
        }
    )
    assert categorized["summary_stats"]["values"]["averageRating"] == 6.82
    assert categorized["summary_stats"]["values"]["goalsScored"] == 42
    assert categorized["attack_stats"]["values"]["shotsOnTarget"] == 4.4
    assert categorized["passing_stats"]["values"]["accuratePasses"] == 412
    assert categorized["defending_stats"]["values"]["tackles"] == 16
    assert categorized["other_stats"]["values"]["yellowCards"] == 2

    dummy = DummyTournamentService()
    tournaments = asyncio.run(dummy.resolve_team_active_tournaments("team-1", 40))
    assert len(tournaments) == 3
    assert tournaments[0]["tournament_id"] == 17
    assert len({(row["tournament_id"], row["season_id"]) for row in tournaments}) == len(tournaments)


if __name__ == "__main__":
    run_team_overview_tests()
    print("Team overview tests passed")
