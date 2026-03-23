from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from supabase import Client

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24


class TeamComparisonCacheService:
    def __init__(self, supabase: Client) -> None:
        self.supabase = supabase

    @staticmethod
    def build_request_hash(request_payload: Dict[str, Any], freshness_payload: Dict[str, Any], *, model_version: str) -> str:
        raw = json.dumps(
            {
                "request": request_payload,
                "freshness": freshness_payload,
                "model_version": model_version,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_cached(self, request_hash: str) -> Optional[Dict[str, Any]]:
        try:
            rows = (
                self.supabase.table("team_comparison_cache")
                .select("comparison_payload,feature_snapshot,robots_payload,confidence_score,data_quality_score,model_version,expires_at")
                .eq("request_hash", request_hash)
                .limit(1)
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("team_comparison_cache read failed. request_hash=%s", request_hash)
            return None
        if not rows:
            return None
        row = rows[0]
        expires_at = str(row.get("expires_at") or "").strip()
        if expires_at:
            try:
                parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if parsed <= datetime.now(timezone.utc):
                    return None
            except ValueError:
                return None
        return row if isinstance(row, dict) else None

    def log_request(
        self,
        *,
        request_hash: str,
        request_payload: Dict[str, Any],
        feature_snapshot: Dict[str, Any],
        scenario_snapshot: Dict[str, Any],
        robots_payload: Dict[str, Any],
        confidence_score: float,
        data_quality_score: float,
        model_version: str,
        cache_hit: bool,
    ) -> None:
        log_row = {
            "request_hash": request_hash,
            "home_team_id": request_payload.get("home_team_id"),
            "away_team_id": request_payload.get("away_team_id"),
            "request_payload": request_payload,
            "included_match_ids": feature_snapshot.get("included_match_ids") or [],
            "feature_snapshot": feature_snapshot,
            "scenario_snapshot": scenario_snapshot,
            "robots_payload": robots_payload,
            "confidence_score": confidence_score,
            "data_quality_score": data_quality_score,
            "cache_hit": bool(cache_hit),
            "model_version": model_version,
        }
        try:
            self.supabase.table("team_comparison_logs").insert(log_row).execute()
        except Exception:
            logger.exception("team_comparison_logs insert failed. request_hash=%s", request_hash)

    def write_cache(
        self,
        *,
        request_hash: str,
        request_payload: Dict[str, Any],
        feature_snapshot: Dict[str, Any],
        scenario_snapshot: Dict[str, Any],
        robots_payload: Dict[str, Any],
        comparison_payload: Dict[str, Any],
        confidence_score: float,
        data_quality_score: float,
        model_version: str,
        cache_hit: bool,
    ) -> None:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=CACHE_TTL_HOURS)
        row = {
            "request_hash": request_hash,
            "home_team_id": request_payload.get("home_team_id"),
            "away_team_id": request_payload.get("away_team_id"),
            "scope": request_payload.get("scope"),
            "season_mode": request_payload.get("season_mode"),
            "data_window": request_payload.get("data_window"),
            "date_from": request_payload.get("date_from"),
            "date_to": request_payload.get("date_to"),
            "selected_tournament_id": request_payload.get("tournament_id"),
            "selected_season_id": request_payload.get("season_id"),
            "comparison_payload": comparison_payload,
            "feature_snapshot": feature_snapshot,
            "robots_payload": robots_payload,
            "confidence_score": confidence_score,
            "data_quality_score": data_quality_score,
            "model_version": model_version,
            "expires_at": expires_at.isoformat(),
            "updated_at": now.isoformat(),
        }
        try:
            self.supabase.table("team_comparison_cache").upsert(row, on_conflict="request_hash").execute()
        except Exception:
            logger.exception("team_comparison_cache write failed. request_hash=%s", request_hash)
        self.log_request(
            request_hash=request_hash,
            request_payload=request_payload,
            feature_snapshot=feature_snapshot,
            scenario_snapshot=scenario_snapshot,
            robots_payload=robots_payload,
            confidence_score=confidence_score,
            data_quality_score=data_quality_score,
            model_version=model_version,
            cache_hit=cache_hit,
        )

    def cleanup_expired(self) -> Dict[str, int]:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            rows = (
                self.supabase.table("team_comparison_cache")
                .select("id", count="exact")
                .lt("expires_at", now_iso)
                .limit(5000)
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("team_comparison_cache cleanup scan failed.")
            return {"deleted": 0}
        deleted = 0
        for row in rows:
            row_id = str(row.get("id") or "").strip()
            if not row_id:
                continue
            try:
                self.supabase.table("team_comparison_cache").delete().eq("id", row_id).execute()
                deleted += 1
            except Exception:
                logger.exception("team_comparison_cache cleanup delete failed. row_id=%s", row_id)
        return {"deleted": deleted}

    def status(self) -> Dict[str, int]:
        now_iso = datetime.now(timezone.utc).isoformat()
        total = 0
        active = 0
        expired = 0
        try:
            total = int(self.supabase.table("team_comparison_cache").select("id", count="exact").limit(1).execute().count or 0)
            active = int(self.supabase.table("team_comparison_cache").select("id", count="exact").gt("expires_at", now_iso).limit(1).execute().count or 0)
            expired = int(self.supabase.table("team_comparison_cache").select("id", count="exact").lt("expires_at", now_iso).limit(1).execute().count or 0)
        except Exception:
            logger.exception("team_comparison_cache status failed.")
        return {"total": total, "active": active, "expired": expired}
