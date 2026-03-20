from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from proxy_pool import ProxyPool, mask_proxy

logger = logging.getLogger("sofascore_collector")

BASE_URL = "https://api.sofascore.com/api/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_RATE_INTERVAL_SECONDS = 1.2

HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.sofascore.com/",
    "Accept": "application/json",
}

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent.parent / ".env")
load_dotenv(BASE_DIR.parent / ".env", override=True)

SOFASCORE_COOKIE = os.getenv("SOFASCORE_COOKIE", "").strip()
if SOFASCORE_COOKIE:
    HEADERS["Cookie"] = SOFASCORE_COOKIE


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = -1.0) -> float:
    try:
        if value is None:
            return fallback
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return fallback


def _fractional_to_decimal(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    if "/" not in text:
        parsed = _safe_float(text, fallback=-1.0)
        return round(parsed, 4) if parsed > 0 else None
    left, right = text.split("/", 1)
    numerator = _safe_float(left, fallback=-1.0)
    denominator = _safe_float(right, fallback=-1.0)
    if numerator < 0 or denominator <= 0:
        return None
    return round((numerator / denominator) + 1.0, 4)


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _extract_threshold(value: str) -> Optional[float]:
    match = re.search(r"([+-]?\d+(?:[.,]\d+)?)", str(value))
    if not match:
        return None
    try:
        return round(float(match.group(1).replace(",", ".")), 1)
    except ValueError:
        return None


def _threshold_suffix(threshold: float) -> str:
    return str(int(threshold)) if float(threshold).is_integer() else str(threshold)


def _is_halftime_market(market_name: str) -> bool:
    marker = _normalize_text(market_name)
    return any(
        token in marker
        for token in ["1st half", "first half", "halftime", "half-time", "ilk yari", "iy"]
    )


def _map_market_key(market_name: str, choice_name: str) -> Optional[str]:
    market = _normalize_text(market_name)
    choice = _normalize_text(choice_name)
    is_ht = _is_halftime_market(market_name)

    if any(token in market for token in ["1x2", "match winner", "full time result", "winner"]):
        if choice in {"1", "home"}:
            return "IY1" if is_ht else "MS1"
        if choice in {"x", "draw"}:
            return "IYX" if is_ht else "MSX"
        if choice in {"2", "away"}:
            return "IY2" if is_ht else "MS2"

    if "both teams to score" in market or "btts" in market:
        if choice in {"yes", "var"}:
            return "KG_VAR"
        if choice in {"no", "yok"}:
            return "KG_YOK"

    if any(token in market for token in ["over/under", "total goals", "goals over/under"]):
        threshold = _extract_threshold(choice) or _extract_threshold(market)
        if threshold is None:
            return None
        if threshold not in {0.5, 1.5, 2.5, 3.5, 4.5}:
            return None
        is_over = ("over" in choice) or choice.startswith("o")
        is_under = ("under" in choice) or choice.startswith("u")
        if not is_over and not is_under:
            return None
        prefix = "IY" if is_ht else "MS"
        return f"{prefix}_{'O' if is_over else 'U'}{_threshold_suffix(threshold)}"

    if "handicap" in market:
        signed = _extract_threshold(choice)
        if signed is None:
            signed = _extract_threshold(market)
        if signed is None:
            return None
        if abs(signed) not in {0.5, 1.0, 1.5, 2.0, 2.5}:
            return None
        if signed > 0:
            return f"HCP_+{_threshold_suffix(abs(signed))}"
        return f"HCP_-{_threshold_suffix(abs(signed))}"

    return None


def _extract_score(value: Dict[str, Any], side: str) -> Optional[int]:
    score = value.get(f"{side}Score")
    if not isinstance(score, dict):
        return None
    for key in ("current", "display", "normaltime"):
        if score.get(key) is not None:
            try:
                return int(score.get(key))
            except (TypeError, ValueError):
                continue
    return None


def _extract_halftime_score(value: Dict[str, Any], side: str) -> Optional[int]:
    score = value.get(f"{side}Score")
    if not isinstance(score, dict):
        return None
    for key in ("period1", "firstHalf"):
        if score.get(key) is not None:
            try:
                return int(score.get(key))
            except (TypeError, ValueError):
                continue
    return None


class SofaScoreCollectorService:
    def __init__(self) -> None:
        self._rate_lock = asyncio.Lock()
        self._last_request_ts = 0.0
        self._min_interval = DEFAULT_RATE_INTERVAL_SECONDS
        self.proxy_pool = ProxyPool.from_env()

    async def _respect_rate_limit(self) -> None:
        async with self._rate_lock:
            now = monotonic()
            elapsed = now - self._last_request_ts
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_ts = monotonic()

    async def _fetch_json(self, path: str, retries: int = 3) -> Optional[Dict[str, Any]]:
        url = f"{BASE_URL}{path}"
        for attempt in range(1, retries + 1):
            await self._respect_rate_limit()
            proxy = self.proxy_pool.next()
            try:
                async with httpx.AsyncClient(
                    headers=HEADERS,
                    timeout=DEFAULT_TIMEOUT_SECONDS,
                    proxy=proxy,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(url)
            except Exception as exc:
                logger.warning(
                    "SofaScore request failed path=%s attempt=%s proxy=%s err=%s",
                    path,
                    attempt,
                    mask_proxy(proxy),
                    exc,
                )
                if attempt < retries:
                    await asyncio.sleep(0.8 * attempt)
                continue

            if response.status_code == 403:
                logger.warning(
                    "SofaScore 403 path=%s attempt=%s proxy=%s",
                    path,
                    attempt,
                    mask_proxy(proxy),
                )
                return None
            if response.status_code == 429:
                logger.warning("SofaScore 429 path=%s attempt=%s", path, attempt)
                await asyncio.sleep(60)
                continue
            if response.status_code != 200:
                logger.warning("SofaScore HTTP %s path=%s", response.status_code, path)
                if attempt < retries:
                    await asyncio.sleep(0.8 * attempt)
                continue

            try:
                payload = response.json()
            except ValueError:
                logger.warning("SofaScore JSON parse failed path=%s", path)
                payload = None
            if isinstance(payload, dict):
                return payload
            return None
        return None

    async def fetch_matches_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        payload = await self._fetch_json(f"/sport/football/scheduled-events/{date_str}")
        if not isinstance(payload, dict):
            return []
        events = payload.get("events")
        return events if isinstance(events, list) else []

    async def fetch_match_detail(self, event_id: int) -> Optional[Dict[str, Any]]:
        return await self._fetch_json(f"/event/{event_id}")

    async def fetch_match_odds(self, event_id: int) -> Dict[str, Any]:
        payload = await self._fetch_json(f"/event/{event_id}/odds/1/all")
        return payload if isinstance(payload, dict) else {}

    def parse_odds(self, odds_data: Dict[str, Any]) -> Dict[str, float]:
        parsed: Dict[str, float] = {}
        markets = odds_data.get("markets")
        if not isinstance(markets, list):
            return parsed

        for market in markets:
            if not isinstance(market, dict):
                continue
            market_name = str(market.get("name") or market.get("marketName") or "")
            choices = market.get("choices")
            if not isinstance(choices, list):
                continue
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                choice_name = str(choice.get("name") or choice.get("choiceName") or "")
                odd_value = choice.get("odd") or choice.get("decimalValue") or choice.get("value")
                decimal = _safe_float(odd_value, fallback=-1.0)
                if decimal <= 0:
                    decimal_from_fractional = _fractional_to_decimal(choice.get("fractionalValue"))
                    decimal = decimal_from_fractional if decimal_from_fractional is not None else -1.0
                if decimal <= 0:
                    continue

                raw_label = f"{market_name}:{choice_name}".strip(":")
                if raw_label:
                    parsed[raw_label] = round(decimal, 4)

                mapped_key = _map_market_key(market_name, choice_name)
                if mapped_key and mapped_key not in parsed:
                    parsed[mapped_key] = round(decimal, 4)

        return parsed

    async def collect_historical(self, days_back: int = 15) -> List[Dict[str, Any]]:
        total_days = max(1, min(int(days_back), 90))
        today = datetime.now(timezone.utc).date()
        collected: List[Dict[str, Any]] = []

        for offset in range(1, total_days + 1):
            date_str = (today - timedelta(days=offset)).isoformat()
            events = await self.fetch_matches_by_date(date_str)
            if not events:
                continue

            for event in events:
                if not isinstance(event, dict):
                    continue
                status = event.get("status") if isinstance(event.get("status"), dict) else {}
                if str(status.get("type") or "").lower() != "finished":
                    continue

                event_id = _safe_int(event.get("id"))
                if event_id <= 0:
                    continue

                detail = await self.fetch_match_detail(event_id)
                merged = detail if isinstance(detail, dict) else event
                home_score = _extract_score(merged, "home")
                away_score = _extract_score(merged, "away")
                if home_score is None or away_score is None:
                    continue
                ht_home = _extract_halftime_score(merged, "home")
                ht_away = _extract_halftime_score(merged, "away")

                odds_payload = await self.fetch_match_odds(event_id)
                odds = self.parse_odds(odds_payload)
                total_goals = home_score + away_score
                result = "H" if home_score > away_score else "A" if away_score > home_score else "D"
                tournament = event.get("tournament") if isinstance(event.get("tournament"), dict) else {}
                unique_tournament = (
                    tournament.get("uniqueTournament")
                    if isinstance(tournament.get("uniqueTournament"), dict)
                    else {}
                )
                home_team = event.get("homeTeam") if isinstance(event.get("homeTeam"), dict) else {}
                away_team = event.get("awayTeam") if isinstance(event.get("awayTeam"), dict) else {}

                collected.append(
                    {
                        "event_id": event_id,
                        "date": date_str,
                        "home_team": str(home_team.get("name") or ""),
                        "away_team": str(away_team.get("name") or ""),
                        "home_score": home_score,
                        "away_score": away_score,
                        "ht_home": ht_home,
                        "ht_away": ht_away,
                        "total_goals": total_goals,
                        "result": result,
                        "tournament": str(unique_tournament.get("name") or tournament.get("name") or ""),
                        "odds": odds,
                    }
                )

            logger.info(
                "SofaScore historical date=%s finished_matches=%s",
                date_str,
                len([row for row in collected if row.get("date") == date_str]),
            )

        logger.info("SofaScore historical collection completed matches=%s days=%s", len(collected), total_days)
        return collected


_collector_service: Optional[SofaScoreCollectorService] = None


def get_service() -> SofaScoreCollectorService:
    global _collector_service
    if _collector_service is None:
        _collector_service = SofaScoreCollectorService()
    return _collector_service
