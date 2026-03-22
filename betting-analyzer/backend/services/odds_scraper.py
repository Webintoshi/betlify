
from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from dotenv import load_dotenv
from supabase import Client, create_client

from prediction_engine.config.markets import SUPPORTED_MARKETS
from services.odds_api_io import OddsApiIo, get_client as get_odds_api_client

logger = logging.getLogger("odds_scraper")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent.parent / ".env")
load_dotenv(BASE_DIR.parent / ".env", override=True)

SUPPORTED_MARKET_SET = set(SUPPORTED_MARKETS)


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = -1.0) -> float:
    try:
        if value is None:
            return fallback
        text = str(value).strip().replace(",", ".")
        if not text or text.lower() in {"n/a", "nan", "none"}:
            return fallback
        return float(text)
    except (TypeError, ValueError):
        return fallback


def _normalize_text(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    ascii_only = raw.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9 ]+", " ", ascii_only)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _parse_iso(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _chunked(values: Sequence[int], size: int) -> Iterable[Sequence[int]]:
    chunk_size = max(1, int(size))
    for index in range(0, len(values), chunk_size):
        yield values[index : index + chunk_size]


class OddsScraperService:
    def __init__(
        self,
        *,
        supabase_client: Optional[Client] = None,
        odds_api_client: Optional[OddsApiIo] = None,
    ) -> None:
        self.supabase = supabase_client or self._build_supabase_client()
        self.odds_api: OddsApiIo = odds_api_client or get_odds_api_client()

        self.min_depth = max(0.0, float(os.getenv("ODDS_API_MIN_DEPTH", "50") or 50.0))
        self.max_spread_pct = max(0.0, float(os.getenv("ODDS_API_MAX_SPREAD_PCT", "0.06") or 0.06))

        self._odds_table_available: Optional[bool] = None
        self._best_bet_column_available: Optional[bool] = None
        self._odds_api_event_column_available: Optional[bool] = None
        self._bookmaker_selection_checked = False

    @property
    def bookmaker_name(self) -> str:
        return self.odds_api.bookmaker or "Betfair Exchange"

    @property
    def bookmaker_key(self) -> str:
        return re.sub(r"\s+", "_", self.bookmaker_name.strip().lower())

    @staticmethod
    def _build_supabase_client() -> Optional[Client]:
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not supabase_url or not supabase_service_key or "BURAYA_" in supabase_service_key:
            return None
        try:
            return create_client(supabase_url, supabase_service_key)
        except Exception:
            logger.exception("Supabase client initialization failed.")
            return None

    def _has_column(self, table_name: str, column_name: str, cache_attr: str) -> bool:
        cached = getattr(self, cache_attr)
        if cached is not None:
            return bool(cached)
        if self.supabase is None:
            setattr(self, cache_attr, False)
            return False
        try:
            self.supabase.table(table_name).select(column_name).limit(1).execute()
            setattr(self, cache_attr, True)
            return True
        except Exception:
            setattr(self, cache_attr, False)
            return False

    def _odds_table_exists(self) -> bool:
        return self._has_column("odds", "id", "_odds_table_available")

    def _best_bet_column_exists(self) -> bool:
        return self._has_column("matches", "best_bet", "_best_bet_column_available")

    def _odds_api_event_column_exists(self) -> bool:
        return self._has_column("matches", "odds_api_event_id", "_odds_api_event_column_available")

    def odds_api_state(self) -> Dict[str, Any]:
        state = self.odds_api.quota_state()
        state["bookmaker_key"] = self.bookmaker_key
        state["min_depth"] = self.min_depth
        state["max_spread_pct"] = self.max_spread_pct
        return state

    def _resolve_match(self, match_id_or_event_id: str) -> Optional[Dict[str, Any]]:
        if self.supabase is None:
            return None
        normalized = str(match_id_or_event_id or "").strip()
        if not normalized:
            return None

        columns = ["id", "status", "match_date"]
        if self._odds_api_event_column_exists():
            columns.append("odds_api_event_id")
        select_clause = ",".join(columns)

        try:
            by_id = (
                self.supabase.table("matches")
                .select(select_clause)
                .eq("id", normalized)
                .limit(1)
                .execute()
            )
            if by_id.data:
                return by_id.data[0]
        except Exception:
            logger.exception("Match lookup by id failed. match_id=%s", normalized)

        if normalized.isdigit() and self._odds_api_event_column_exists():
            try:
                by_event = (
                    self.supabase.table("matches")
                    .select(select_clause)
                    .eq("odds_api_event_id", int(normalized))
                    .limit(1)
                    .execute()
                )
                if by_event.data:
                    return by_event.data[0]
            except Exception:
                logger.exception("Match lookup by odds_api_event_id failed. event_id=%s", normalized)
        return None

    def _load_match_rows(self, *, from_iso: str, to_iso: str) -> List[Dict[str, Any]]:
        if self.supabase is None:
            return []
        columns = ["id", "home_team_id", "away_team_id", "league", "match_date", "status", "ft_home", "ft_away"]
        if self._odds_api_event_column_exists():
            columns.append("odds_api_event_id")
        select_clause = ",".join(columns)
        try:
            rows = (
                self.supabase.table("matches")
                .select(select_clause)
                .gte("match_date", from_iso)
                .lte("match_date", to_iso)
                .order("match_date")
                .limit(5000)
                .execute()
                .data
                or []
            )
            return rows
        except Exception:
            logger.exception("Match rows query failed for event sync.")
            return []
    def _load_team_name_map(self, matches: Sequence[Dict[str, Any]]) -> Dict[str, str]:
        if self.supabase is None:
            return {}
        team_ids = sorted(
            {
                str(item.get("home_team_id") or "")
                for item in matches
                if item.get("home_team_id")
            }
            | {
                str(item.get("away_team_id") or "")
                for item in matches
                if item.get("away_team_id")
            }
        )
        if not team_ids:
            return {}
        try:
            rows = (
                self.supabase.table("teams")
                .select("id,name")
                .in_("id", team_ids)
                .execute()
                .data
                or []
            )
            return {str(row.get("id")): str(row.get("name") or "") for row in rows if row.get("id")}
        except Exception:
            logger.exception("Team name map query failed.")
            return {}

    @staticmethod
    def _league_similarity(match_league: str, event_league: str) -> float:
        left = set(_normalize_text(match_league).split())
        right = set(_normalize_text(event_league).split())
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        union = len(left | right)
        if union == 0:
            return 0.0
        return intersection / union

    def _match_score(
        self,
        *,
        match_row: Dict[str, Any],
        event_row: Dict[str, Any],
        team_name_map: Mapping[str, str],
    ) -> float:
        home_name = _normalize_text(team_name_map.get(str(match_row.get("home_team_id") or ""), ""))
        away_name = _normalize_text(team_name_map.get(str(match_row.get("away_team_id") or ""), ""))
        event_home = _normalize_text(event_row.get("home"))
        event_away = _normalize_text(event_row.get("away"))
        if not home_name or not away_name or not event_home or not event_away:
            return -1.0

        score = 0.0
        if home_name == event_home:
            score += 4.0
        elif home_name in event_home or event_home in home_name:
            score += 2.0

        if away_name == event_away:
            score += 4.0
        elif away_name in event_away or event_away in away_name:
            score += 2.0

        match_dt = _parse_iso(match_row.get("match_date"))
        event_dt = _parse_iso(event_row.get("date"))
        if match_dt and event_dt:
            diff_minutes = abs((match_dt - event_dt).total_seconds()) / 60.0
            if diff_minutes <= 20:
                score += 3.0
            elif diff_minutes <= 45:
                score += 2.0
            elif diff_minutes <= 90:
                score += 1.0
            elif diff_minutes > 180:
                return -1.0

        league_name = str(match_row.get("league") or "")
        event_league = str((event_row.get("league") or {}).get("name") or (event_row.get("league") or {}).get("slug") or "")
        score += self._league_similarity(league_name, event_league) * 2.0

        return score

    def _find_best_match(
        self,
        *,
        event_row: Dict[str, Any],
        candidate_rows: Sequence[Dict[str, Any]],
        team_name_map: Mapping[str, str],
        used_match_ids: set[str],
    ) -> Optional[Dict[str, Any]]:
        best_row: Optional[Dict[str, Any]] = None
        best_score = -1.0
        for row in candidate_rows:
            row_id = str(row.get("id") or "")
            if not row_id or row_id in used_match_ids:
                continue
            score = self._match_score(match_row=row, event_row=event_row, team_name_map=team_name_map)
            if score > best_score:
                best_score = score
                best_row = row
        if best_row is None:
            return None
        if best_score < 7.0:
            return None
        return best_row

    def _upsert_event_mapping(self, *, match_id: str, event_id: int) -> bool:
        if self.supabase is None or not self._odds_api_event_column_exists():
            return False
        try:
            self.supabase.table("matches").update({"odds_api_event_id": int(event_id)}).eq("id", match_id).execute()
            return True
        except Exception:
            logger.exception("odds_api_event_id update failed. match_id=%s event_id=%s", match_id, event_id)
            return False

    def _event_result_payload(self, event_row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        status_raw = str(event_row.get("status") or "").strip().lower()
        scores = event_row.get("scores") if isinstance(event_row.get("scores"), dict) else {}
        home_score = _safe_int(scores.get("home"), fallback=-1)
        away_score = _safe_int(scores.get("away"), fallback=-1)
        if home_score < 0 or away_score < 0:
            return None

        ht_home, ht_away = self._extract_ht_scores(event_row=event_row)

        finished = status_raw in {"settled", "finished"}
        payload = {
            "status": "finished" if finished else status_raw or "scheduled",
            "home_score": home_score,
            "away_score": away_score,
            "ht_home": ht_home,
            "ht_away": ht_away,
            "total_goals": home_score + away_score,
            "result": "H" if home_score > away_score else "A" if home_score < away_score else "D",
            "ht_result": None,
            "btts": home_score > 0 and away_score > 0,
            "finished": finished,
        }
        if ht_home is not None and ht_away is not None:
            payload["ht_result"] = "H" if ht_home > ht_away else "A" if ht_home < ht_away else "D"
        return payload

    @staticmethod
    def _extract_ht_scores(*, event_row: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
        scores = event_row.get("scores") if isinstance(event_row.get("scores"), dict) else {}

        direct_pairs: Sequence[Tuple[str, str]] = (
            ("ht_home", "ht_away"),
            ("home_ht", "away_ht"),
            ("homeHt", "awayHt"),
        )
        for home_key, away_key in direct_pairs:
            home = _safe_int(scores.get(home_key), fallback=-1)
            away = _safe_int(scores.get(away_key), fallback=-1)
            if home >= 0 and away >= 0:
                return home, away

        nested_keys: Sequence[str] = ("ht", "halfTime", "period1", "firstHalf")
        for key in nested_keys:
            node = scores.get(key)
            if isinstance(node, dict):
                home = _safe_int(node.get("home"), fallback=-1)
                away = _safe_int(node.get("away"), fallback=-1)
                if home >= 0 and away >= 0:
                    return home, away

        periods = event_row.get("periods")
        if isinstance(periods, dict):
            node = periods.get("period1") or periods.get("firstHalf")
            if isinstance(node, dict):
                home = _safe_int(node.get("home"), fallback=-1)
                away = _safe_int(node.get("away"), fallback=-1)
                if home >= 0 and away >= 0:
                    return home, away
        return None, None

    def _apply_settled_event_to_match(self, *, match_row: Dict[str, Any], event_row: Dict[str, Any]) -> bool:
        if self.supabase is None:
            return False
        result_payload = self._event_result_payload(event_row)
        if not result_payload or not bool(result_payload.get("finished")):
            return False

        match_id = str(match_row.get("id") or "")
        if not match_id:
            return False
        home_score = _safe_int(result_payload.get("home_score"), fallback=-1)
        away_score = _safe_int(result_payload.get("away_score"), fallback=-1)
        if home_score < 0 or away_score < 0:
            return False

        payload: Dict[str, Any] = {
            "status": "finished",
            "ft_home": home_score,
            "ft_away": away_score,
        }
        ht_home = result_payload.get("ht_home")
        ht_away = result_payload.get("ht_away")
        if isinstance(ht_home, int) and isinstance(ht_away, int):
            payload["ht_home"] = ht_home
            payload["ht_away"] = ht_away
        try:
            self.supabase.table("matches").update(payload).eq("id", match_id).execute()
            return True
        except Exception:
            logger.exception("Match settled score update failed. match_id=%s", match_id)
            return False

    async def sync_events(
        self,
        *,
        past_hours: int = 24,
        future_hours: int = 48,
        max_pages: int = 6,
    ) -> Dict[str, Any]:
        if self.supabase is None:
            return {"events": 0, "matched": 0, "linked": 0, "settled_updates": 0, "unmatched": 0}
        if not self._odds_api_event_column_exists():
            return {
                "events": 0,
                "matched": 0,
                "linked": 0,
                "settled_updates": 0,
                "unmatched": 0,
                "error": "matches.odds_api_event_id column not found",
            }

        now_utc = datetime.now(timezone.utc)
        from_iso = _to_rfc3339(now_utc - timedelta(hours=max(1, past_hours)))
        to_iso = _to_rfc3339(now_utc + timedelta(hours=max(1, future_hours)))

        if not self._bookmaker_selection_checked:
            selected = await self.odds_api.get_selected_bookmakers(critical=False)
            if isinstance(selected, dict):
                bookmaker_list = [str(item) for item in (selected.get("bookmakers") or [])]
                if self.bookmaker_name not in bookmaker_list:
                    logger.warning(
                        "OddsAPI secili bookmaker listesinde '%s' yok. selected=%s",
                        self.bookmaker_name,
                        bookmaker_list,
                    )
                else:
                    logger.info("OddsAPI bookmaker dogrulandi. selected=%s", bookmaker_list)
            self._bookmaker_selection_checked = True

        events = await self.odds_api.get_events_paginated(
            sport="football",
            status="pending,live,settled",
            bookmaker=self.bookmaker_name,
            from_iso=from_iso,
            to_iso=to_iso,
            page_size=500,
            max_pages=max(1, int(max_pages)),
            critical=False,
        )
        if not events:
            return {
                "events": 0,
                "matched": 0,
                "linked": 0,
                "settled_updates": 0,
                "unmatched": 0,
                "skipped_due_quota": self.odds_api.should_skip_non_critical(),
            }
        match_rows = self._load_match_rows(from_iso=from_iso, to_iso=to_iso)
        if not match_rows:
            return {
                "events": len(events),
                "matched": 0,
                "linked": 0,
                "settled_updates": 0,
                "unmatched": len(events),
            }

        team_name_map = self._load_team_name_map(match_rows)
        by_event_id: Dict[int, Dict[str, Any]] = {}
        for row in match_rows:
            event_id = _safe_int(row.get("odds_api_event_id"), fallback=0)
            if event_id > 0:
                by_event_id[event_id] = row

        matched = 0
        linked = 0
        settled_updates = 0
        unmatched = 0
        used_match_ids: set[str] = set()

        for event in events:
            event_id = _safe_int(event.get("id"), fallback=0)
            if event_id <= 0:
                continue
            matched_row = by_event_id.get(event_id)
            if matched_row is None:
                matched_row = self._find_best_match(
                    event_row=event,
                    candidate_rows=match_rows,
                    team_name_map=team_name_map,
                    used_match_ids=used_match_ids,
                )
                if matched_row is not None:
                    row_id = str(matched_row.get("id") or "")
                    if row_id and self._upsert_event_mapping(match_id=row_id, event_id=event_id):
                        linked += 1
                        by_event_id[event_id] = matched_row
            if matched_row is None:
                unmatched += 1
                logger.debug(
                    "OddsAPI event eslesmedi. event_id=%s home=%s away=%s date=%s",
                    event_id,
                    event.get("home"),
                    event.get("away"),
                    event.get("date"),
                )
                continue

            match_id = str(matched_row.get("id") or "")
            if match_id:
                used_match_ids.add(match_id)
            matched += 1
            if self._apply_settled_event_to_match(match_row=matched_row, event_row=event):
                settled_updates += 1

        logger.info(
            "OddsAPI events sync tamamlandi. events=%s matched=%s linked=%s settled_updates=%s unmatched=%s remaining=%s",
            len(events),
            matched,
            linked,
            settled_updates,
            unmatched,
            self.odds_api.requests_remaining,
        )
        return {
            "events": len(events),
            "matched": matched,
            "linked": linked,
            "settled_updates": settled_updates,
            "unmatched": unmatched,
            "quota": self.odds_api.quota_state(),
        }

    def _should_accept_quote(self, *, back: float, lay: Optional[float], depth_back: float) -> Tuple[bool, Optional[str], Optional[float]]:
        if back <= 1.0:
            return False, "invalid_back", None
        if depth_back < self.min_depth:
            return False, "low_liquidity", None
        spread_pct: Optional[float] = None
        if lay is not None and lay > 1.0 and back > 0:
            spread_pct = (lay - back) / back
            if spread_pct > self.max_spread_pct:
                return False, "wide_spread", spread_pct
        return True, None, spread_pct

    @staticmethod
    def _choose_best(existing: Optional[Dict[str, Any]], candidate: Dict[str, Any]) -> Dict[str, Any]:
        if existing is None:
            return candidate
        existing_depth = _safe_float(existing.get("depth"), fallback=0.0)
        candidate_depth = _safe_float(candidate.get("depth"), fallback=0.0)
        if candidate_depth > existing_depth:
            return candidate
        if candidate_depth == existing_depth:
            existing_odd = _safe_float(existing.get("odd"), fallback=0.0)
            candidate_odd = _safe_float(candidate.get("odd"), fallback=0.0)
            if candidate_odd > existing_odd:
                return candidate
        return existing

    @staticmethod
    def _depth_value(quote: Dict[str, Any], keys: Sequence[str]) -> float:
        for key in keys:
            value = _safe_float(quote.get(key), fallback=-1.0)
            if value >= 0:
                return value
        return 0.0

    def _record_candidate(
        self,
        *,
        parsed: Dict[str, Dict[str, Any]],
        rejects: Dict[str, int],
        market_key: str,
        back: float,
        lay: Optional[float],
        depth_back: float,
        source_market: str,
    ) -> None:
        if market_key not in SUPPORTED_MARKET_SET:
            return
        accepted, reason, spread_pct = self._should_accept_quote(back=back, lay=lay, depth_back=depth_back)
        if not accepted:
            rejects[reason or "rejected"] = rejects.get(reason or "rejected", 0) + 1
            return

        candidate = {
            "odd": round(back, 4),
            "lay": None if lay is None else round(lay, 4),
            "depth": round(depth_back, 2),
            "spread_pct": None if spread_pct is None else round(spread_pct, 6),
            "source_market": source_market,
        }
        parsed[market_key] = self._choose_best(parsed.get(market_key), candidate)

    def _parse_event_odds(self, event_payload: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, int]]:
        parsed: Dict[str, Dict[str, Any]] = {}
        rejects: Dict[str, int] = {}

        bookmakers = event_payload.get("bookmakers") if isinstance(event_payload.get("bookmakers"), dict) else {}
        market_rows: List[Dict[str, Any]] = []

        selected = bookmakers.get(self.bookmaker_name)
        if isinstance(selected, list):
            market_rows.extend(item for item in selected if isinstance(item, dict))
        else:
            rejects["bookmaker_missing"] = rejects.get("bookmaker_missing", 0) + 1
            return {}, rejects

        for market in market_rows:
            name_raw = str(market.get("name") or "")
            name = _normalize_text(name_raw)
            odds_rows = market.get("odds") if isinstance(market.get("odds"), list) else []
            for quote in odds_rows:
                if not isinstance(quote, dict):
                    continue
                if name == "ml":
                    self._record_candidate(parsed=parsed, rejects=rejects, market_key="MS1", back=_safe_float(quote.get("home"), fallback=-1.0), lay=_safe_float(quote.get("layHome"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthHome", "depthBackHome", "depthHomeBack"]), source_market=name_raw)
                    self._record_candidate(parsed=parsed, rejects=rejects, market_key="MSX", back=_safe_float(quote.get("draw"), fallback=-1.0), lay=_safe_float(quote.get("layDraw"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthDraw", "depthBackDraw", "depthDrawBack"]), source_market=name_raw)
                    self._record_candidate(parsed=parsed, rejects=rejects, market_key="MS2", back=_safe_float(quote.get("away"), fallback=-1.0), lay=_safe_float(quote.get("layAway"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthAway", "depthBackAway", "depthAwayBack"]), source_market=name_raw)
                    continue

                if name == "ml ht":
                    self._record_candidate(parsed=parsed, rejects=rejects, market_key="IY1", back=_safe_float(quote.get("home"), fallback=-1.0), lay=_safe_float(quote.get("layHome"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthHome", "depthBackHome", "depthHomeBack"]), source_market=name_raw)
                    self._record_candidate(parsed=parsed, rejects=rejects, market_key="IYX", back=_safe_float(quote.get("draw"), fallback=-1.0), lay=_safe_float(quote.get("layDraw"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthDraw", "depthBackDraw", "depthDrawBack"]), source_market=name_raw)
                    self._record_candidate(parsed=parsed, rejects=rejects, market_key="IY2", back=_safe_float(quote.get("away"), fallback=-1.0), lay=_safe_float(quote.get("layAway"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthAway", "depthBackAway", "depthAwayBack"]), source_market=name_raw)
                    continue

                if name == "both teams to score":
                    self._record_candidate(parsed=parsed, rejects=rejects, market_key="KG_VAR", back=_safe_float(quote.get("yes"), fallback=-1.0), lay=_safe_float(quote.get("layYes"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthYes", "depthOver", "depthBackYes"]), source_market=name_raw)
                    self._record_candidate(parsed=parsed, rejects=rejects, market_key="KG_YOK", back=_safe_float(quote.get("no"), fallback=-1.0), lay=_safe_float(quote.get("layNo"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthNo", "depthUnder", "depthBackNo"]), source_market=name_raw)
                    continue

                if name in {"totals", "totals ht"}:
                    line = round(_safe_float(quote.get("hdp"), fallback=-10.0), 1)
                    if line <= 0:
                        continue
                    is_ht = name == "totals ht"
                    valid_lines = {0.5, 1.5, 2.5} if is_ht else {0.5, 1.5, 2.5, 3.5, 4.5}
                    if line not in valid_lines:
                        continue
                    suffix = str(int(line)) if float(line).is_integer() else str(line)
                    over_key = f"{'IY' if is_ht else 'MS'}_O{suffix}"
                    under_key = f"{'IY' if is_ht else 'MS'}_U{suffix}"
                    self._record_candidate(parsed=parsed, rejects=rejects, market_key=over_key, back=_safe_float(quote.get("over"), fallback=-1.0), lay=_safe_float(quote.get("layOver"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthOver", "depthBackOver"]), source_market=name_raw)
                    self._record_candidate(parsed=parsed, rejects=rejects, market_key=under_key, back=_safe_float(quote.get("under"), fallback=-1.0), lay=_safe_float(quote.get("layUnder"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthUnder", "depthBackUnder"]), source_market=name_raw)
                    continue

                if name == "spread":
                    line = round(_safe_float(quote.get("hdp"), fallback=-99.0), 1)
                    if line == -0.5:
                        self._record_candidate(parsed=parsed, rejects=rejects, market_key="HCP_-0.5", back=_safe_float(quote.get("home"), fallback=-1.0), lay=_safe_float(quote.get("layHome"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthHome", "depthBackHome"]), source_market=name_raw)
                        self._record_candidate(parsed=parsed, rejects=rejects, market_key="HCP_+0.5", back=_safe_float(quote.get("away"), fallback=-1.0), lay=_safe_float(quote.get("layAway"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthAway", "depthBackAway"]), source_market=name_raw)
                    elif line == -1.0:
                        self._record_candidate(parsed=parsed, rejects=rejects, market_key="HCP_-1", back=_safe_float(quote.get("home"), fallback=-1.0), lay=_safe_float(quote.get("layHome"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthHome", "depthBackHome"]), source_market=name_raw)
                        self._record_candidate(parsed=parsed, rejects=rejects, market_key="HCP_+1", back=_safe_float(quote.get("away"), fallback=-1.0), lay=_safe_float(quote.get("layAway"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthAway", "depthBackAway"]), source_market=name_raw)
                    elif line == -1.5:
                        self._record_candidate(parsed=parsed, rejects=rejects, market_key="HCP_+1.5", back=_safe_float(quote.get("away"), fallback=-1.0), lay=_safe_float(quote.get("layAway"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthAway", "depthBackAway"]), source_market=name_raw)
                    elif line == -2.0:
                        self._record_candidate(parsed=parsed, rejects=rejects, market_key="HCP_+2", back=_safe_float(quote.get("away"), fallback=-1.0), lay=_safe_float(quote.get("layAway"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthAway", "depthBackAway"]), source_market=name_raw)
                    elif line == -2.5:
                        self._record_candidate(parsed=parsed, rejects=rejects, market_key="HCP_+2.5", back=_safe_float(quote.get("away"), fallback=-1.0), lay=_safe_float(quote.get("layAway"), fallback=-1.0), depth_back=self._depth_value(quote, ["depthAway", "depthBackAway"]), source_market=name_raw)

        odds = {
            market: float(values.get("odd", 0.0))
            for market, values in parsed.items()
            if float(values.get("odd", 0.0)) > 1.0
        }
        return odds, rejects

    def _upsert_odds_history(self, *, match_id: str, market: str, odd: float, is_finished: bool) -> None:
        if self.supabase is None:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        bookmaker = self.bookmaker_key
        try:
            existing = (
                self.supabase.table("odds_history")
                .select("id,opening_odd,current_odd")
                .eq("match_id", match_id)
                .eq("bookmaker", bookmaker)
                .eq("market_type", market)
                .limit(1)
                .execute()
            )
            rows = existing.data or []
            if rows:
                row = rows[0]
                opening = _safe_float(row.get("opening_odd") or row.get("current_odd"), fallback=odd)
                payload: Dict[str, Any] = {"opening_odd": opening, "current_odd": odd, "recorded_at": now_iso}
                if is_finished:
                    payload["closing_odd"] = odd
                self.supabase.table("odds_history").update(payload).eq("id", row["id"]).execute()
            else:
                self.supabase.table("odds_history").insert(
                    {
                        "match_id": match_id,
                        "market_type": market,
                        "bookmaker": bookmaker,
                        "opening_odd": odd,
                        "current_odd": odd,
                        "closing_odd": odd if is_finished else None,
                        "recorded_at": now_iso,
                    }
                ).execute()
        except Exception:
            logger.exception("odds_history upsert failed. match_id=%s market=%s", match_id, market)

    def _upsert_odds_snapshot(self, *, match_id: str, market: str, odd: float, ev: Optional[float]) -> None:
        if self.supabase is None or not self._odds_table_exists():
            return
        payload = {
            "match_id": match_id,
            "market": market,
            "odd": round(float(odd), 4),
            "ev": None if ev is None else round(float(ev), 6),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.supabase.table("odds").upsert(payload, on_conflict="match_id,market").execute()
        except Exception:
            logger.exception("odds table upsert failed. match_id=%s market=%s", match_id, market)
    def _save_best_bet(self, match_id: str, market_name: str) -> None:
        if self.supabase is None or not self._best_bet_column_exists() or not market_name:
            return
        try:
            self.supabase.table("matches").update({"best_bet": market_name}).eq("id", match_id).execute()
        except Exception:
            logger.exception("matches.best_bet update failed. match_id=%s", match_id)

    async def get_odds_for_match(self, match_id_or_event_id: str) -> Dict[str, float]:
        match_row = self._resolve_match(match_id_or_event_id)
        if not match_row:
            return {}

        match_id = str(match_row.get("id") or "")
        event_id = _safe_int(match_row.get("odds_api_event_id"), fallback=0)
        if not match_id:
            return {}
        if event_id <= 0:
            sync_result = await self.sync_events(past_hours=48, future_hours=72, max_pages=4)
            logger.debug("match odds icin event sync tetiklendi. result=%s", sync_result)
            match_row = self._resolve_match(match_id) or match_row
            event_id = _safe_int(match_row.get("odds_api_event_id"), fallback=0)
            if event_id <= 0:
                return {}

        payload = await self.odds_api.get_odds_single(event_id, bookmakers=self.bookmaker_name, critical=False)
        if not isinstance(payload, dict):
            return {}

        odds, rejects = self._parse_event_odds(payload)
        if not odds:
            logger.info("Odds parse bos dondu. match_id=%s event_id=%s rejects=%s", match_id, event_id, rejects)
            return {}

        is_finished = str(payload.get("status") or match_row.get("status") or "").strip().lower() in {"settled", "finished"}
        for market, odd in odds.items():
            self._upsert_odds_history(match_id=match_id, market=market, odd=odd, is_finished=is_finished)
            self._upsert_odds_snapshot(match_id=match_id, market=market, odd=odd, ev=None)
        return odds

    async def refresh_todays_matches(self, *, timezone_name: str = "Europe/Istanbul") -> Dict[str, Any]:
        if self.supabase is None:
            return {"processed_matches": 0, "updated_markets": 0}

        if self.odds_api.should_skip_non_critical():
            logger.warning("Odds refresh skip: remaining=%s", self.odds_api.requests_remaining)
            return {
                "processed_matches": 0,
                "updated_markets": 0,
                "skipped_due_quota": True,
                "quota": self.odds_api.quota_state(),
            }

        await self.sync_events(past_hours=24, future_hours=48, max_pages=4)

        from zoneinfo import ZoneInfo

        tz = ZoneInfo(timezone_name)
        now_tz = datetime.now(tz)
        today = now_tz.date().isoformat()
        tomorrow = (now_tz.date() + timedelta(days=1)).isoformat()

        try:
            query = (
                self.supabase.table("matches")
                .select("id,status,match_date,odds_api_event_id")
                .gte("match_date", f"{today}T00:00:00")
                .lte("match_date", f"{tomorrow}T23:59:59")
                .in_("status", ["scheduled", "live"])
            )
            if self._odds_api_event_column_exists():
                query = query.not_.is_("odds_api_event_id", "null")
            rows = query.order("match_date").execute().data or []
        except Exception:
            logger.exception("Today matches read failed for odds refresh.")
            return {"processed_matches": 0, "updated_markets": 0}

        by_event_id: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            event_id = _safe_int(row.get("odds_api_event_id"), fallback=0)
            if event_id > 0:
                by_event_id[event_id] = row

        if not by_event_id:
            return {"processed_matches": 0, "updated_markets": 0}

        processed_matches = 0
        updated_markets = 0
        reject_summary: Dict[str, int] = {}

        for chunk in _chunked(list(by_event_id.keys()), 10):
            if self.odds_api.should_skip_non_critical():
                logger.warning("Odds refresh reserve guard nedeniyle erken durduruldu.")
                break
            events = await self.odds_api.get_odds_multi(chunk, bookmakers=self.bookmaker_name, critical=False)
            if not events:
                continue

            for event in events:
                event_id = _safe_int(event.get("id"), fallback=0)
                match_row = by_event_id.get(event_id)
                if not match_row:
                    continue
                odds, rejects = self._parse_event_odds(event)
                for reason, count in rejects.items():
                    reject_summary[reason] = reject_summary.get(reason, 0) + count
                if not odds:
                    continue

                match_id = str(match_row.get("id") or "")
                if not match_id:
                    continue
                is_finished = str(event.get("status") or match_row.get("status") or "").lower() in {"settled", "finished"}
                for market, odd in odds.items():
                    self._upsert_odds_history(match_id=match_id, market=market, odd=odd, is_finished=is_finished)
                    self._upsert_odds_snapshot(match_id=match_id, market=market, odd=odd, ev=None)
                processed_matches += 1
                updated_markets += len(odds)

        logger.info(
            "Betfair odds refresh tamamlandi. processed_matches=%s updated_markets=%s rejects=%s remaining=%s",
            processed_matches,
            updated_markets,
            reject_summary,
            self.odds_api.requests_remaining,
        )
        return {
            "processed_matches": processed_matches,
            "updated_markets": updated_markets,
            "rejected": reject_summary,
            "quota": self.odds_api.quota_state(),
        }
    async def refresh_settled_results(self, *, lookback_hours: int = 48) -> Dict[str, Any]:
        if self.supabase is None:
            return {"scanned_matches": 0, "updated_matches": 0}
        if not self._odds_api_event_column_exists():
            return {"scanned_matches": 0, "updated_matches": 0, "error": "odds_api_event_id column missing"}

        now_utc = datetime.now(timezone.utc)
        from_iso = _to_rfc3339(now_utc - timedelta(hours=max(1, lookback_hours)))
        to_iso = _to_rfc3339(now_utc + timedelta(hours=6))

        try:
            match_rows = (
                self.supabase.table("matches")
                .select("id,status,match_date,odds_api_event_id,ft_home,ft_away")
                .not_.is_("odds_api_event_id", "null")
                .gte("match_date", from_iso)
                .lte("match_date", to_iso)
                .order("match_date")
                .limit(4000)
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("refresh_settled_results match query failed.")
            return {"scanned_matches": 0, "updated_matches": 0}

        if not match_rows:
            return {"scanned_matches": 0, "updated_matches": 0}

        settled_events = await self.odds_api.get_events_paginated(
            sport="football",
            status="settled",
            bookmaker=self.bookmaker_name,
            from_iso=from_iso,
            to_iso=to_iso,
            page_size=500,
            max_pages=6,
            critical=True,
        )
        by_event: Dict[int, Dict[str, Any]] = {
            _safe_int(item.get("id"), fallback=0): item
            for item in settled_events
            if _safe_int(item.get("id"), fallback=0) > 0
        }

        updated = 0
        missing_event_ids: List[int] = []
        for row in match_rows:
            event_id = _safe_int(row.get("odds_api_event_id"), fallback=0)
            if event_id <= 0:
                continue
            event = by_event.get(event_id)
            if event is None:
                missing_event_ids.append(event_id)
                continue
            if self._apply_settled_event_to_match(match_row=row, event_row=event):
                updated += 1

        for event_id in missing_event_ids[:10]:
            event = await self.odds_api.get_event_by_id(event_id, critical=True)
            if not isinstance(event, dict):
                continue
            if str(event.get("status") or "").lower() not in {"settled", "finished"}:
                continue
            row = next((item for item in match_rows if _safe_int(item.get("odds_api_event_id"), fallback=0) == event_id), None)
            if row and self._apply_settled_event_to_match(match_row=row, event_row=event):
                updated += 1

        logger.info(
            "OddsAPI settled reconcile tamamlandi. scanned=%s updated=%s missing=%s remaining=%s",
            len(match_rows),
            updated,
            len(missing_event_ids),
            self.odds_api.requests_remaining,
        )
        return {
            "scanned_matches": len(match_rows),
            "updated_matches": updated,
            "missing_events": len(missing_event_ids),
            "quota": self.odds_api.quota_state(),
        }

    def save_ev_rows(self, *, match_id: str, ev_result: Dict[str, Any]) -> None:
        if self.supabase is None:
            return

        all_markets = ev_result.get("all_markets", [])
        if isinstance(all_markets, list):
            for row in all_markets:
                if not isinstance(row, dict):
                    continue
                market = str(row.get("market_type") or "")
                odd = _safe_float(row.get("odd"), fallback=-1.0)
                if not market or odd <= 0:
                    continue
                ev_value = _safe_float(row.get("ev"), fallback=-999.0)
                self._upsert_odds_snapshot(
                    match_id=match_id,
                    market=market,
                    odd=odd,
                    ev=None if ev_value <= -900 else ev_value,
                )

        best_market = ev_result.get("best_market", {})
        if isinstance(best_market, dict):
            market_name = str(best_market.get("market_type") or "")
            if market_name:
                self._save_best_bet(match_id, market_name)

    async def close(self) -> None:
        return None


_default_service = OddsScraperService()


def get_service() -> OddsScraperService:
    return _default_service
