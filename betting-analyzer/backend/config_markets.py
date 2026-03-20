from __future__ import annotations

EXCLUDED_MARKETS = {
    "IY_O0.5",
    "IY_U0.5",
    "IY_O1.5",
    "IY_U1.5",
    "IY_O2.5",
    "IY_U2.5",
}

VALID_MARKETS = {
    "MS1": {"min_prob": 0.35, "max_prob": 0.80, "min_odd": 1.25, "max_odd": 4.50},
    "MSX": {"min_prob": 0.20, "max_prob": 0.45, "min_odd": 2.00, "max_odd": 6.00},
    "MS2": {"min_prob": 0.20, "max_prob": 0.65, "min_odd": 1.30, "max_odd": 6.00},
    "MS_O2.5": {"min_prob": 0.40, "max_prob": 0.78, "min_odd": 1.30, "max_odd": 3.50},
    "MS_U2.5": {"min_prob": 0.25, "max_prob": 0.62, "min_odd": 1.30, "max_odd": 3.50},
    "MS_O1.5": {"min_prob": 0.55, "max_prob": 0.92, "min_odd": 1.15, "max_odd": 2.50},
    "KG_VAR": {"min_prob": 0.38, "max_prob": 0.72, "min_odd": 1.30, "max_odd": 3.00},
    "KG_YOK": {"min_prob": 0.28, "max_prob": 0.62, "min_odd": 1.30, "max_odd": 3.50},
    "IY1": {"min_prob": 0.25, "max_prob": 0.65, "min_odd": 1.40, "max_odd": 5.00},
    "IYX": {"min_prob": 0.28, "max_prob": 0.58, "min_odd": 1.60, "max_odd": 4.50},
    "IY2": {"min_prob": 0.12, "max_prob": 0.50, "min_odd": 1.60, "max_odd": 8.00},
}

EV_THRESHOLDS = {
    "MS1": {"min": 0.030, "max": 0.180},
    "MSX": {"min": 0.035, "max": 0.220},
    "MS2": {"min": 0.030, "max": 0.200},
    "MS_O2.5": {"min": 0.025, "max": 0.150},
    "MS_U2.5": {"min": 0.025, "max": 0.150},
    "MS_O1.5": {"min": 0.020, "max": 0.120},
    "KG_VAR": {"min": 0.030, "max": 0.180},
    "KG_YOK": {"min": 0.030, "max": 0.180},
    "IY1": {"min": 0.035, "max": 0.200},
    "IYX": {"min": 0.040, "max": 0.220},
    "IY2": {"min": 0.035, "max": 0.220},
}

MIN_CONFIDENCE_SCORE = 55.0
MIN_KELLY_PCT = 1.5
FRACTIONAL_KELLY = 0.25
