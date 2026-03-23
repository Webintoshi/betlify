from __future__ import annotations

from typing import Any, Dict, List


def confidence_label(score: float) -> str:
    if score >= 85:
        return "Yüksek Güven"
    if score >= 70:
        return "İyi Güven"
    if score >= 55:
        return "Orta Güven"
    if score >= 40:
        return "Düşük Güven"
    return "Sınırlı Güven"


def data_quality_label(score: float) -> str:
    if score >= 80:
        return "Veri yeterliliği güçlü"
    if score >= 60:
        return "Veri yeterliliği makul"
    if score >= 40:
        return "Veri yeterliliği sınırlı"
    return "Veri yeterliliği zayıf"


def power_edge_label(edge: float) -> str:
    absolute_edge = abs(edge)
    if absolute_edge >= 20:
        return "Açık üstünlük"
    if absolute_edge >= 10:
        return "Belirgin üstünlük"
    if absolute_edge >= 4:
        return "Hafif üstünlük"
    return "Dengeli görünüm"


def build_risk_factors(snapshot: Dict[str, Any], shared_cards: List[Dict[str, Any]], confidence: Dict[str, Any]) -> List[str]:
    risks: List[str] = []
    if bool(snapshot.get("cross_league")):
        risks.append("Takımlar farklı lig bağlamından geldiği için karşılaştırma güvenirliği düşüyor.")
    if int(snapshot.get("home", {}).get("injury_count", 0)) > 0 or int(snapshot.get("away", {}).get("injury_count", 0)) > 0:
        risks.append("Eksik oyuncu bilgileri karşılaştırma dengesini etkileyebilir.")
    if float(confidence.get("confidence_score", 0.0) or 0.0) < 55:
        risks.append("Model güven skoru düşük; sonuçlar temkinli okunmalı.")
    if float(confidence.get("data_quality_score", 0.0) or 0.0) < 50:
        risks.append("Veri kapsaması sınırlı olduğu için bazı metrikler fallback ile üretildi.")
    low_gap_cards = [card for card in shared_cards if abs(float(card.get("edge", 0.0) or 0.0)) < 4]
    if len(low_gap_cards) >= 4:
        risks.append("Birçok ana eksen birbirine yakın; maç dengeli akışa açık.")
    return risks


def build_common_commentary(snapshot: Dict[str, Any], features: Dict[str, Any], scenarios: Dict[str, Any]) -> Dict[str, str]:
    home_name = str(snapshot.get("home", {}).get("team", {}).get("name") or "Ev Sahibi")
    away_name = str(snapshot.get("away", {}).get("team", {}).get("name") or "Deplasman")
    attack_winner = str(features.get("shared", {}).get("attack", {}).get("winner_label") or "dengede")
    defense_winner = str(features.get("shared", {}).get("defense", {}).get("winner_label") or "dengede")
    top_scenario = (scenarios.get("scenarios") or [{}])[0]
    scenario_title = str(top_scenario.get("title") or "Dengeli maç")
    short = (
        f"{home_name} ile {away_name} karşılaştırmasında hücum tarafında {attack_winner}, savunma tarafında ise {defense_winner} öne çıkıyor. "
        f"Mevcut veri seti maçın {scenario_title.lower()} senaryosuna daha yakın olduğunu gösteriyor."
    )
    detailed = (
        f"Karşılaştırma modeli; son form, iç saha/deplasman ayrımı, sezon istatistikleri ve mevcut takım verilerini birlikte okuyarak {home_name} ile {away_name} arasındaki güç farkını oluşturdu. "
        f"Hücum üretkenliği, savunma dayanıklılığı ve tempo sinyalleri aynı yöne bakıyorsa güven artıyor, çelişkili sinyal varsa sonuç temkinli etiketleniyor."
    )
    expert = (
        f"Bu eşleşmede tek veri noktasına dayalı yorum yapılmıyor. Ağırlıklı form pencereleri, hücum-skor üretimi, xG ya da proxy xG, home/away farkı ve senaryo motoru birlikte kullanıldığı için çıktı açıklanabilir ama sonuç tek yönlü okunmamalı."
    )
    return {"short": short, "detailed": detailed, "expert": expert}
