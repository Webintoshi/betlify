from __future__ import annotations

from typing import Any, Dict

from .explanation_service import build_common_commentary, build_risk_factors, confidence_label, data_quality_label, power_edge_label

ANA_SPEC = {"version": "ana-v1", "name": "ANA", "warning": "Bu analiz bilgi amaçlıdır, bahis tavsiyesi değildir."}
BMA_SPEC = {"version": "bma-v1", "name": "BMA", "warning": "Bu analiz tarihsel performansa dayanır, gelecek sonucu temsil etmez."}
GMA_SPEC = {"version": "gma-v1", "name": "GMA", "warning": "Bu analiz veritabanındaki mevcut cache verileriyle üretilmiştir; sonuç yorumu temkinli okunmalıdır."}


class _BaseRobot:
    spec: Dict[str, Any] = {}

    def _team_names(self, snapshot: Dict[str, Any]) -> tuple[str, str]:
        return (
            str(snapshot.get("home", {}).get("team", {}).get("name") or "Ev Sahibi"),
            str(snapshot.get("away", {}).get("team", {}).get("name") or "Deplasman"),
        )

    def _summary_card(self, snapshot: Dict[str, Any], features: Dict[str, Any], scenarios: Dict[str, Any], confidence: Dict[str, Any]) -> Dict[str, Any]:
        home_name, away_name = self._team_names(snapshot)
        edge = float(features.get("shared", {}).get("comparison_edge", 0.0) or 0.0)
        favorite = home_name if edge > 3 else away_name if edge < -3 else "Dengeli"
        top_score = (scenarios.get("top_scores") or [{"score": "1-1"}])[0]
        top_scenario = (scenarios.get("top_3_scenarios") or [{"title": "Dengeli senaryo"}])[0]
        risks = build_risk_factors(snapshot, features.get("shared", {}).get("cards") or [], confidence)
        return {
            "favorite_team": favorite,
            "power_difference_pct": round(abs(edge), 2),
            "recommended_scenario": top_scenario.get("title"),
            "most_likely_score": top_score.get("score"),
            "confidence_label": confidence_label(float(confidence.get("confidence_score", 0.0) or 0.0)),
            "risk_warning": risks[0] if risks else "Belirgin ekstra risk sinyali yok.",
        }

    def _common_payload(self, snapshot: Dict[str, Any], features: Dict[str, Any], scenarios: Dict[str, Any], confidence: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": self.spec.get("name"),
            "spec_version": self.spec.get("version"),
            "summary_card": self._summary_card(snapshot, features, scenarios, confidence),
            "confidence_note": f"{confidence_label(float(confidence.get('confidence_score', 0.0) or 0.0))} | {data_quality_label(float(confidence.get('data_quality_score', 0.0) or 0.0))}",
            "data_gaps": list(snapshot.get("data_gaps") or []),
        }


class ANARobot(_BaseRobot):
    spec = ANA_SPEC

    def render(self, snapshot: Dict[str, Any], features: Dict[str, Any], scenarios: Dict[str, Any], confidence: Dict[str, Any]) -> Dict[str, Any]:
        home_name, away_name = self._team_names(snapshot)
        shared = features.get("shared", {})
        cards = shared.get("cards") or []
        h2h = snapshot.get("h2h", {}).get("summary", {})
        top_score = (scenarios.get("top_scores") or [{"score": "1-1", "probability": 0.1}])[0]
        risks = build_risk_factors(snapshot, cards, confidence)
        report_blocks = [
            {"title": "Analiz Uyarısı", "body": self.spec["warning"]},
            {"title": "Güç Dengesi", "body": "\n".join([f"- {card['label']}: {home_name} {card['home_score']:.1f} | {away_name} {card['away_score']:.1f} | Üstünlük: {card['winner_label']}" for card in cards[:6]])},
            {"title": "H2H Özeti", "body": f"Son kafa kafaya penceresinde {home_name} {int(h2h.get('home_wins', 0) or 0)} galibiyet, {away_name} {int(h2h.get('away_wins', 0) or 0)} galibiyet ve {int(h2h.get('draws', 0) or 0)} beraberlik üretti."},
            {"title": "Senaryo Olasılıkları", "body": f"Ev sahibi galibiyeti %{round(float(scenarios.get('one_x_two', {}).get('home', 0.0)) * 100.0, 1)}, beraberlik %{round(float(scenarios.get('one_x_two', {}).get('draw', 0.0)) * 100.0, 1)}, deplasman galibiyeti %{round(float(scenarios.get('one_x_two', {}).get('away', 0.0)) * 100.0, 1)}. Üst 2.5 %{round(float(scenarios.get('totals', {}).get('over_2_5', 0.0)) * 100.0, 1)}, KG Var %{round(float(scenarios.get('btts', {}).get('yes', 0.0)) * 100.0, 1)}. En olası skor {top_score['score']} (%{round(float(top_score.get('probability', 0.0)) * 100.0, 1)})."},
            {"title": "Üstünlük Analizi", "body": f"Toplam güç farkı {power_edge_label(float(shared.get('comparison_edge', 0.0) or 0.0)).lower()} seviyede. Hücum-skor üretimi, rol bazlı form ve kadro bütünlüğü aynı yöne bakarsa {self._summary_card(snapshot, features, scenarios, confidence)['favorite_team']} tarafı istatistiksel olarak öne çıkıyor."},
            {"title": "Risk Faktörleri", "body": "\n".join(f"- {risk}" for risk in (risks or ["Belirgin ekstra risk sinyali yok."]))},
        ]
        payload = self._common_payload(snapshot, features, scenarios, confidence)
        payload["report_blocks"] = report_blocks
        return payload


class BMARobot(_BaseRobot):
    spec = BMA_SPEC

    def render(self, snapshot: Dict[str, Any], features: Dict[str, Any], scenarios: Dict[str, Any], confidence: Dict[str, Any]) -> Dict[str, Any]:
        home_name, away_name = self._team_names(snapshot)
        home = features.get("home", {})
        away = features.get("away", {})
        shared = features.get("shared", {})
        commentary = build_common_commentary(snapshot, features, scenarios)
        report_blocks = [
            {"title": "Analiz Uyarısı", "body": self.spec["warning"]},
            {"title": "Form Analizi", "body": f"{home_name} form skoru {home.get('form_score', 0):.1f}, {away_name} form skoru {away.get('form_score', 0):.1f}. Trend etiketi sırasıyla {home.get('trend', 'stabil')} ve {away.get('trend', 'stabil')}."},
            {"title": "Hücum ve Savunma Gücü", "body": f"Hücum: {home_name} {home.get('attack_score', 0):.1f} | {away_name} {away.get('attack_score', 0):.1f}. Savunma: {home_name} {home.get('defense_score', 0):.1f} | {away_name} {away.get('defense_score', 0):.1f}. xG/pxG tabanı: {home_name} {home.get('xg_for', 0):.2f}, {away_name} {away.get('xg_for', 0):.2f}."},
            {"title": "Poisson + Dixon-Coles", "body": f"Lambda değerleri ev {float(scenarios.get('lambda_home', 0.0)):.2f}, deplasman {float(scenarios.get('lambda_away', 0.0)):.2f}. 1X2: Ev %{round(float(scenarios.get('one_x_two', {}).get('home', 0.0)) * 100.0, 1)} | X %{round(float(scenarios.get('one_x_two', {}).get('draw', 0.0)) * 100.0, 1)} | 2 %{round(float(scenarios.get('one_x_two', {}).get('away', 0.0)) * 100.0, 1)}."},
            {"title": "ELO Benzeri Güç Skoru", "body": f"İç sistem ELO-benzeri rating: {home_name} {home.get('elo_like_rating', 0):.0f}, {away_name} {away.get('elo_like_rating', 0):.0f}. Genel güç farkı {power_edge_label(float(shared.get('comparison_edge', 0.0) or 0.0)).lower()} olarak okunuyor."},
            {"title": "Ensemble Sonuç", "body": f"Üst 2.5 %{round(float(scenarios.get('totals', {}).get('over_2_5', 0.0)) * 100.0, 1)}, Alt 2.5 %{round(float(scenarios.get('totals', {}).get('under_2_5', 0.0)) * 100.0, 1)}, KG Var %{round(float(scenarios.get('btts', {}).get('yes', 0.0)) * 100.0, 1)}. {commentary['detailed']}"},
        ]
        payload = self._common_payload(snapshot, features, scenarios, confidence)
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
        report_blocks = [
            {"title": "Analiz Uyarısı", "body": self.spec["warning"]},
            {"title": "Kısa Yorum", "body": commentary["short"]},
            {"title": "Detaylı Yorum", "body": commentary["detailed"]},
            {"title": "Uzman Yorumu", "body": commentary["expert"]},
            {"title": "Alan Bazlı Üstünlük", "body": f"Form {home_name} {home.get('form_score', 0):.1f} - {away_name} {away.get('form_score', 0):.1f}, hücum {home_name} {home.get('attack_score', 0):.1f} - {away_name} {away.get('attack_score', 0):.1f}, savunma {home_name} {home.get('defense_score', 0):.1f} - {away_name} {away.get('defense_score', 0):.1f}."},
            {"title": "Senaryo Motoru", "body": "\n".join(scenario_lines or ["- Belirgin senaryo üretmek için veri sınırlı."])},
            {"title": "Riskler ve Veri Boşlukları", "body": "\n".join(f"- {line}" for line in ((risks or []) + list(snapshot.get('data_gaps') or []))[:8]) or "- Ek risk sinyali yok."},
        ]
        payload = self._common_payload(snapshot, features, scenarios, confidence)
        payload["report_blocks"] = report_blocks
        payload["header_summary"] = {"home_team": home_name, "away_team": away_name, "comparison_date": snapshot.get("generated_at"), "data_window": snapshot.get("request", {}).get("data_window"), "league_context": scenarios.get("league_context")}
        return payload
