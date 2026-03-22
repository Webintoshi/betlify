from __future__ import annotations


def ensemble(dc_probs: dict, ml_probs: dict | None, dc_w: float = 0.65, ml_w: float = 0.35) -> dict:
    """Blend Dixon-Coles and ML probabilities when ML is available."""
    if ml_probs is None:
        return dict(dc_probs)
    return {
        market: round(dc_w * dc_probs.get(market, 0.0) + ml_w * ml_probs.get(market, dc_probs.get(market, 0.0)), 5)
        for market in dc_probs
    }
