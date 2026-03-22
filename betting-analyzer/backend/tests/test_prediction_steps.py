from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from prediction_engine.steps.step1_features import build_features
from prediction_engine.steps.step2_xg import predict_xg
from prediction_engine.steps.step3_dixon_coles import compute_probabilities
from prediction_engine.steps.step5_odds import check_line_movement, remove_vig
from prediction_engine.steps.step6_drift import validate_drift
from prediction_engine.steps.step8_ev import compute_ev, ev_valid
from prediction_engine.steps.step9_stake import final_stake, kelly_stake


def run_step_tests() -> None:
    features = build_features(
        home_stats={"last6": ["W", "D", "W"], "avg_goals_for": 1.7, "avg_goals_against": 1.0, "home_avg_goals_for": 2.0, "home_avg_goals_against": 0.9},
        away_stats={"last6": ["L", "D", "L"], "avg_goals_for": 1.0, "avg_goals_against": 1.5, "away_avg_goals_for": 0.8, "away_avg_goals_against": 1.6},
        h2h={"avg_home_goals": 1.6, "avg_away_goals": 0.9, "matches": [{}, {}]},
        league="Premier League",
    )
    assert 0 <= features["home_form"] <= 1
    assert 0 <= features["away_form"] <= 1

    home_xg, away_xg = predict_xg(features)
    assert home_xg > 0
    assert away_xg > 0

    probs, lambdas = compute_probabilities(home_xg, away_xg, "Premier League")
    assert abs((probs["MS1"] + probs["MSX"] + probs["MS2"]) - 1.0) < 0.02
    assert abs((probs["IY1"] + probs["IYX"] + probs["IY2"]) - 1.0) < 0.02
    assert lambdas["home"] > 0 and lambdas["away"] > 0

    no_vig = remove_vig({"MS1": 2.0, "MSX": 3.4, "MS2": 4.0})
    assert abs(sum(no_vig.values()) - 1.0) < 0.001

    drift = validate_drift({"MS1": 0.5}, {"MS1": 0.45})
    assert "MS1" in drift

    assert check_line_movement(2.0, 1.6)
    assert not check_line_movement(2.0, 1.9)

    ev = compute_ev(0.55, 2.0)
    assert ev > 0
    ok, reason = ev_valid("MS1", ev)
    assert isinstance(ok, bool)
    assert reason is None or isinstance(reason, str)

    kelly = kelly_stake(0.55, 2.0, 66)
    stake = final_stake(kelly, 66, bankroll=1000.0)
    assert stake["final_stake"] >= 0


if __name__ == "__main__":
    run_step_tests()
    print("Prediction engine step tests passed")
