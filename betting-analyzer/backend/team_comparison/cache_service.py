from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from supabase import Client

from .models import SUPPORTED_ROBOTS

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

    @staticmethod
    def build_robot_request_hash(
        request_payload: Dict[str, Any],
        freshness_payload: Dict[str, Any],
        *,
        model_version: str,
        robot_key: str,
        robot_version: str,
    ) -> str:
        raw = json.dumps(
            {
                "request": request_payload,
                "freshness": freshness_payload,
                "model_version": model_version,
                "robot_key": robot_key,
                "robot_version": robot_version,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_cached_robot(self, request_hash: str) -> Optional[Dict[str, Any]]:
        try:
            rows = (
                self.supabase.table("team_comparison_robot_cache")
                .select("robot_key,robot_payload,feature_snapshot,scenario_snapshot,confidence_score,data_quality_score,model_version,robot_model_version,expires_at")
                .eq("request_hash", request_hash)
                .limit(1)
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("team_comparison_robot_cache read failed. request_hash=%s", request_hash)
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

    def log_robot_request(
        self,
        *,
        request_hash: str,
        base_request_hash: str,
        robot_key: str,
        request_payload: Dict[str, Any],
        feature_snapshot: Dict[str, Any],
        scenario_snapshot: Dict[str, Any],
        robot_payload: Dict[str, Any],
        confidence_score: float,
        data_quality_score: float,
        model_version: str,
        robot_model_version: str,
        cache_hit: bool,
    ) -> None:
        log_row = {
            "request_hash": request_hash,
            "base_request_hash": base_request_hash,
            "robot_key": robot_key,
            "home_team_id": request_payload.get("home_team_id"),
            "away_team_id": request_payload.get("away_team_id"),
            "request_payload": request_payload,
            "included_match_ids": feature_snapshot.get("included_match_ids") or [],
            "feature_snapshot": feature_snapshot,
            "scenario_snapshot": scenario_snapshot,
            "robot_payload": robot_payload,
            "confidence_score": confidence_score,
            "data_quality_score": data_quality_score,
            "cache_hit": bool(cache_hit),
            "model_version": model_version,
            "robot_model_version": robot_model_version,
        }
        try:
            self.supabase.table("team_comparison_robot_logs").insert(log_row).execute()
        except Exception:
            logger.exception("team_comparison_robot_logs insert failed. request_hash=%s robot=%s", request_hash, robot_key)

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

    def write_robot_cache(
        self,
        *,
        request_hash: str,
        base_request_hash: str,
        robot_key: str,
        request_payload: Dict[str, Any],
        feature_snapshot: Dict[str, Any],
        scenario_snapshot: Dict[str, Any],
        robot_payload: Dict[str, Any],
        confidence_score: float,
        data_quality_score: float,
        model_version: str,
        robot_model_version: str,
        cache_hit: bool,
    ) -> None:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=CACHE_TTL_HOURS)
        row = {
            "request_hash": request_hash,
            "base_request_hash": base_request_hash,
            "robot_key": robot_key,
            "home_team_id": request_payload.get("home_team_id"),
            "away_team_id": request_payload.get("away_team_id"),
            "scope": request_payload.get("scope"),
            "season_mode": request_payload.get("season_mode"),
            "data_window": request_payload.get("data_window"),
            "date_from": request_payload.get("date_from"),
            "date_to": request_payload.get("date_to"),
            "selected_tournament_id": request_payload.get("tournament_id"),
            "selected_season_id": request_payload.get("season_id"),
            "robot_payload": robot_payload,
            "feature_snapshot": feature_snapshot,
            "scenario_snapshot": scenario_snapshot,
            "confidence_score": confidence_score,
            "data_quality_score": data_quality_score,
            "model_version": model_version,
            "robot_model_version": robot_model_version,
            "expires_at": expires_at.isoformat(),
            "updated_at": now.isoformat(),
        }
        try:
            self.supabase.table("team_comparison_robot_cache").upsert(row, on_conflict="request_hash").execute()
        except Exception:
            logger.exception("team_comparison_robot_cache write failed. request_hash=%s robot=%s", request_hash, robot_key)
        self.log_robot_request(
            request_hash=request_hash,
            base_request_hash=base_request_hash,
            robot_key=robot_key,
            request_payload=request_payload,
            feature_snapshot=feature_snapshot,
            scenario_snapshot=scenario_snapshot,
            robot_payload=robot_payload,
            confidence_score=confidence_score,
            data_quality_score=data_quality_score,
            model_version=model_version,
            robot_model_version=robot_model_version,
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
        robot_deleted = 0
        try:
            robot_rows = (
                self.supabase.table("team_comparison_robot_cache")
                .select("id", count="exact")
                .lt("expires_at", now_iso)
                .limit(5000)
                .execute()
                .data
                or []
            )
        except Exception:
            logger.exception("team_comparison_robot_cache cleanup scan failed.")
            robot_rows = []
        for row in robot_rows:
            row_id = str(row.get("id") or "").strip()
            if not row_id:
                continue
            try:
                self.supabase.table("team_comparison_robot_cache").delete().eq("id", row_id).execute()
                robot_deleted += 1
            except Exception:
                logger.exception("team_comparison_robot_cache cleanup delete failed. row_id=%s", row_id)
        return {"deleted": deleted, "robot_deleted": robot_deleted}

    def status(self) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        total = 0
        active = 0
        expired = 0
        robot_total = 0
        robot_active = 0
        robot_expired = 0
        robot_by_key = {robot_key: 0 for robot_key in SUPPORTED_ROBOTS}
        try:
            total = int(self.supabase.table("team_comparison_cache").select("id", count="exact").limit(1).execute().count or 0)
            active = int(self.supabase.table("team_comparison_cache").select("id", count="exact").gt("expires_at", now_iso).limit(1).execute().count or 0)
            expired = int(self.supabase.table("team_comparison_cache").select("id", count="exact").lt("expires_at", now_iso).limit(1).execute().count or 0)
            robot_total = int(self.supabase.table("team_comparison_robot_cache").select("id", count="exact").limit(1).execute().count or 0)
            robot_active = int(self.supabase.table("team_comparison_robot_cache").select("id", count="exact").gt("expires_at", now_iso).limit(1).execute().count or 0)
            robot_expired = int(self.supabase.table("team_comparison_robot_cache").select("id", count="exact").lt("expires_at", now_iso).limit(1).execute().count or 0)
            for robot_key in SUPPORTED_ROBOTS:
                robot_by_key[robot_key] = int(
                    self.supabase.table("team_comparison_robot_cache")
                    .select("id", count="exact")
                    .eq("robot_key", robot_key)
                    .gt("expires_at", now_iso)
                    .limit(1)
                    .execute()
                    .count
                    or 0
                )
        except Exception:
            logger.exception("team_comparison_cache status failed.")
        return {
            "shared": {"total": total, "active": active, "expired": expired},
            "robots": {"total": robot_total, "active": robot_active, "expired": robot_expired, "by_key": robot_by_key},
        }
