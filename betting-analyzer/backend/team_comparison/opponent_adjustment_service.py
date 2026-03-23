from __future__ import annotations

from typing import Any, Dict


class TeamComparisonOpponentAdjustmentService:
    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _winner(home_value: float, away_value: float) -> str:
        if abs(home_value - away_value) < 1.5:
            return "draw"
        return "home" if home_value > away_value else "away"

    @staticmethod
    def _winner_label(snapshot: Dict[str, Any], winner: str) -> str:
        if winner == "home":
            return str(snapshot.get("home", {}).get("team", {}).get("name") or "Ev Sahibi")
        if winner == "away":
            return str(snapshot.get("away", {}).get("team", {}).get("name") or "Deplasman")
        return "dengede"

    def _power_index(self, team_features: Dict[str, Any]) -> float:
        attack = float(team_features.get("attack_score", 0.0) or 0.0)
        defense = float(team_features.get("defense_score", 0.0) or 0.0)
        form = float(team_features.get("form_score", 0.0) or 0.0)
        home_away = float(team_features.get("home_away_score", 0.0) or 0.0)
        squad = float(team_features.get("squad_score", 0.0) or 0.0)
        context = float(team_features.get("context_score", 0.0) or 0.0)
        points_per_game = float(team_features.get("points_per_game", 0.0) or 0.0)
        rating = float(team_features.get("average_rating", 0.0) or 0.0)
        value = 0.22 * attack + 0.2 * defense + 0.18 * form + 0.12 * home_away + 0.14 * squad + 0.08 * context + 3.5 * points_per_game + max(0.0, rating - 6.0) * 4.0
        return round(self._clamp(value), 2)

    def _build_card(self, *, key: str, label: str, snapshot: Dict[str, Any], home_value: float, away_value: float, explanation: str) -> Dict[str, Any]:
        winner = self._winner(home_value, away_value)
        return {
            "key": key,
            "label": label,
            "home_score": round(home_value, 2),
            "away_score": round(away_value, 2),
            "edge": round(home_value - away_value, 2),
            "winner": winner,
            "winner_label": self._winner_label(snapshot, winner),
            "explanation": explanation,
        }

    def apply(self, features: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
        home = dict(features.get("home") or {})
        away = dict(features.get("away") or {})

        home_power = self._power_index(home)
        away_power = self._power_index(away)
        home["power_index"] = home_power
        away["power_index"] = away_power
        home["elo_like_rating"] = round(1500 + home_power * 5 + 55, 2)
        away["elo_like_rating"] = round(1500 + away_power * 5, 2)

        power_gap = (home_power - away_power) / 100.0
        home["adjusted_attack_score"] = round(self._clamp(home.get("attack_score", 0.0) * (1.0 + power_gap / 5.0)), 2)
        away["adjusted_attack_score"] = round(self._clamp(away.get("attack_score", 0.0) * (1.0 - power_gap / 5.0)), 2)
        home["adjusted_defense_score"] = round(self._clamp(home.get("defense_score", 0.0) * (1.0 + power_gap / 6.0)), 2)
        away["adjusted_defense_score"] = round(self._clamp(away.get("defense_score", 0.0) * (1.0 - power_gap / 6.0)), 2)

        general_power_home = self._clamp(
            0.16 * float(home.get("attack_score", 0.0))
            + 0.16 * float(home.get("defense_score", 0.0))
            + 0.14 * float(home.get("form_score", 0.0))
            + 0.12 * float(home.get("home_away_score", 0.0))
            + 0.08 * float(home.get("tempo_score", 0.0))
            + 0.08 * float(home.get("set_piece_score", 0.0))
            + 0.08 * float(home.get("transition_score", 0.0))
            + 0.08 * float(home.get("resilience_score", 0.0))
            + 0.05 * float(home.get("squad_score", 0.0))
            + 0.05 * float(home.get("context_score", 0.0))
        )
        general_power_away = self._clamp(
            0.16 * float(away.get("attack_score", 0.0))
            + 0.16 * float(away.get("defense_score", 0.0))
            + 0.14 * float(away.get("form_score", 0.0))
            + 0.12 * float(away.get("home_away_score", 0.0))
            + 0.08 * float(away.get("tempo_score", 0.0))
            + 0.08 * float(away.get("set_piece_score", 0.0))
            + 0.08 * float(away.get("transition_score", 0.0))
            + 0.08 * float(away.get("resilience_score", 0.0))
            + 0.05 * float(away.get("squad_score", 0.0))
            + 0.05 * float(away.get("context_score", 0.0))
        )
        comparison_edge = round(max(-100.0, min(100.0, (general_power_home - general_power_away) * 1.4)), 2)

        cards = [
            self._build_card(key="general_power", label="Genel Güç", snapshot=snapshot, home_value=general_power_home, away_value=general_power_away, explanation="Form, hücum, savunma ve bağlam skorlarının birleşik görünümü."),
            self._build_card(key="attack", label="Hücum", snapshot=snapshot, home_value=float(home.get("attack_score", 0.0)), away_value=float(away.get("attack_score", 0.0)), explanation="Gol üretimi, xG/proxy xG, şut kalitesi ve hücum sürekliliği birlikte okunur."),
            self._build_card(key="defense", label="Savunma", snapshot=snapshot, home_value=float(home.get("defense_score", 0.0)), away_value=float(away.get("defense_score", 0.0)), explanation="Yenilen gol, xGA eğilimi, clean sheet oranı ve son bölüm kırılganlığı hesaba katılır."),
            self._build_card(key="form", label="Form", snapshot=snapshot, home_value=float(home.get("form_score", 0.0)), away_value=float(away.get("form_score", 0.0)), explanation="Yakın dönem ağırlıklı form ve trend sinyali birlikte değerlendirilir."),
            self._build_card(key="home_away", label="İç Saha / Deplasman", snapshot=snapshot, home_value=float(home.get("home_away_score", 0.0)), away_value=float(away.get("home_away_score", 0.0)), explanation="Ev sahibinin iç saha, deplasman takımının dış saha performans penceresi kullanılır."),
            self._build_card(key="tempo", label="Tempo", snapshot=snapshot, home_value=float(home.get("tempo_score", 0.0)), away_value=float(away.get("tempo_score", 0.0)), explanation="Şut hacmi, korner üretimi ve gollü maç eğilimi tempo skorunu besler."),
            self._build_card(key="set_piece", label="Duran Top", snapshot=snapshot, home_value=float(home.get("set_piece_score", 0.0)), away_value=float(away.get("set_piece_score", 0.0)), explanation="Korner, kafa golü ve serbest vuruş katkıları duran top tehdidini temsil eder."),
            self._build_card(key="transition", label="Geçiş Oyunu", snapshot=snapshot, home_value=float(home.get("transition_score", 0.0)), away_value=float(away.get("transition_score", 0.0)), explanation="Kontra atak eğilimi, büyük şans ve isabetli şut üretimi geçiş skorunu belirler."),
            self._build_card(key="squad", label="Kadro Bütünlüğü", snapshot=snapshot, home_value=float(home.get("squad_score", 0.0)), away_value=float(away.get("squad_score", 0.0)), explanation="Üst düzey oyuncu kalitesi, piyasa değeri ve eksik oyuncu cezası birlikte ele alınır."),
        ]
        card_map = {card["key"]: card for card in cards}

        axes = [
            self._build_card(key="general_form", label="Genel Form", snapshot=snapshot, home_value=float(home.get("form_score", 0.0)), away_value=float(away.get("form_score", 0.0)), explanation="Son 10 maç ağırlıklı form puanı."),
            self._build_card(key="attack_power", label="Hücum Gücü", snapshot=snapshot, home_value=float(home.get("attack_score", 0.0)), away_value=float(away.get("attack_score", 0.0)), explanation="Gol ve xG üretim kapasitesi."),
            self._build_card(key="defense_security", label="Savunma Güvenliği", snapshot=snapshot, home_value=float(home.get("defense_score", 0.0)), away_value=float(away.get("defense_score", 0.0)), explanation="Savunma kırılganlığı ve clean sheet dengesi."),
            self._build_card(key="venue_edge", label="İç Saha / Deplasman Avantajı", snapshot=snapshot, home_value=float(home.get("home_away_score", 0.0)), away_value=float(away.get("home_away_score", 0.0)), explanation="Takımların rol bazlı performansı."),
            self._build_card(key="tempo_rhythm", label="Tempo ve Oyun Ritmi", snapshot=snapshot, home_value=float(home.get("tempo_score", 0.0)), away_value=float(away.get("tempo_score", 0.0)), explanation="Şut yoğunluğu ve maç hızı."),
            self._build_card(key="set_piece_effect", label="Duran Top Etkinliği", snapshot=snapshot, home_value=float(home.get("set_piece_score", 0.0)), away_value=float(away.get("set_piece_score", 0.0)), explanation="Korner ve duran top üretimi."),
            self._build_card(key="transition_game", label="Geçiş Oyunu", snapshot=snapshot, home_value=float(home.get("transition_score", 0.0)), away_value=float(away.get("transition_score", 0.0)), explanation="Geçiş hücumları ve hızlı aksiyon tehdidi."),
            self._build_card(key="first_half", label="İlk Yarı Başlangıç Gücü", snapshot=snapshot, home_value=float(home.get("first_half_pressure_score", 0.0)), away_value=float(away.get("first_half_pressure_score", 0.0)), explanation="Maça hızlı başlama ve ilk yarı üretkenliği."),
            self._build_card(key="second_half", label="İkinci Yarı Direnç", snapshot=snapshot, home_value=float(home.get("resilience_score", 0.0)), away_value=float(away.get("resilience_score", 0.0)), explanation="İkinci yarı dayanıklılık ve geç oyuna tepki."),
            self._build_card(key="score_protection", label="Skor Koruma Kabiliyeti", snapshot=snapshot, home_value=float(home.get("score_protection_score", 0.0)), away_value=float(away.get("score_protection_score", 0.0)), explanation="Öne geçildiğinde skoru koruma kapasitesi."),
            self._build_card(key="comeback", label="Geri Dönüş Kabiliyeti", snapshot=snapshot, home_value=float(home.get("comeback_score", 0.0)), away_value=float(away.get("comeback_score", 0.0)), explanation="Geriden gelip üretken kalabilme kabiliyeti."),
            self._build_card(key="goal_expectation", label="Gol Beklentisi", snapshot=snapshot, home_value=float(home.get("goal_expectation_score", 0.0)), away_value=float(away.get("goal_expectation_score", 0.0)), explanation="xG tabanı ve gollü maç sinyali."),
            self._build_card(key="opponent_resilience", label="Rakip Kalitesine Karşı Dayanıklılık", snapshot=snapshot, home_value=home_power, away_value=away_power, explanation="Takımın genel güç endeksi ve bağlam dayanıklılığı."),
            self._build_card(key="squad_integrity", label="Kadro Bütünlüğü", snapshot=snapshot, home_value=float(home.get("squad_score", 0.0)), away_value=float(away.get("squad_score", 0.0)), explanation="Eksik oyuncu ve üst düzey kalite dengesi."),
            self._build_card(key="data_reliability", label="Veri Güvenilirliği", snapshot=snapshot, home_value=float(home.get("data_reliability_score", 0.0)), away_value=float(away.get("data_reliability_score", 0.0)), explanation="Kullanılan örneklem ve kaynak kapsamı."),
        ]

        shared = {"cards": cards, "axes": axes, **card_map, "comparison_edge": comparison_edge}
        return {**features, "home": home, "away": away, "shared": shared}
