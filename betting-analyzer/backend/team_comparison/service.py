from __future__ import annotations

from typing import Any, Dict

from .cache_service import TeamComparisonCacheService
from .confidence_service import TeamComparisonConfidenceService
from .data_service import TeamComparisonDataService
from .feature_service import TeamComparisonFeatureService
from .models import COMPARISON_MODEL_VERSION, TeamComparisonMeta, TeamComparisonRequest
from .opponent_adjustment_service import TeamComparisonOpponentAdjustmentService
from .robots import ANARobot, BMARobot, GMARobot
from .scenario_service import TeamComparisonScenarioService


class TeamComparisonService:
    def __init__(self, supabase) -> None:
        self.supabase = supabase
        self.cache_service = TeamComparisonCacheService(supabase)
        self.data_service = TeamComparisonDataService(supabase)
        self.feature_service = TeamComparisonFeatureService()
        self.opponent_adjustment_service = TeamComparisonOpponentAdjustmentService()
        self.scenario_service = TeamComparisonScenarioService()
        self.confidence_service = TeamComparisonConfidenceService()
        self.ana_robot = ANARobot()
        self.bma_robot = BMARobot()
        self.gma_robot = GMARobot()

    def meta(self) -> Dict[str, Any]:
        meta = TeamComparisonMeta().to_payload()
        featured_teams = []
        try:
            rows = (
                self.supabase.table("teams")
                .select("id,name,league,country")
                .not_.is_("sofascore_id", "null")
                .order("league")
                .order("name")
                .limit(120)
                .execute()
                .data
                or []
            )
            featured_teams = [
                {
                    "id": str(row.get("id") or ""),
                    "name": str(row.get("name") or ""),
                    "league": str(row.get("league") or ""),
                    "country": str(row.get("country") or ""),
                }
                for row in rows
                if row.get("id") and row.get("name")
            ]
        except Exception:
            featured_teams = []
        return {**meta, "team_selector_source": "/teams", "featured_teams": featured_teams}

    def _assemble_response(
        self,
        request: TeamComparisonRequest,
        snapshot: Dict[str, Any],
        features: Dict[str, Any],
        scenarios: Dict[str, Any],
        confidence: Dict[str, Any],
        robots_payload: Dict[str, Any],
        *,
        cache_hit: bool,
    ) -> Dict[str, Any]:
        home_team = snapshot.get("home", {}).get("team", {})
        away_team = snapshot.get("away", {}).get("team", {})
        shared = features.get("shared", {})
        return {
            "request": request.to_payload(),
            "header_summary": {
                "home_team": home_team,
                "away_team": away_team,
                "league_context": scenarios.get("league_context") or features.get("league_context"),
                "comparison_date": snapshot.get("generated_at"),
                "data_window": int(request.data_window),
                "confidence_score": confidence.get("confidence_score"),
                "data_quality_score": confidence.get("data_quality_score"),
                "cross_league": bool(snapshot.get("cross_league")),
                "fixture_context": snapshot.get("fixture_context"),
            },
            "shared_comparison": {
                "cards": shared.get("cards") or [],
                "axes": shared.get("axes") or [],
                "comparison_edge": shared.get("comparison_edge"),
            },
            "probability_block": {
                "home_edge": scenarios.get("home_edge"),
                "draw_tendency": scenarios.get("draw_tendency"),
                "away_threat_level": scenarios.get("away_threat_level"),
                "over_tendency": scenarios.get("over_tendency"),
                "btts_tendency": scenarios.get("btts_tendency"),
                "top_5_scorelines": scenarios.get("top_scores") or [],
                "top_3_scenarios": scenarios.get("top_3_scenarios") or [],
                "one_x_two": scenarios.get("one_x_two") or {},
                "totals": scenarios.get("totals") or {},
                "btts": scenarios.get("btts") or {},
                "lambda_home": scenarios.get("lambda_home"),
                "lambda_away": scenarios.get("lambda_away"),
                "tempo_class": scenarios.get("tempo_class"),
                "first_goal_window": scenarios.get("first_goal_window"),
            },
            "visualization": {
                "radar_values": {
                    "home": {
                        "attack_score": features.get("home", {}).get("attack_score"),
                        "defense_score": features.get("home", {}).get("defense_score"),
                        "form_score": features.get("home", {}).get("form_score"),
                        "home_away_score": features.get("home", {}).get("home_away_score"),
                        "tempo_score": features.get("home", {}).get("tempo_score"),
                        "transition_score": features.get("home", {}).get("transition_score"),
                        "set_piece_score": features.get("home", {}).get("set_piece_score"),
                        "resilience_score": features.get("home", {}).get("resilience_score"),
                    },
                    "away": {
                        "attack_score": features.get("away", {}).get("attack_score"),
                        "defense_score": features.get("away", {}).get("defense_score"),
                        "form_score": features.get("away", {}).get("form_score"),
                        "home_away_score": features.get("away", {}).get("home_away_score"),
                        "tempo_score": features.get("away", {}).get("tempo_score"),
                        "transition_score": features.get("away", {}).get("transition_score"),
                        "set_piece_score": features.get("away", {}).get("set_piece_score"),
                        "resilience_score": features.get("away", {}).get("resilience_score"),
                    },
                },
                "bar_comparison": shared.get("cards") or [],
                "scenario_bars": scenarios.get("top_3_scenarios") or [],
            },
            "robots": robots_payload,
            "data_quality": {"score": confidence.get("data_quality_score"), "components": confidence.get("components") or {}},
            "confidence": confidence,
            "data_gaps": list(dict.fromkeys((snapshot.get("data_gaps") or []) + list(confidence.get("warnings") or []))),
            "meta": {
                "model_version": COMPARISON_MODEL_VERSION,
                "cache_hit": cache_hit,
                "selected_tournament": features.get("selected_tournament"),
                "feature_sources": features.get("feature_sources") or {},
                "included_match_ids": features.get("included_match_ids") or [],
            },
        }

    def compare(self, request: TeamComparisonRequest) -> Dict[str, Any]:
        request.validate()
        request_payload = request.to_payload()
        freshness_payload = self.data_service.build_source_freshness(request)
        request_hash = self.cache_service.build_request_hash(request_payload, freshness_payload, model_version=COMPARISON_MODEL_VERSION)

        if not request.refresh:
            cached = self.cache_service.get_cached(request_hash)
            if cached:
                payload = dict(cached.get("comparison_payload") or {})
                payload.setdefault("meta", {})
                payload["meta"]["cache_hit"] = True
                self.cache_service.log_request(
                    request_hash=request_hash,
                    request_payload=request_payload,
                    feature_snapshot=cached.get("feature_snapshot") or {},
                    scenario_snapshot=payload.get("probability_block") or {},
                    robots_payload=cached.get("robots_payload") or {},
                    confidence_score=float(cached.get("confidence_score") or 0.0),
                    data_quality_score=float(cached.get("data_quality_score") or 0.0),
                    model_version=str(cached.get("model_version") or COMPARISON_MODEL_VERSION),
                    cache_hit=True,
                )
                return payload

        snapshot = self.data_service.collect(request)
        features = self.feature_service.build(snapshot, request)
        features = self.opponent_adjustment_service.apply(features, snapshot)
        scenarios = self.scenario_service.run(snapshot, features, request)
        confidence = self.confidence_service.score(snapshot, features, scenarios)
        robots_payload = {
            "ana": self.ana_robot.render(snapshot, features, scenarios, confidence),
            "bma": self.bma_robot.render(snapshot, features, scenarios, confidence),
            "gma": self.gma_robot.render(snapshot, features, scenarios, confidence),
        }
        payload = self._assemble_response(request, snapshot, features, scenarios, confidence, robots_payload, cache_hit=False)
        self.cache_service.write_cache(
            request_hash=request_hash,
            request_payload=request_payload,
            feature_snapshot=features,
            scenario_snapshot=scenarios,
            robots_payload=robots_payload,
            comparison_payload=payload,
            confidence_score=float(confidence.get("confidence_score") or 0.0),
            data_quality_score=float(confidence.get("data_quality_score") or 0.0),
            model_version=COMPARISON_MODEL_VERSION,
            cache_hit=False,
        )
        return payload
