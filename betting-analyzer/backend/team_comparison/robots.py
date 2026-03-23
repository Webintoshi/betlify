from __future__ import annotations

from typing import Any, Dict

from .explanation_service import build_common_commentary, build_risk_factors, confidence_label, data_quality_label, power_edge_label

ANA_SPEC = {"version": "ana-v2", "name": "ANA", "warning": "Bu analiz bilgi amaçlıdır, bahis tavsiyesi değildir."}
BMA_SPEC = {"version": "bma-v2", "name": "BMA", "warning": "Bu analiz tarihsel performansa dayanır, gelecek sonucu temsil etmez."}
GMA_SPEC = {"version": "gma-v2", "name": "GMA", "warning": "Bu analiz veritabanındaki mevcut cache verileriyle üretilmiştir; sonuç yorumu temkinli okunmalıdır."}


class _BaseRobot:
    spec: Dict[str, Any] = {}

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _avg(values: list[float]) -> float:
        cleaned = [float(value) for value in values]
        return sum(cleaned) / len(cleaned) if cleaned else 0.0

    def _team_names(self, snapshot: Dict[str, Any]) -> tuple[str, str]:
        return (
            str(snapshot.get("home", {}).get("team", {}).get("name") or "Ev Sahibi"),
            str(snapshot.get("away", {}).get("team", {}).get("name") or "Deplasman"),
        )

    def _winner(self, snapshot: Dict[str, Any], home_value: float, away_value: float, *, draw_threshold: float = 2.0) -> tuple[str, str]:
        if abs(float(home_value) - float(away_value)) <= draw_threshold:
            return "draw", "Dengeli"
        home_name, away_name = self._team_names(snapshot)
        return ("home", home_name) if home_value > away_value else ("away", away_name)

    def _breakdown_row(self, snapshot: Dict[str, Any], label: str, home_value: float, away_value: float) -> Dict[str, Any]:
        winner, winner_label = self._winner(snapshot, home_value, away_value)
        return {
            "label": label,
            "home_value": round(float(home_value), 2),
            "away_value": round(float(away_value), 2),
            "winner": winner,
            "winner_label": winner_label,
            "edge": round(float(home_value) - float(away_value), 2),
        }

    def _derive_most_likely_score(self, top_scores: list[Dict[str, Any]], *, bias: str = "base") -> str:
        if not top_scores:
            return "1-1"
        if bias == "draw":
            draws = [row for row in top_scores if int(row.get("home_goals", -1)) == int(row.get("away_goals", -2))]
            if draws:
                return str(draws[0].get("score") or "1-1")
        if bias == "home":
            wins = [row for row in top_scores if int(row.get("home_goals", -1)) > int(row.get("away_goals", -1))]
            if wins:
                return str(wins[0].get("score") or top_scores[0].get("score") or "1-0")
        if bias == "away":
            wins = [row for row in top_scores if int(row.get("home_goals", -1)) < int(row.get("away_goals", -1))]
            if wins:
                return str(wins[0].get("score") or top_scores[0].get("score") or "0-1")
        return str(top_scores[0].get("score") or "1-1")

    def _scenario_title_from_market_view(self, snapshot: Dict[str, Any], scenarios: Dict[str, Any], *, prefer_goals: bool = False) -> str:
        home_name, away_name = self._team_names(snapshot)
        home_win = float(scenarios.get("one_x_two", {}).get("home", 0.0) or 0.0)
        draw = float(scenarios.get("one_x_two", {}).get("draw", 0.0) or 0.0)
        away_win = float(scenarios.get("one_x_two", {}).get("away", 0.0) or 0.0)
        over = float(scenarios.get("totals", {}).get("over_2_5", 0.0) or 0.0)
        btts = float(scenarios.get("btts", {}).get("yes", 0.0) or 0.0)
        if prefer_goals and over >= 0.56 and btts >= 0.50:
            return "Gollü ve iki taraflı senaryo"
        if home_win >= max(draw, away_win):
            return f"{home_name} tarafı önde"
        if away_win >= max(draw, home_win):
            return f"{away_name} tarafı önde"
        return "Dengeli maç senaryosu"

    def _summary_card(
        self,
        confidence: Dict[str, Any],
        *,
        favorite_team: str,
        power_difference_pct: float,
        recommended_scenario: str,
        most_likely_score: str,
        risks: list[str],
    ) -> Dict[str, Any]:
        return {
            "favorite_team": favorite_team,
            "power_difference_pct": round(abs(power_difference_pct), 2),
            "recommended_scenario": recommended_scenario,
            "most_likely_score": most_likely_score,
            "confidence_label": confidence_label(float(confidence.get("confidence_score", 0.0) or 0.0)),
            "risk_warning": (risks or ["Belirgin ekstra risk sinyali yok."])[0],
        }

    def _common_payload(
        self,
        snapshot: Dict[str, Any],
        confidence: Dict[str, Any],
        *,
        summary_card: Dict[str, Any],
        methodology: str,
        key_signals: list[str],
        model_breakdown: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "name": self.spec.get("name"),
            "spec_version": self.spec.get("version"),
            "summary_card": summary_card,
            "methodology": methodology,
            "key_signals": key_signals,
            "model_breakdown": model_breakdown,
            "confidence_note": f"{confidence_label(float(confidence.get('confidence_score', 0.0) or 0.0))} | {data_quality_label(float(confidence.get('data_quality_score', 0.0) or 0.0))}",
            "data_gaps": list(snapshot.get("data_gaps") or []),
        }


class ANARobot(_BaseRobot):
    spec = ANA_SPEC

    def render(self, snapshot: Dict[str, Any], features: Dict[str, Any], scenarios: Dict[str, Any], confidence: Dict[str, Any]) -> Dict[str, Any]:
        home_name, away_name = self._team_names(snapshot)
        home = features.get("home", {})
        away = features.get("away", {})
        shared = features.get("shared", {})
        cards = shared.get("cards") or []
        h2h = snapshot.get("h2h", {}).get("summary", {})
        h2h_home_score = self._clamp(50 + (int(h2h.get("home_wins", 0) or 0) - int(h2h.get("away_wins", 0) or 0)) * 12)
        h2h_away_score = self._clamp(50 + (int(h2h.get("away_wins", 0) or 0) - int(h2h.get("home_wins", 0) or 0)) * 12)
        squad_home_score = self._clamp(float(home.get("squad_score", 0.0) or 0.0) - float(home.get("injury_count", 0.0) or 0.0) * 4.0)
        squad_away_score = self._clamp(float(away.get("squad_score", 0.0) or 0.0) - float(away.get("injury_count", 0.0) or 0.0) * 4.0)
        model_breakdown = [
            self._breakdown_row(snapshot, "Hücum Gücü", float(home.get("attack_score", 0.0) or 0.0), float(away.get("attack_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "Savunma Gücü", float(home.get("defense_score", 0.0) or 0.0), float(away.get("defense_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "Form Durumu", float(home.get("form_score", 0.0) or 0.0), float(away.get("form_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "Ev/Dep Performansı", float(home.get("home_away_score", 0.0) or 0.0), float(away.get("home_away_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "H2H Üstünlüğü", h2h_home_score, h2h_away_score),
            self._breakdown_row(snapshot, "Kadro Durumu", squad_home_score, squad_away_score),
        ]
        home_model_score = self._avg([float(row["home_value"]) for row in model_breakdown])
        away_model_score = self._avg([float(row["away_value"]) for row in model_breakdown])
        _, favorite_label = self._winner(snapshot, home_model_score, away_model_score, draw_threshold=3.0)
        top_score = self._derive_most_likely_score(
            scenarios.get("top_scores") or [],
            bias="home" if favorite_label == home_name else "away" if favorite_label == away_name else "draw",
        )
        risks = build_risk_factors(snapshot, cards, confidence)
        summary_card = self._summary_card(
            confidence,
            favorite_team=favorite_label,
            power_difference_pct=home_model_score - away_model_score,
            recommended_scenario=self._scenario_title_from_market_view(snapshot, scenarios, prefer_goals=True),
            most_likely_score=top_score,
            risks=risks,
        )
        key_signals = [
            f"Hücum farkı: {home_name} {float(home.get('attack_score', 0.0) or 0.0):.1f} | {away_name} {float(away.get('attack_score', 0.0) or 0.0):.1f}",
            f"H2H dengesi: {home_name} {int(h2h.get('home_wins', 0) or 0)} galibiyet, {away_name} {int(h2h.get('away_wins', 0) or 0)} galibiyet",
            f"Kadro cezası: {home_name} {int(home.get('injury_count', 0) or 0)} eksik | {away_name} {int(away.get('injury_count', 0) or 0)} eksik",
        ]
        report_blocks = [
            {"title": "Analiz Uyarısı", "body": self.spec["warning"]},
            {"title": "Güç Dengesi", "body": "\n".join([f"- {card['label']}: {home_name} {card['home_score']:.1f} | {away_name} {card['away_score']:.1f} | Üstünlük: {card['winner_label']}" for card in cards[:6]])},
            {"title": "H2H Özeti", "body": f"Son kafa kafaya penceresinde {home_name} {int(h2h.get('home_wins', 0) or 0)} galibiyet, {away_name} {int(h2h.get('away_wins', 0) or 0)} galibiyet ve {int(h2h.get('draws', 0) or 0)} beraberlik üretti."},
            {"title": "Senaryo Olasılıkları", "body": f"Ev sahibi galibiyeti %{round(float(scenarios.get('one_x_two', {}).get('home', 0.0)) * 100.0, 1)}, beraberlik %{round(float(scenarios.get('one_x_two', {}).get('draw', 0.0)) * 100.0, 1)}, deplasman galibiyeti %{round(float(scenarios.get('one_x_two', {}).get('away', 0.0)) * 100.0, 1)}. Üst 2.5 %{round(float(scenarios.get('totals', {}).get('over_2_5', 0.0)) * 100.0, 1)}, KG Var %{round(float(scenarios.get('btts', {}).get('yes', 0.0)) * 100.0, 1)}. ANA için en uyumlu skor bandı {top_score}."},
            {"title": "Üstünlük Analizi", "body": f"ANA, 6 boyutlu güç dengesi kullandığı için toplam farkı {power_edge_label(home_model_score - away_model_score).lower()} seviyede okuyor. Hücum-skor üretimi, rol bazlı form, H2H ve kadro bütünlüğü aynı yöne bakarsa {summary_card['favorite_team']} tarafı bu modelde öne çıkıyor."},
            {"title": "Risk Faktörleri", "body": "\n".join(f"- {risk}" for risk in (risks or ["Belirgin ekstra risk sinyali yok."]))},
        ]
        payload = self._common_payload(
            snapshot,
            confidence,
            summary_card=summary_card,
            methodology="6 boyutlu güç dengesi: hücum, savunma, form, rol bazlı performans, H2H ve kadro durumu eşit eksenlerle tartılır.",
            key_signals=key_signals,
            model_breakdown=model_breakdown,
        )
        payload["report_blocks"] = report_blocks
        return payload


class BMARobot(_BaseRobot):
    spec = BMA_SPEC

    def render(self, snapshot: Dict[str, Any], features: Dict[str, Any], scenarios: Dict[str, Any], confidence: Dict[str, Any]) -> Dict[str, Any]:
        home_name, away_name = self._team_names(snapshot)
        home = features.get("home", {})
        away = features.get("away", {})
        commentary = build_common_commentary(snapshot, features, scenarios)
        elo_home = float(home.get("elo_like_rating", 0.0) or 0.0)
        elo_away = float(away.get("elo_like_rating", 0.0) or 0.0)
        elo_delta = (elo_home + 100.0) - elo_away
        expected_home = 1.0 / (1.0 + (10.0 ** (-elo_delta / 400.0)))
        draw_share = self._clamp(0.34 - abs(expected_home - 0.5) * 0.32, 0.16, 0.32)
        elo_home_win = self._clamp(expected_home * (1.0 - draw_share), 0.12, 0.76)
        elo_away_win = self._clamp((1.0 - expected_home) * (1.0 - draw_share), 0.12, 0.76)
        model_home_score = self._clamp(
            float(home.get("form_score", 0.0) or 0.0) * 0.20
            + float(home.get("attack_score", 0.0) or 0.0) * 0.20
            + float(home.get("defense_score", 0.0) or 0.0) * 0.18
            + (elo_home - 1500.0) * 0.08
            + float(scenarios.get("one_x_two", {}).get("home", 0.0) or 0.0) * 32.0
            + elo_home_win * 22.0
        )
        model_away_score = self._clamp(
            float(away.get("form_score", 0.0) or 0.0) * 0.20
            + float(away.get("attack_score", 0.0) or 0.0) * 0.20
            + float(away.get("defense_score", 0.0) or 0.0) * 0.18
            + (elo_away - 1500.0) * 0.08
            + float(scenarios.get("one_x_two", {}).get("away", 0.0) or 0.0) * 32.0
            + elo_away_win * 22.0
        )
        _, favorite_label = self._winner(snapshot, model_home_score, model_away_score, draw_threshold=2.5)
        model_breakdown = [
            self._breakdown_row(snapshot, "Form Rating", float(home.get("form_score", 0.0) or 0.0), float(away.get("form_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "Attack Strength", float(home.get("attack_score", 0.0) or 0.0), float(away.get("attack_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "Defense Strength", float(home.get("defense_score", 0.0) or 0.0), float(away.get("defense_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "ELO-benzeri Rating", elo_home, elo_away),
            self._breakdown_row(snapshot, "Dixon-Coles 1X2 Eğimi", float(scenarios.get("one_x_two", {}).get("home", 0.0) or 0.0) * 100.0, float(scenarios.get("one_x_two", {}).get("away", 0.0) or 0.0) * 100.0),
            self._breakdown_row(snapshot, "Ensemble Model Skoru", model_home_score, model_away_score),
        ]
        risks = build_risk_factors(snapshot, features.get("shared", {}).get("cards") or [], confidence)
        summary_card = self._summary_card(
            confidence,
            favorite_team=favorite_label,
            power_difference_pct=model_home_score - model_away_score,
            recommended_scenario=self._scenario_title_from_market_view(snapshot, scenarios, prefer_goals=False),
            most_likely_score=self._derive_most_likely_score(
                scenarios.get("top_scores") or [],
                bias="home" if favorite_label == home_name else "away" if favorite_label == away_name else "draw",
            ),
            risks=risks,
        )
        key_signals = [
            f"ELO-benzeri fark: {home_name} {elo_home:.0f} | {away_name} {elo_away:.0f}",
            f"Lambda: ev {float(scenarios.get('lambda_home', 0.0)):.2f} | dep {float(scenarios.get('lambda_away', 0.0)):.2f}",
            f"Ensemble 1X2: Ev %{round(float(scenarios.get('one_x_two', {}).get('home', 0.0)) * 100.0, 1)} | X %{round(float(scenarios.get('one_x_two', {}).get('draw', 0.0)) * 100.0, 1)} | Dep %{round(float(scenarios.get('one_x_two', {}).get('away', 0.0)) * 100.0, 1)}",
        ]
        report_blocks = [
            {"title": "Analiz Uyarısı", "body": self.spec["warning"]},
            {"title": "Form Analizi", "body": f"{home_name} form skoru {home.get('form_score', 0):.1f}, {away_name} form skoru {away.get('form_score', 0):.1f}. Trend etiketi sırasıyla {home.get('trend', 'stabil')} ve {away.get('trend', 'stabil')}."},
            {"title": "Hücum ve Savunma Gücü", "body": f"Hücum: {home_name} {home.get('attack_score', 0):.1f} | {away_name} {away.get('attack_score', 0):.1f}. Savunma: {home_name} {home.get('defense_score', 0):.1f} | {away_name} {away.get('defense_score', 0):.1f}. xG/pxG tabanı: {home_name} {home.get('xg_for', 0):.2f}, {away_name} {away.get('xg_for', 0):.2f}."},
            {"title": "Poisson + Dixon-Coles", "body": f"Lambda değerleri ev {float(scenarios.get('lambda_home', 0.0)):.2f}, deplasman {float(scenarios.get('lambda_away', 0.0)):.2f}. 1X2: Ev %{round(float(scenarios.get('one_x_two', {}).get('home', 0.0)) * 100.0, 1)} | X %{round(float(scenarios.get('one_x_two', {}).get('draw', 0.0)) * 100.0, 1)} | 2 %{round(float(scenarios.get('one_x_two', {}).get('away', 0.0)) * 100.0, 1)}."},
            {"title": "ELO Benzeri Güç Skoru", "body": f"İç sistem ELO-benzeri rating: {home_name} {elo_home:.0f}, {away_name} {elo_away:.0f}. ELO-bazlı sonuç eğimi ev %{round(elo_home_win * 100.0, 1)} | X %{round(draw_share * 100.0, 1)} | dep %{round(elo_away_win * 100.0, 1)}."},
            {"title": "Ensemble Sonuç", "body": f"BMA, Poisson/Dixon-Coles ve ELO-benzeri katmanı birlikte okur. Bu birleşik bakışta güç farkı {power_edge_label(model_home_score - model_away_score).lower()} seviyede. Üst 2.5 %{round(float(scenarios.get('totals', {}).get('over_2_5', 0.0)) * 100.0, 1)}, Alt 2.5 %{round(float(scenarios.get('totals', {}).get('under_2_5', 0.0)) * 100.0, 1)}, KG Var %{round(float(scenarios.get('btts', {}).get('yes', 0.0)) * 100.0, 1)}. {commentary['detailed']}"},
        ]
        payload = self._common_payload(
            snapshot,
            confidence,
            summary_card=summary_card,
            methodology="9 aşamalı teknik model: form, attack/defense strength, Poisson, Dixon-Coles, ELO-benzeri rating ve ensemble birleştirmesi kullanılır.",
            key_signals=key_signals,
            model_breakdown=model_breakdown,
        )
        payload["report_blocks"] = report_blocks
        return payload


class GMARobot(_BaseRobot):
    spec = GMA_SPEC

    def render(self, snapshot: Dict[str, Any], features: Dict[str, Any], scenarios: Dict[str, Any], confidence: Dict[str, Any]) -> Dict[str, Any]:
        home_name, away_name = self._team_names(snapshot)
        home = features.get("home", {})
        away = features.get("away", {})
        commentary = build_common_commentary(snapshot, features, scenarios)
        risks = build_risk_factors(snapshot, features.get("shared", {}).get("cards") or [], confidence)
        top_scenarios = scenarios.get("top_3_scenarios") or []
        scenario_lines = [f"- {row.get('title')}: %{round(float(row.get('probability_score', 0.0)), 1)} | Tempo: {row.get('tempo')} | İlk gol penceresi: {row.get('first_goal_window')}" for row in top_scenarios]
        model_breakdown = [
            self._breakdown_row(snapshot, "Genel Güç", float(features.get("shared", {}).get("general_power", {}).get("home_score", home.get("power_index", 0.0)) or home.get("power_index", 0.0)), float(features.get("shared", {}).get("general_power", {}).get("away_score", away.get("power_index", 0.0)) or away.get("power_index", 0.0))),
            self._breakdown_row(snapshot, "Tempo", float(home.get("tempo_score", 0.0) or 0.0), float(away.get("tempo_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "Geçiş Oyunu", float(home.get("transition_score", 0.0) or 0.0), float(away.get("transition_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "Duran Top", float(home.get("set_piece_score", 0.0) or 0.0), float(away.get("set_piece_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "Dayanıklılık", float(home.get("resilience_score", 0.0) or 0.0), float(away.get("resilience_score", 0.0) or 0.0)),
            self._breakdown_row(snapshot, "Bağlam/Kadro", self._avg([float(home.get("squad_score", 0.0) or 0.0), float(home.get("context_score", 0.0) or 0.0)]), self._avg([float(away.get("squad_score", 0.0) or 0.0), float(away.get("context_score", 0.0) or 0.0)])),
        ]
        home_model_score = self._avg([float(row["home_value"]) for row in model_breakdown])
        away_model_score = self._avg([float(row["away_value"]) for row in model_breakdown])
        _, favorite_label = self._winner(snapshot, home_model_score, away_model_score, draw_threshold=2.0)
        summary_card = self._summary_card(
            confidence,
            favorite_team=favorite_label,
            power_difference_pct=home_model_score - away_model_score,
            recommended_scenario=str((top_scenarios[0] if top_scenarios else {"title": self._scenario_title_from_market_view(snapshot, scenarios)}).get("title")),
            most_likely_score=self._derive_most_likely_score(
                scenarios.get("top_scores") or [],
                bias="home" if favorite_label == home_name else "away" if favorite_label == away_name else "draw",
            ),
            risks=risks,
        )
        strongest_cards = sorted(features.get("shared", {}).get("cards") or [], key=lambda row: abs(float(row.get("edge", 0.0) or 0.0)), reverse=True)
        key_signals = [
            f"{str(row.get('label') or '')}: {str(row.get('winner_label') or 'Dengeli')} ({abs(float(row.get('edge', 0.0) or 0.0)):.1f} puan fark)"
            for row in strongest_cards[:3]
        ] or [
            f"Toplam comparison edge: {float(features.get('shared', {}).get('comparison_edge', 0.0) or 0.0):.1f}",
            f"Tempo sınıfı: {str(scenarios.get('tempo_class') or 'Düşük')}",
            f"BTTS eğilimi: %{round(float(scenarios.get('btts', {}).get('yes', 0.0) or 0.0) * 100.0, 1)}",
        ]
        report_blocks = [
            {"title": "Analiz Uyarısı", "body": self.spec["warning"]},
            {"title": "Kısa Yorum", "body": commentary["short"]},
            {"title": "Detaylı Yorum", "body": commentary["detailed"]},
            {"title": "Uzman Yorumu", "body": commentary["expert"]},
            {"title": "Alan Bazlı Üstünlük", "body": f"Form {home_name} {home.get('form_score', 0):.1f} - {away_name} {away.get('form_score', 0):.1f}, hücum {home_name} {home.get('attack_score', 0):.1f} - {away_name} {away.get('attack_score', 0):.1f}, savunma {home_name} {home.get('defense_score', 0):.1f} - {away_name} {away.get('defense_score', 0):.1f}."},
            {"title": "Senaryo Motoru", "body": "\n".join(scenario_lines or ["- Belirgin senaryo üretmek için veri sınırlı."])},
            {"title": "Riskler ve Veri Boşlukları", "body": "\n".join(f"- {line}" for line in ((risks or []) + list(snapshot.get('data_gaps') or []))[:8]) or "- Ek risk sinyali yok."},
        ]
        payload = self._common_payload(
            snapshot,
            confidence,
            summary_card=summary_card,
            methodology="Çok katmanlı ürün modeli: attack, defense, form, tempo, transition, set piece, resilience, squad ve context eksenlerini birlikte tartar.",
            key_signals=key_signals,
            model_breakdown=model_breakdown,
        )
        payload["report_blocks"] = report_blocks
        payload["header_summary"] = {"home_team": home_name, "away_team": away_name, "comparison_date": snapshot.get("generated_at"), "data_window": snapshot.get("request", {}).get("data_window"), "league_context": scenarios.get("league_context")}
        return payload
