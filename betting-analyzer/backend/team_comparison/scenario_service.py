from __future__ import annotations

import math
from typing import Any, Dict, List

from prediction_engine.config.settings import RHO_BY_LEAGUE, resolve_league_settings_key


class TeamComparisonScenarioService:
    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _poisson_pmf(k: int, lam: float) -> float:
        if lam <= 0:
            return 1.0 if k == 0 else 0.0
        return math.exp(-lam) * (lam ** k) / math.factorial(k)

    @staticmethod
    def _rho_correction(x: int, y: int, lam: float, mu: float, rho: float) -> float:
        if x == 0 and y == 0:
            return 1 - lam * mu * rho
        if x == 0 and y == 1:
            return 1 + lam * rho
        if x == 1 and y == 0:
            return 1 + mu * rho
        if x == 1 and y == 1:
            return 1 - rho
        return 1.0

    def _score_matrix(self, lam: float, mu: float, rho: float, max_goals: int = 5) -> List[List[float]]:
        matrix: List[List[float]] = []
        total = 0.0
        for i in range(max_goals + 1):
            row: List[float] = []
            for j in range(max_goals + 1):
                value = self._poisson_pmf(i, lam) * self._poisson_pmf(j, mu) * self._rho_correction(i, j, lam, mu, rho)
                value = max(0.0, value)
                row.append(value)
                total += value
            matrix.append(row)
        if total <= 0:
            uniform = 1.0 / float((max_goals + 1) ** 2)
            return [[uniform for _ in range(max_goals + 1)] for _ in range(max_goals + 1)]
        return [[value / total for value in row] for row in matrix]

    def _top_scores(self, matrix: List[List[float]], limit: int = 5) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        size = len(matrix)
        for i in range(size):
            for j in range(size):
                rows.append({"score": f"{i}-{j}", "home_goals": i, "away_goals": j, "probability": round(float(matrix[i][j]), 5)})
        rows.sort(key=lambda item: float(item.get("probability", 0.0)), reverse=True)
        return rows[:limit]

    def _group_probability(self, matrix: List[List[float]], predicate) -> float:
        size = len(matrix)
        return float(sum(matrix[i][j] for i in range(size) for j in range(size) if predicate(i, j)))

    def _tempo_band(self, total_lambda: float) -> str:
        if total_lambda >= 3.0:
            return "Yüksek"
        if total_lambda >= 2.1:
            return "Orta"
        return "Düşük"

    def _first_goal_window(self, total_lambda: float) -> str:
        if total_lambda >= 2.7:
            return "1-30"
        if total_lambda >= 1.9:
            return "31-60"
        return "61-90"

    def _build_named_scenarios(self, snapshot: Dict[str, Any], features: Dict[str, Any], probabilities: Dict[str, float], top_scores: List[Dict[str, Any]], total_lambda: float) -> List[Dict[str, Any]]:
        home_name = str(snapshot.get("home", {}).get("team", {}).get("name") or "Ev Sahibi")
        away_name = str(snapshot.get("away", {}).get("team", {}).get("name") or "Deplasman")
        home = features.get("home") or {}
        away = features.get("away") or {}
        top_score = top_scores[0] if top_scores else {"score": "1-1", "probability": 0.1}
        scenario_rows = [
            {
                "key": "home_pressure",
                "title": f"{home_name} baskılı başlar",
                "probability_score": round(min(100.0, (float(home.get("first_half_pressure_score", 0.0)) + probabilities["MS1"] * 100.0) / 2.0), 2),
                "favored_side": "home",
                "reasons": [
                    "Ev sahibi ilk yarı baskı metriğinde önde.",
                    "Deplasman savunma skoru baskı altında kırılmaya daha açık.",
                    f"Toplam tempo sınıfı {self._tempo_band(total_lambda).lower()} seviyede seyrediyor.",
                ],
                "risk_factors": ["Erken gol gelmezse oyun dengeli faza kayabilir."],
                "first_goal_window": self._first_goal_window(total_lambda),
                "tempo": self._tempo_band(total_lambda),
            },
            {
                "key": "balanced_low_risk",
                "title": "Dengeli ve kontrollü başlangıç",
                "probability_score": round(min(100.0, (probabilities["MSX"] * 100.0 + (100.0 - abs(float(features.get("shared", {}).get("comparison_edge", 0.0))))) / 2.0), 2),
                "favored_side": "draw",
                "reasons": [
                    "Genel güç farkı sınırlıysa ilk bölüm kontrollü akabilir.",
                    "Beraberlik olasılığı senaryo motorunda belirgin pay alıyor.",
                    "İki takımın form sinyalleri tamamen tek yöne bakmıyor.",
                ],
                "risk_factors": ["Tek bir duran top veya bireysel hata dengeyi bozabilir."],
                "first_goal_window": self._first_goal_window(max(total_lambda - 0.4, 0.8)),
                "tempo": "Düşük" if total_lambda < 2.2 else "Orta",
            },
            {
                "key": "away_transition",
                "title": f"{away_name} geçiş oyunu ile tehdit üretir",
                "probability_score": round(min(100.0, (float(away.get("transition_score", 0.0)) + probabilities["MS2"] * 100.0) / 2.0), 2),
                "favored_side": "away",
                "reasons": [
                    "Deplasman geçiş oyunu metriğinde öne çıkabiliyor.",
                    "Ev sahibi savunma kırılganlığı yüksekse bu kanal değer kazanır.",
                    "BTTS olasılığı karşı tehdit ihtimalini destekliyor.",
                ],
                "risk_factors": ["Deplasman topa daha az sahip olsa bile etkin çıkış bulmak zorunda."],
                "first_goal_window": self._first_goal_window(total_lambda),
                "tempo": self._tempo_band(total_lambda),
            },
            {
                "key": "two_way_goals",
                "title": "Gollü ve iki taraflı maç",
                "probability_score": round(min(100.0, ((probabilities["MS_O2.5"] + probabilities["KG_VAR"]) * 100.0) / 2.0), 2),
                "favored_side": "both",
                "reasons": [
                    "Üst 2.5 ve KG Var sinyalleri birlikte yukarı bakıyor.",
                    "Tempo ve gol beklentisi skorları maçın açılma ihtimalini artırıyor.",
                    f"En olası skor kümeleri arasında {top_score['score']} benzeri iki taraflı skorlar var.",
                ],
                "risk_factors": ["Erken kırılma olmazsa beklenti daha kontrollü hatta kayabilir."],
                "first_goal_window": self._first_goal_window(total_lambda),
                "tempo": "Yüksek" if total_lambda >= 2.6 else self._tempo_band(total_lambda),
            },
            {
                "key": "controlled_favorite",
                "title": "Favori taraf kontrollü üstünlük kurar",
                "probability_score": round(min(100.0, max(probabilities["MS1"], probabilities["MS2"]) * 100.0), 2),
                "favored_side": "home" if probabilities["MS1"] >= probabilities["MS2"] else "away",
                "reasons": [
                    "Genel güç farkı tek tarafa eğiliyorsa maç kontrolü o tarafa geçebilir.",
                    "Savunma skoru üstün olan takım oyunu daha abartısız şekilde kilitleyebilir.",
                    "En olası skor çizgileri tek farkla biten sonuçlara da işaret ediyor.",
                ],
                "risk_factors": ["Skor açılmazsa beraberlik penceresi canlı kalır."],
                "first_goal_window": self._first_goal_window(max(total_lambda - 0.2, 0.8)),
                "tempo": self._tempo_band(total_lambda),
            },
        ]
        scenario_rows.sort(key=lambda item: float(item.get("probability_score", 0.0)), reverse=True)
        return scenario_rows

    def run(self, snapshot: Dict[str, Any], features: Dict[str, Any], request: Any) -> Dict[str, Any]:
        home = features.get("home") or {}
        away = features.get("away") or {}
        league_context = str(features.get("league_context") or snapshot.get("fixture_context", {}).get("league") or "default")
        resolved_league = resolve_league_settings_key(league_context)
        rho = RHO_BY_LEAGUE.get(resolved_league, RHO_BY_LEAGUE["default"])
        home_attack = float(home.get("adjusted_attack_score") or home.get("attack_score") or 0.0)
        away_attack = float(away.get("adjusted_attack_score") or away.get("attack_score") or 0.0)
        home_defense = float(home.get("adjusted_defense_score") or home.get("defense_score") or 0.0)
        away_defense = float(away.get("adjusted_defense_score") or away.get("defense_score") or 0.0)
        home_squad = 1.0 - min(0.18, float(home.get("injury_count", 0)) * 0.025)
        away_squad = 1.0 - min(0.18, float(away.get("injury_count", 0)) * 0.025)

        lambda_home = self._clamp(((home_attack / 100.0) * 1.35 + (100.0 - away_defense) / 100.0 * 1.15 + float(home.get("xg_for", 1.1)) * 0.45) * 0.68 * max(home_squad, 0.82), 0.25, 4.2)
        lambda_away = self._clamp(((away_attack / 100.0) * 1.18 + (100.0 - home_defense) / 100.0 * 1.05 + float(away.get("xg_for", 1.0)) * 0.42) * 0.64 * max(away_squad, 0.82), 0.2, 3.8)

        matrix = self._score_matrix(lambda_home, lambda_away, rho, max_goals=5)
        top_scores = self._top_scores(matrix, limit=5)
        probabilities = {
            "MS1": round(self._group_probability(matrix, lambda i, j: i > j), 5),
            "MSX": round(self._group_probability(matrix, lambda i, j: i == j), 5),
            "MS2": round(self._group_probability(matrix, lambda i, j: i < j), 5),
            "MS_O1.5": round(self._group_probability(matrix, lambda i, j: (i + j) > 1.5), 5),
            "MS_O2.5": round(self._group_probability(matrix, lambda i, j: (i + j) > 2.5), 5),
            "MS_O3.5": round(self._group_probability(matrix, lambda i, j: (i + j) > 3.5), 5),
            "MS_U1.5": round(self._group_probability(matrix, lambda i, j: (i + j) < 1.5), 5),
            "MS_U2.5": round(self._group_probability(matrix, lambda i, j: (i + j) < 2.5), 5),
            "MS_U3.5": round(self._group_probability(matrix, lambda i, j: (i + j) < 3.5), 5),
            "KG_VAR": round(self._group_probability(matrix, lambda i, j: i > 0 and j > 0), 5),
            "KG_YOK": round(self._group_probability(matrix, lambda i, j: i == 0 or j == 0), 5),
        }
        total_lambda = lambda_home + lambda_away
        scenarios = self._build_named_scenarios(snapshot, features, probabilities, top_scores, total_lambda)
        return {
            "lambda_home": round(lambda_home, 4),
            "lambda_away": round(lambda_away, 4),
            "one_x_two": {"home": probabilities["MS1"], "draw": probabilities["MSX"], "away": probabilities["MS2"]},
            "totals": {
                "over_1_5": probabilities["MS_O1.5"],
                "under_1_5": probabilities["MS_U1.5"],
                "over_2_5": probabilities["MS_O2.5"],
                "under_2_5": probabilities["MS_U2.5"],
                "over_3_5": probabilities["MS_O3.5"],
                "under_3_5": probabilities["MS_U3.5"],
            },
            "btts": {"yes": probabilities["KG_VAR"], "no": probabilities["KG_YOK"]},
            "market_probabilities": probabilities,
            "top_scores": top_scores,
            "tempo_class": self._tempo_band(total_lambda),
            "first_goal_window": self._first_goal_window(total_lambda),
            "top_3_scenarios": scenarios[:3],
            "scenarios": scenarios,
            "home_edge": round(float(features.get("shared", {}).get("comparison_edge", 0.0)), 2),
            "draw_tendency": round(probabilities["MSX"] * 100.0, 2),
            "away_threat_level": round(probabilities["MS2"] * 100.0, 2),
            "over_tendency": round(probabilities["MS_O2.5"] * 100.0, 2),
            "btts_tendency": round(probabilities["KG_VAR"] * 100.0, 2),
            "league_context": league_context,
        }
