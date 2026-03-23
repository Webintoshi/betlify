from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


class TeamComparisonConfidenceService:
    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _score_freshness(self, snapshot: Dict[str, Any]) -> float:
        now = datetime.now(timezone.utc)
        stamps = [
            snapshot.get("freshness", {}).get("home_team_data_last_fetched_at"),
            snapshot.get("freshness", {}).get("away_team_data_last_fetched_at"),
            snapshot.get("freshness", {}).get("home_profile_last_fetched_at"),
            snapshot.get("freshness", {}).get("away_profile_last_fetched_at"),
        ]
        if not any(stamps):
            return 35.0
        values: List[float] = []
        for stamp in stamps:
            parsed = self._parse_datetime(stamp)
            if parsed is None:
                values.append(30.0)
                continue
            age = now - parsed
            if age <= timedelta(days=1):
                values.append(95.0)
            elif age <= timedelta(days=3):
                values.append(82.0)
            elif age <= timedelta(days=7):
                values.append(68.0)
            else:
                values.append(45.0)
        return round(sum(values) / len(values), 2)

    def score(self, snapshot: Dict[str, Any], features: Dict[str, Any], scenarios: Dict[str, Any]) -> Dict[str, Any]:
        home = features.get("home") or {}
        away = features.get("away") or {}
        data_quality = self._clamp((float(home.get("data_reliability_score", 0.0)) + float(away.get("data_reliability_score", 0.0))) / 2.0)
        lineup_certainty = self._clamp(72.0 if (home.get("injuries") or away.get("injuries")) else 48.0)
        league_stability = 58.0 if snapshot.get("cross_league") else 82.0
        freshness = self._score_freshness(snapshot)
        mapping_confidence = self._clamp(88.0 - len(snapshot.get("data_gaps") or []) * 8.0)
        model_consensus = self._clamp(100.0 - abs(float(features.get("shared", {}).get("comparison_edge", 0.0)) - float(scenarios.get("home_edge", 0.0))) * 0.8)
        context_reliability = 78.0 if snapshot.get("fixture_context", {}).get("has_fixture_context") else 62.0
        sample_strength = self._clamp((float(home.get("matches_used", 0.0)) + float(away.get("matches_used", 0.0))) / 2.0 * 5.0)

        confidence = self._clamp(
            0.20 * data_quality
            + 0.15 * lineup_certainty
            + 0.15 * league_stability
            + 0.10 * freshness
            + 0.10 * mapping_confidence
            + 0.10 * model_consensus
            + 0.10 * context_reliability
            + 0.10 * sample_strength
        )

        warnings: List[str] = []
        if snapshot.get("cross_league"):
            warnings.append("Takımlar farklı lig bağlamında olduğu için model güveni aşağı çekildi.")
        if data_quality < 55:
            warnings.append("Veri yeterliliği sınırlı; bazı metrikler fallback ile üretildi.")
        if sample_strength < 45:
            warnings.append("Örneklem boyutu zayıf; yakın dönem verisi sınırlı olabilir.")
        if freshness < 60:
            warnings.append("Kaynak cache tazeliği sınırlı; bazı veriler güncel olmayabilir.")
        if abs(float(features.get("shared", {}).get("comparison_edge", 0.0))) < 5:
            warnings.append("Güç farkı düşük; maç dengeli okunmalı.")

        band = "yüksek" if confidence >= 85 else "iyi" if confidence >= 70 else "orta" if confidence >= 55 else "düşük" if confidence >= 40 else "sınırlı"
        return {
            "confidence_score": round(confidence, 2),
            "data_quality_score": round(data_quality, 2),
            "confidence_band": band,
            "components": {
                "data_quality": round(data_quality, 2),
                "lineup_certainty": round(lineup_certainty, 2),
                "league_stability": round(league_stability, 2),
                "freshness": round(freshness, 2),
                "mapping_confidence": round(mapping_confidence, 2),
                "model_consensus": round(model_consensus, 2),
                "context_reliability": round(context_reliability, 2),
                "sample_strength": round(sample_strength, 2),
            },
            "warnings": warnings,
        }
