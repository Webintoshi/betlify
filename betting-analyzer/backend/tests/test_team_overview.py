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

    def _get_team_row(self, team_id: str):  # type: ignore[override]
        return {"id": team_id, "league": "Trendyol S?per Lig"}

    def _get_cached_team_profile_row(self, *, team_id: str = "", sofascore_team_id: int = 0):  # type: ignore[override]
        return {
            "updated_at": "2026-03-23T00:00:00+00:00",
            "payload": {
                "team": {
                    "primaryUniqueTournament": {
                        "id": 679,
                        "name": "UEFA Europa League",
                    }
                }
            },
        }

    async def get_latest_tournament_season_id(self, tournament_id: int):  # type: ignore[override]
        return {
            52: 61629,
            96: 61631,
            679: 61628,
        }.get(tournament_id, 61627)

    async def _request(self, endpoint: str, params=None, ttl_seconds: int = 600):  # type: ignore[override]
        if endpoint.endswith("/events/last/0"):
            return {
                "events": [
                    {
                        "id": 1,
                        "startTimestamp": 1774224000,
                        "tournament": {"uniqueTournament": {"id": 96, "name": "T?rkiye Kupas?"}},
                        "season": {"id": 61631, "year": "2025/26"},
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
                        "tournament": {"uniqueTournament": {"id": 52, "name": "Trendyol S?per Lig"}},
                        "season": {"id": 61629, "year": "2025/26"},
                    },
                    {
                        "id": 4,
                        "startTimestamp": 1774915200,
                        "tournament": {"uniqueTournament": {"id": 7, "name": ""}},
                        "season": {"id": 61630, "year": "2025/26"},
                    },
                ]
            }
        return None


class DummyRecentMatchesService(SofaScoreService):
    def __init__(self) -> None:
        super().__init__(supabase_client=None)
        self.supabase = None

    async def _request(self, endpoint: str, params=None, ttl_seconds: int = 600):  # type: ignore[override]
        if endpoint.endswith("/events/last/0"):
            return {
                "events": [
                    {
                        "id": 101,
                        "startTimestamp": 1771632000,
                        "status": {"type": "finished"},
                        "homeTeam": {"id": 40, "name": "Aston Villa"},
                        "awayTeam": {"id": 50, "name": "Chelsea"},
                        "homeScore": {"current": 1},
                        "awayScore": {"current": 0},
                        "tournament": {"uniqueTournament": {"id": 1, "name": "Premier League"}},
                    },
                    {
                        "id": 102,
                        "startTimestamp": 1773446400,
                        "status": {"type": "finished"},
                        "homeTeam": {"id": 60, "name": "Liverpool"},
                        "awayTeam": {"id": 40, "name": "Aston Villa"},
                        "homeScore": {"current": 1},
                        "awayScore": {"current": 2},
                        "tournament": {"uniqueTournament": {"id": 1, "name": "Premier League"}},
                    },
                    {
                        "id": 103,
                        "startTimestamp": 1774051200,
                        "status": {"type": "finished"},
                        "homeTeam": {"id": 40, "name": "Aston Villa"},
                        "awayTeam": {"id": 70, "name": "Tottenham"},
                        "homeScore": {"current": 0},
                        "awayScore": {"current": 0},
                        "tournament": {"uniqueTournament": {"id": 679, "name": "UEFA Europa League"}},
                    },
                    {
                        "id": 104,
                        "startTimestamp": 1774656000,
                        "status": {"type": "inprogress"},
                        "homeTeam": {"id": 40, "name": "Aston Villa"},
                        "awayTeam": {"id": 80, "name": "West Ham"},
                        "homeScore": {"current": 0},
                        "awayScore": {"current": 0},
                        "tournament": {"uniqueTournament": {"id": 1, "name": "Premier League"}},
                    },
                ]
            }
        return {"events": []}


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

    recent_service = DummyRecentMatchesService()
    recent_matches = asyncio.run(recent_service.get_team_recent_matches(40, limit=3))
    assert [row["date"][:10] for row in recent_matches] == ["2026-03-21", "2026-03-14", "2026-02-21"]
    assert [row["result"] for row in recent_matches] == ["D", "W", "W"]

    dummy = DummyTournamentService()
    tournaments = asyncio.run(dummy.resolve_team_active_tournaments("team-1", 40))
    assert len(tournaments) == 3
    assert tournaments[0]["tournament_id"] == 52
    assert tournaments[1]["tournament_id"] == 679
    assert tournaments[2]["tournament_id"] == 96
    assert all(str(row.get("resolved_tournament_name") or "").strip() for row in tournaments)
    assert len({(row["tournament_id"], row["season_id"]) for row in tournaments}) == len(tournaments)


if __name__ == "__main__":
    run_team_overview_tests()
    print("Team overview tests passed")
