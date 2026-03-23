from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from supabase import Client
from zoneinfo import ZoneInfo

from prediction_engine.config.markets import SUPPORTED_MARKETS
from services.prediction_evaluator import evaluate_prediction
from services.result_fetcher import ResultFetcher, get_service as get_result_fetcher_service

logger = logging.getLogger(__name__)
SUPPORTED_MARKET_SET = {str(item).strip().upper() for item in SUPPORTED_MARKETS}


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_iso(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _chunks(values: Sequence[str], size: int = 300) -> Iterable[Sequence[str]]:
    step = max(1, int(size))
    for index in range(0, len(values), step):
        yield values[index : index + step]


def _has_column(client: Client, table_name: str, column_name: str) -> bool:
    try:
        client.table(table_name).select(column_name).limit(1).execute()
        return True
    except Exception as exc:
        message = str(exc).lower()
        if "does not exist" in message or "could not find the" in message:
            return False
        return True


def _result_from_match_row(match_row: Dict[str, Any]) -> Dict[str, Any]:
    home_score = _safe_int(match_row.get("ft_home"))
    away_score = _safe_int(match_row.get("ft_away"))
    ht_home = _safe_int(match_row.get("ht_home"))
    ht_away = _safe_int(match_row.get("ht_away"))
    return {
        "home_score": home_score,
        "away_score": away_score,
        "ht_home": ht_home,
        "ht_away": ht_away,
        "total_goals": home_score + away_score,
        "result": "H" if home_score > away_score else "A" if home_score < away_score else "D",
        "ht_result": "H" if ht_home > ht_away else "A" if ht_home < ht_away else "D",
        "btts": home_score > 0 and away_score > 0,
        "finished": str(match_row.get("status", "")).lower() == "finished",
    }


def _build_actual_outcome_text(result: Dict[str, Any]) -> str:
    ft = f"{_safe_int(result.get('home_score'))}-{_safe_int(result.get('away_score'))}"
    ht_home = result.get("ht_home")
    ht_away = result.get("ht_away")
    if ht_home is None or ht_away is None:
        return ft
    return f"FT {ft} | HT {_safe_int(ht_home)}-{_safe_int(ht_away)}"


def _update_match_result_columns(client: Client, match_id: str, result: Dict[str, Any]) -> None:
    raw_status = str(result.get("status") or "finished").strip().lower()
    normalized_status = "finished" if raw_status in {"settled", "finished"} else raw_status or "finished"
    payload: Dict[str, Any] = {"status": normalized_status}
    if _has_column(client, "matches", "ft_home"):
        payload["ft_home"] = _safe_int(result.get("home_score"))
    if _has_column(client, "matches", "ft_away"):
        payload["ft_away"] = _safe_int(result.get("away_score"))
    if _has_column(client, "matches", "ht_home"):
        payload["ht_home"] = _safe_int(result.get("ht_home"))
    if _has_column(client, "matches", "ht_away"):
        payload["ht_away"] = _safe_int(result.get("ht_away"))

    try:
        client.table("matches").update(payload).eq("id", match_id).execute()
    except Exception:
        logger.exception("Match result update failed. match_id=%s", match_id)


def _fetch_predictions(client: Client, *, limit: int, lookback_days: int) -> List[Dict[str, Any]]:
    query = (
        client.table("predictions")
        .select("id,match_id,market_type,predicted_outcome,created_at,recommended")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if lookback_days > 0:
        lower_bound = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        query = query.gte("created_at", lower_bound)
    rows = query.execute().data or []
    filtered: List[Dict[str, Any]] = []
    seen_match_ids: set[str] = set()
    for row in rows:
        if not bool(row.get("recommended", False)):
            continue
        match_id = str(row.get("match_id") or "").strip()
        if not match_id or match_id in seen_match_ids:
            continue
        market_name = str(row.get("market_type") or row.get("predicted_outcome") or "").strip().upper()
        if market_name in SUPPORTED_MARKET_SET:
            seen_match_ids.add(match_id)
            filtered.append(row)
    return filtered


def _fetch_resolved_prediction_ids(client: Client, prediction_ids: List[str]) -> set[str]:
    resolved: set[str] = set()
    for chunk in _chunks(prediction_ids, size=300):
        if not chunk:
            continue
        try:
            rows = (
                client.table("results_tracker")
                .select("prediction_id")
                .in_("prediction_id", list(chunk))
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("results_tracker lookup failed.")
            continue
        for row in rows:
            prediction_id = str(row.get("prediction_id") or "").strip()
            if prediction_id:
                resolved.add(prediction_id)
    return resolved


def _fetch_match_rows(client: Client, match_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not match_ids:
        return {}
    columns = ["id", "status", "match_date"]
    if _has_column(client, "matches", "odds_api_event_id"):
        columns.append("odds_api_event_id")
    if _has_column(client, "matches", "ft_home"):
        columns.append("ft_home")
    if _has_column(client, "matches", "ft_away"):
        columns.append("ft_away")
    if _has_column(client, "matches", "ht_home"):
        columns.append("ht_home")
    if _has_column(client, "matches", "ht_away"):
        columns.append("ht_away")

    rows: List[Dict[str, Any]] = []
    select_clause = ",".join(columns)
    for chunk in _chunks(match_ids, size=300):
        if not chunk:
            continue
        try:
            rows.extend(
                client.table("matches")
                .select(select_clause)
                .in_("id", list(chunk))
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("matches lookup failed.")
    return {str(row.get("id")): row for row in rows if row.get("id")}


def _fetch_odds_map(client: Client, match_ids: List[str]) -> Dict[Tuple[str, str], float]:
    if not match_ids:
        return {}
    rows: List[Dict[str, Any]] = []
    for chunk in _chunks(match_ids, size=300):
        if not chunk:
            continue
        try:
            rows.extend(
                client.table("odds")
                .select("match_id,market,odd")
                .in_("match_id", list(chunk))
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("odds lookup failed.")
            break

    mapped: Dict[Tuple[str, str], float] = {}
    for row in rows:
        match_id = str(row.get("match_id") or "").strip()
        market = str(row.get("market") or "").strip().upper()
        odd = _safe_float(row.get("odd"), fallback=0.0)
        if match_id and market and odd > 1.0:
            mapped[(match_id, market)] = odd
    return mapped


async def process_pending_predictions(
    *,
    supabase: Client,
    batch_size: int = 500,
    lookback_days: int = 30,
    timezone_name: str = "Europe/Istanbul",
    result_fetcher: Optional[ResultFetcher] = None,
) -> Dict[str, Any]:
    fetcher = result_fetcher or get_result_fetcher_service()
    scan_limit = max(50, min(5000, int(batch_size) * 10))
    predictions = _fetch_predictions(supabase, limit=scan_limit, lookback_days=lookback_days)
    if not predictions:
        return {
            "checked_predictions": 0,
            "unresolved_predictions": 0,
            "finished_matches": 0,
            "evaluated_predictions": 0,
            "correct_predictions": 0,
        }

    prediction_ids = [str(row.get("id") or "").strip() for row in predictions if row.get("id")]
    resolved_ids = _fetch_resolved_prediction_ids(supabase, prediction_ids)
    unresolved = [row for row in predictions if str(row.get("id") or "").strip() and str(row.get("id")) not in resolved_ids]
    unresolved = unresolved[: max(1, int(batch_size))]

    if not unresolved:
        return {
            "checked_predictions": len(predictions),
            "unresolved_predictions": 0,
            "finished_matches": 0,
            "evaluated_predictions": 0,
            "correct_predictions": 0,
        }

    match_ids = sorted({str(row.get("match_id") or "").strip() for row in unresolved if row.get("match_id")})
    match_map = _fetch_match_rows(supabase, match_ids)

    event_cache: Dict[int, Dict[str, Any]] = {}
    finished_by_match: Dict[str, Dict[str, Any]] = {}
    api_calls = 0
    skipped_without_event_id = 0

    for match_id in match_ids:
        row = match_map.get(match_id)
        if not isinstance(row, dict):
            continue

        status = str(row.get("status") or "").lower()
        has_ft = row.get("ft_home") is not None and row.get("ft_away") is not None
        if status == "finished" and has_ft:
            finished_by_match[match_id] = _result_from_match_row(row)
            continue

        match_date = _parse_iso(row.get("match_date"))
        now_utc = datetime.now(timezone.utc)
        if status in {"scheduled", "pending", "upcoming", "notstarted", "ns"} and match_date and match_date > now_utc:
            # Henuz oynanmamis maclar icin result API cagrisi yapma.
            continue

        event_id = _safe_int(row.get("odds_api_event_id"), fallback=0)
        if event_id <= 0:
            skipped_without_event_id += 1
            continue

        if event_id not in event_cache:
            payload = await fetcher.fetch_match_result(event_id)
            api_calls += 1
            if isinstance(payload, dict):
                event_cache[event_id] = payload
            else:
                event_cache[event_id] = {}

        payload = event_cache.get(event_id) or {}
        if not payload:
            continue

        _update_match_result_columns(supabase, match_id, payload)
        if bool(payload.get("finished")):
            finished_by_match[match_id] = payload

    evaluated = 0
    correct = 0
    unknown_market = 0
    timezone_obj = ZoneInfo(timezone_name)
    resolved_at = datetime.now(timezone_obj).isoformat()

    for row in unresolved:
        prediction_id = str(row.get("id") or "").strip()
        match_id = str(row.get("match_id") or "").strip()
        result_payload = finished_by_match.get(match_id)
        if not prediction_id or not match_id or not isinstance(result_payload, dict):
            continue

        market = str(row.get("market_type") or row.get("predicted_outcome") or "").strip()
        verdict = evaluate_prediction(market, result_payload)
        if verdict is None:
            unknown_market += 1
            continue

        tracker_payload = {
            "prediction_id": prediction_id,
            "actual_outcome": _build_actual_outcome_text(result_payload),
            "was_correct": bool(verdict),
            "resolved_at": resolved_at,
        }
        try:
            supabase.table("results_tracker").upsert(tracker_payload, on_conflict="prediction_id").execute()
            evaluated += 1
            if verdict:
                correct += 1
        except Exception:
            logger.exception("results_tracker upsert failed. prediction_id=%s", prediction_id)

    return {
        "checked_predictions": len(predictions),
        "unresolved_predictions": len(unresolved),
        "candidate_matches": len(match_ids),
        "finished_matches": len(finished_by_match),
        "api_calls": api_calls,
        "evaluated_predictions": evaluated,
        "correct_predictions": correct,
        "skipped_without_event_id": skipped_without_event_id,
        "skipped_without_sofascore_id": skipped_without_event_id,
        "skipped_unknown_market": unknown_market,
    }


async def build_performance_summary(
    *,
    supabase: Client,
    lookback_days: int = 90,
    limit: int = 5000,
) -> Dict[str, Any]:
    predictions = _fetch_predictions(supabase, limit=max(100, limit), lookback_days=lookback_days)
    if not predictions:
        return {
            "total_predictions": 0,
            "evaluated_predictions": 0,
            "pending_predictions": 0,
            "hits": 0,
            "losses": 0,
            "hit_rate": 0.0,
            "roi": 0.0,
            "profit_loss": 0.0,
            "by_market": {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    prediction_ids = [str(row.get("id") or "").strip() for row in predictions if row.get("id")]
    resolved_rows: List[Dict[str, Any]] = []
    for chunk in _chunks(prediction_ids, size=300):
        if not chunk:
            continue
        try:
            resolved_rows.extend(
                supabase.table("results_tracker")
                .select("prediction_id,actual_outcome,was_correct,resolved_at")
                .in_("prediction_id", list(chunk))
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("results_tracker history lookup failed.")
            break

    resolved_map = {str(row.get("prediction_id") or "").strip(): row for row in resolved_rows if row.get("prediction_id")}
    resolved_predictions = [row for row in predictions if str(row.get("id") or "").strip() in resolved_map]
    match_ids = sorted({str(row.get("match_id") or "").strip() for row in resolved_predictions if row.get("match_id")})
    odds_map = _fetch_odds_map(supabase, match_ids)

    hits = 0
    losses = 0
    profit_loss = 0.0
    bet_count_with_odds = 0
    by_market: Dict[str, Dict[str, Any]] = {}

    for prediction in resolved_predictions:
        prediction_id = str(prediction.get("id") or "").strip()
        market = str(prediction.get("market_type") or prediction.get("predicted_outcome") or "").strip().upper()
        match_id = str(prediction.get("match_id") or "").strip()
        resolved = resolved_map.get(prediction_id, {})
        was_correct = bool(resolved.get("was_correct"))

        if was_correct:
            hits += 1
        else:
            losses += 1

        odd = odds_map.get((match_id, market))
        market_pl: Optional[float] = None
        if odd is not None and odd > 1.0:
            market_pl = (odd - 1.0) if was_correct else -1.0
            profit_loss += market_pl
            bet_count_with_odds += 1

        bucket = by_market.setdefault(
            market or "UNKNOWN",
            {"total": 0, "hits": 0, "losses": 0, "profit_loss": 0.0, "bets_with_odds": 0},
        )
        bucket["total"] += 1
        bucket["hits"] += 1 if was_correct else 0
        bucket["losses"] += 0 if was_correct else 1
        if market_pl is not None:
            bucket["profit_loss"] += market_pl
            bucket["bets_with_odds"] += 1

    for market, bucket in by_market.items():
        total = int(bucket["total"])
        bets_with_odds = int(bucket["bets_with_odds"])
        bucket["hit_rate"] = round((bucket["hits"] / total) * 100.0, 2) if total else 0.0
        bucket["roi"] = round((bucket["profit_loss"] / bets_with_odds) * 100.0, 2) if bets_with_odds else 0.0
        bucket["profit_loss"] = round(float(bucket["profit_loss"]), 4)
        bucket["market"] = market

    evaluated_total = len(resolved_predictions)
    hit_rate = round((hits / evaluated_total) * 100.0, 2) if evaluated_total else 0.0
    roi = round((profit_loss / bet_count_with_odds) * 100.0, 2) if bet_count_with_odds else 0.0

    return {
        "total_predictions": len(predictions),
        "evaluated_predictions": evaluated_total,
        "pending_predictions": max(0, len(predictions) - evaluated_total),
        "hits": hits,
        "losses": losses,
        "hit_rate": hit_rate,
        "roi": roi,
        "profit_loss": round(profit_loss, 4),
        "bets_with_odds": bet_count_with_odds,
        "by_market": by_market,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def list_prediction_results(
    *,
    supabase: Client,
    status: str = "all",
    market: str = "all",
    lookback_days: int = 30,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    rows = _fetch_predictions(supabase, limit=max(1, min(2000, limit)), lookback_days=lookback_days)
    prediction_ids = [str(row.get("id") or "").strip() for row in rows if row.get("id")]
    resolved_ids = _fetch_resolved_prediction_ids(supabase, prediction_ids)

    resolved_map: Dict[str, Dict[str, Any]] = {}
    for chunk in _chunks(list(resolved_ids), size=300):
        if not chunk:
            continue
        try:
            data = (
                supabase.table("results_tracker")
                .select("prediction_id,actual_outcome,was_correct,resolved_at")
                .in_("prediction_id", list(chunk))
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("results_tracker detail lookup failed.")
            data = []
        for item in data:
            prediction_id = str(item.get("prediction_id") or "").strip()
            if prediction_id:
                resolved_map[prediction_id] = item

    match_ids = sorted({str(row.get("match_id") or "").strip() for row in rows if row.get("match_id")})
    odds_map = _fetch_odds_map(supabase, match_ids)

    items: List[Dict[str, Any]] = []
    for row in rows:
        prediction_id = str(row.get("id") or "").strip()
        if not prediction_id:
            continue
        market_name = str(row.get("market_type") or row.get("predicted_outcome") or "").strip().upper()
        if market_name not in SUPPORTED_MARKET_SET:
            continue
        if market != "all" and market_name != str(market or "").strip().upper():
            continue

        resolved = resolved_map.get(prediction_id)
        derived_status = "evaluated" if resolved else "pending"
        if status != "all" and derived_status != str(status).strip().lower():
            continue

        match_id = str(row.get("match_id") or "").strip()
        odd = odds_map.get((match_id, market_name))
        was_correct = resolved.get("was_correct") if isinstance(resolved, dict) else None
        profit_loss: Optional[float] = None
        if odd is not None and was_correct is not None:
            profit_loss = round((odd - 1.0) if bool(was_correct) else -1.0, 4)

        items.append(
            {
                "prediction_id": prediction_id,
                "match_id": match_id,
                "market": market_name,
                "status": derived_status,
                "was_correct": was_correct,
                "actual_outcome": resolved.get("actual_outcome") if isinstance(resolved, dict) else None,
                "resolved_at": resolved.get("resolved_at") if isinstance(resolved, dict) else None,
                "odd": round(odd, 4) if odd is not None else None,
                "profit_loss": profit_loss,
                "created_at": row.get("created_at"),
            }
        )

    return items
