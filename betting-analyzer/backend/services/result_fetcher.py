from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from services.odds_api_io import OddsApiIo, get_client as get_odds_api_client

logger = logging.getLogger(__name__)


def _safe_int(value: Any, fallback: int = -1) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


class ResultFetcher:
    def __init__(self, *, odds_api_client: Optional[OddsApiIo] = None) -> None:
        self.odds_api = odds_api_client or get_odds_api_client()

    async def fetch_match_result(self, odds_api_event_id: int) -> Optional[Dict[str, Any]]:
        event_id = int(odds_api_event_id or 0)
        if event_id <= 0:
            return None
        try:
            payload = await self.odds_api.get_event_by_id(event_id, critical=True)
        except Exception:
            logger.exception("Result fetch failed. odds_api_event_id=%s", event_id)
            return None
        if not isinstance(payload, dict):
            return None
        status = str(payload.get("status") or "").strip().lower()
        scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
        home_score = _safe_int(scores.get("home"), fallback=-1)
        away_score = _safe_int(scores.get("away"), fallback=-1)
        if home_score < 0 or away_score < 0:
            return None
        finished = status in {"settled", "finished"}
        return {
            "status": "finished" if finished else status or "scheduled",
            "home_score": home_score,
            "away_score": away_score,
            "ht_home": None,
            "ht_away": None,
            "total_goals": home_score + away_score,
            "result": "H" if home_score > away_score else "A" if home_score < away_score else "D",
            "ht_result": None,
            "btts": home_score > 0 and away_score > 0,
            "finished": finished,
        }


_default_fetcher = ResultFetcher()


def get_service() -> ResultFetcher:
    return _default_fetcher
