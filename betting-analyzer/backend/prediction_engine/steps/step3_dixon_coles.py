from __future__ import annotations

import numpy as np
from scipy.stats import poisson

from prediction_engine.config.settings import HOME_ADVANTAGE, HT_LAMBDA_RATIO, RHO_BY_LEAGUE


def rho_correction(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    if x == 0 and y == 1:
        return 1 + lam * rho
    if x == 1 and y == 0:
        return 1 + mu * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def score_matrix(lam: float, mu: float, rho: float, max_goals: int = 8) -> np.ndarray:
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            matrix[i][j] = poisson.pmf(i, lam) * poisson.pmf(j, mu) * rho_correction(i, j, lam, mu, rho)
    matrix = np.clip(matrix, 0, None)
    total = float(matrix.sum())
    if total <= 0:
        return np.ones((max_goals + 1, max_goals + 1)) / float((max_goals + 1) ** 2)
    return matrix / total


def compute_probabilities(home_xg: float, away_xg: float, league: str = "default") -> tuple[dict, dict]:
    rho = RHO_BY_LEAGUE.get(league, RHO_BY_LEAGUE["default"])

    lam = max(0.3, min(HOME_ADVANTAGE * home_xg, 4.5))
    mu = max(0.3, min(away_xg, 4.0))
    ht_lam = round(lam * HT_LAMBDA_RATIO, 4)
    ht_mu = round(mu * HT_LAMBDA_RATIO, 4)

    matrix = score_matrix(lam, mu, rho, max_goals=8)
    ht_matrix = score_matrix(ht_lam, ht_mu, rho * 0.8, max_goals=5)

    def group_prob(source: np.ndarray, predicate) -> float:
        size = source.shape[0]
        return float(sum(source[i][j] for i in range(size) for j in range(size) if predicate(i, j)))

    probabilities = {
        "MS1": round(group_prob(matrix, lambda i, j: i > j), 5),
        "MSX": round(group_prob(matrix, lambda i, j: i == j), 5),
        "MS2": round(group_prob(matrix, lambda i, j: i < j), 5),
        "MS_O2.5": round(group_prob(matrix, lambda i, j: (i + j) > 2.5), 5),
        "MS_U2.5": round(group_prob(matrix, lambda i, j: (i + j) < 2.5), 5),
        "MS_O1.5": round(group_prob(matrix, lambda i, j: (i + j) > 1.5), 5),
        "KG_VAR": round(group_prob(matrix, lambda i, j: i > 0 and j > 0), 5),
        "KG_YOK": round(group_prob(matrix, lambda i, j: i == 0 or j == 0), 5),
        "IY1": round(group_prob(ht_matrix, lambda i, j: i > j), 5),
        "IYX": round(group_prob(ht_matrix, lambda i, j: i == j), 5),
        "IY2": round(group_prob(ht_matrix, lambda i, j: i < j), 5),
    }

    lambdas = {"home": lam, "away": mu, "ht_home": ht_lam, "ht_away": ht_mu}
    return probabilities, lambdas
