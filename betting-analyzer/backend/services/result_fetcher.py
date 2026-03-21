from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sofascore import SofaScoreService, get_service as get_sofascore_service

logger = logging.getLogger(__name__)


class ResultFetcher:
    def __init__(self, *, sofascore_service: Optional[SofaScoreService] = None) -> None:
        self.sofascore = sofascore_service or get_sofascore_service()

    async def fetch_match_result(self, sofascore_id: int) -> Optional[Dict[str, Any]]:
        if int(sofascore_id or 0) <= 0:
            return None
        try:
            payload = await self.sofascore.get_event_result(int(sofascore_id))
        except Exception:
            logger.exception("Result fetch failed. sofascore_id=%s", sofascore_id)
            return None
        if not isinstance(payload, dict):
            return None
        return payload


_default_fetcher = ResultFetcher()


def get_service() -> ResultFetcher:
    return _default_fetcher

