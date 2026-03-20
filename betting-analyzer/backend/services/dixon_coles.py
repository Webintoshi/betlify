from __future__ import annotations

from typing import Dict

import numpy as np
from scipy.stats import poisson


def rho_correction(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - (lam * mu * rho)
    if x == 0 and y == 1:
        return 1 + (lam * rho)
    if x == 1 and y == 0:
        return 1 + (mu * rho)
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def score_matrix(lam: float, mu: float, rho: float = -0.13, max_goals: int = 8) -> np.ndarray:
    goals_cap = max(4, int(max_goals))
    lam = max(0.05, float(lam))
    mu = max(0.05, float(mu))
    matrix = np.zeros((goals_cap + 1, goals_cap + 1))
    for i in range(goals_cap + 1):
        for j in range(goals_cap + 1):
            matrix[i][j] = (
                poisson.pmf(i, lam)
                * poisson.pmf(j, mu)
                * rho_correction(i, j, lam, mu, rho)
            )
    matrix = np.clip(matrix, 0, None)
    total = float(matrix.sum())
    if total <= 0:
        return np.ones((goals_cap + 1, goals_cap + 1)) / float((goals_cap + 1) ** 2)
    return matrix / total


def compute_match_probs(lam_home: float, mu_away: float, rho: float = -0.13) -> Dict[str, float]:
    matrix = score_matrix(lam_home, mu_away, rho=rho)
    n = matrix.shape[0]

    ms1 = float(np.sum(np.tril(matrix, -1)))
    ms2 = float(np.sum(np.triu(matrix, 1)))
    msx = float(np.trace(matrix))

    o15 = float(1 - sum(matrix[i][j] for i in range(n) for j in range(n) if i + j <= 1))
    o25 = float(1 - sum(matrix[i][j] for i in range(n) for j in range(n) if i + j <= 2))
    u25 = float(1 - o25)
    u15 = float(1 - o15)

    kg_var = float(1 - sum(matrix[i][j] for i in range(n) for j in range(n) if i == 0 or j == 0))
    kg_yok = float(1 - kg_var)

    return {
        "MS1": round(ms1, 5),
        "MSX": round(msx, 5),
        "MS2": round(ms2, 5),
        "MS_O1.5": round(o15, 5),
        "MS_U1.5": round(u15, 5),
        "MS_O2.5": round(o25, 5),
        "MS_U2.5": round(u25, 5),
        "KG_VAR": round(kg_var, 5),
        "KG_YOK": round(kg_yok, 5),
    }


def compute_ht_probs(ht_lam: float, ht_mu: float, rho: float = -0.10) -> Dict[str, float]:
    matrix = score_matrix(ht_lam, ht_mu, rho=rho, max_goals=5)
    n = matrix.shape[0]

    iy1 = float(sum(matrix[i][j] for i in range(n) for j in range(n) if i > j))
    iyx = float(sum(matrix[i][j] for i in range(n) for j in range(n) if i == j))
    iy2 = float(sum(matrix[i][j] for i in range(n) for j in range(n) if i < j))

    return {
        "IY1": round(iy1, 5),
        "IYX": round(iyx, 5),
        "IY2": round(iy2, 5),
    }
