from __future__ import annotations

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
    "MS1": {"min": 0.05, "max": 0.18},
    "MSX": {"min": 0.05, "max": 0.22},
    "MS2": {"min": 0.05, "max": 0.20},
    "MS_O2.5": {"min": 0.05, "max": 0.15},
    "MS_U2.5": {"min": 0.05, "max": 0.15},
    "MS_O1.5": {"min": 0.04, "max": 0.12},
    "KG_VAR": {"min": 0.05, "max": 0.18},
    "KG_YOK": {"min": 0.05, "max": 0.18},
    "IY1": {"min": 0.05, "max": 0.20},
    "IYX": {"min": 0.05, "max": 0.22},
    "IY2": {"min": 0.05, "max": 0.22},
}

MAX_DRIFT = {
    "MS1": 0.15,
    "MSX": 0.18,
    "MS2": 0.15,
    "MS_O2.5": 0.18,
    "MS_U2.5": 0.18,
    "MS_O1.5": 0.16,
    "KG_VAR": 0.18,
    "KG_YOK": 0.18,
    "IY1": 0.18,
    "IYX": 0.18,
    "IY2": 0.18,
}

SUPPORTED_MARKETS = list(VALID_MARKETS.keys())
