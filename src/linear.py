"""Least squares and logistic regression, both with cluster-robust errors.

Carried over from the earlier projects in this series, with the docstring
rewritten for what it is doing here.

**Why both.** The main question is "how many places", which is least
squares. But the one exclusion that could bend the answer - that a
retirement has no finishing position - is a yes-or-no question about
every entry, and that is a logit. A linear probability model would answer
it too, and would predict negative chances of retiring for the front row,
which is one of the two ends of the grid the check is about.

**Clustering.** Errors are clustered on the race throughout, because a
penalty to one car promotes every car behind it. The twenty rows of one
Sunday are one event seen twenty times. The small-sample correction
counts clusters rather than rows.

**Separation.** A logit fitted on a covariate that predicts the outcome
perfectly has no finite maximum, and the coefficients run away while the
fit looks superb. `logit` watches for it and refuses. That is not a
hypothetical here: a driver-season in which the car finished every race
is a column that predicts "classified" perfectly, and there are many of
them. `confound.retirement` is fitted with season effects for exactly
this reason, and checks the claim rather than asserting it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

MAX_STEPS = 100
TOLERANCE = 1e-10
RUNAWAY = 40.0        # |x'b| beyond this is separation, not a strong effect


@dataclass(frozen=True)
class Fit:
    """A fitted model and its cluster-robust covariance."""

    names: tuple[str, ...]
    beta: np.ndarray
    covariance: np.ndarray
    n: int
    groups: int
    label: str = ""
    kind: str = "ols"
    fit_statistic: float = float("nan")   # R squared, or McFadden's for logit

    def __getitem__(self, name: str) -> float:
        return float(self.beta[self.names.index(name)])

    def error(self, name: str) -> float:
        index = self.names.index(name)
        return float(np.sqrt(self.covariance[index, index]))

    def t_value(self, name: str) -> float:
        return self[name] / self.error(name)

    def p_value(self, name: str) -> float:
        return float(2 * stats.t.sf(abs(self.t_value(name)),
                                    max(self.groups - 1, 1)))

    def interval(self, name: str, alpha: float = 0.05) -> tuple[float, float]:
        half = stats.t.ppf(1 - alpha / 2, max(self.groups - 1, 1))
        spread = half * self.error(name)
        return self[name] - spread, self[name] + spread

    def index(self, name: str) -> int:
        return self.names.index(name)


def _check(y: np.ndarray, matrix: np.ndarray, names: tuple[str, ...],
           group: np.ndarray) -> None:
    if matrix.shape[0] != y.size:
        raise ValueError("design and outcome have different lengths")
    if group.size != y.size:
        raise ValueError("cluster labels and outcome have different lengths")
    rank = np.linalg.matrix_rank(matrix)
    if rank < matrix.shape[1]:
        raise ValueError(
            f"the design is rank deficient (rank {rank} < "
            f"{matrix.shape[1]} columns: {', '.join(names)})")


def _sandwich(bread: np.ndarray, score: np.ndarray, group: np.ndarray,
              n: int, k: int) -> tuple[np.ndarray, int]:
    """Liang-Zeger meat, summed within clusters, with a cluster correction."""
    labels = np.unique(group)
    meat = np.zeros((k, k))
    for one in labels:
        total = score[group == one].sum(axis=0)
        meat += np.outer(total, total)
    clusters = labels.size
    correction = (clusters / max(clusters - 1, 1)) * \
                 ((n - 1) / max(n - k, 1))
    return bread @ meat @ bread * correction, int(clusters)


def ols(y: np.ndarray, matrix: np.ndarray, names: tuple[str, ...],
        group: np.ndarray, *, label: str = "") -> Fit:
    """Least squares with Liang-Zeger cluster-robust covariance."""
    _check(y, matrix, names, group)
    beta, *_ = np.linalg.lstsq(matrix, y, rcond=None)
    residual = y - matrix @ beta
    bread = np.linalg.inv(matrix.T @ matrix)
    covariance, clusters = _sandwich(
        bread, matrix * residual[:, None], group, y.size, matrix.shape[1])

    centred = y - y.mean()
    spread = float(centred @ centred)
    # A constant outcome has no variance to explain, so this is undefined
    # rather than zero.
    explained = (1 - float(residual @ residual) / spread
                 if spread > 0 else float("nan"))
    return Fit(names=tuple(names), beta=beta, covariance=covariance,
               n=int(y.size), groups=clusters, label=label, kind="ols",
               fit_statistic=explained)


def logit(y: np.ndarray, matrix: np.ndarray, names: tuple[str, ...],
          group: np.ndarray, *, label: str = "") -> Fit:
    """Logistic regression by Newton-Raphson, cluster-robust covariance.

    The outcome must be zero or one. The returned coefficients are on the
    log-odds scale, so they are read through `probability` rather than
    directly.
    """
    _check(y, matrix, names, group)
    if not np.isin(y, (0.0, 1.0)).all():
        raise ValueError("a logit needs a zero/one outcome")
    if y.min() == y.max():
        raise ValueError("the outcome never varies, so nothing is identified")

    k = matrix.shape[1]
    beta = np.zeros(k)
    for _ in range(MAX_STEPS):
        linear = matrix @ beta
        if np.abs(linear).max() > RUNAWAY:
            raise ValueError(
                "the fit is separating: some column predicts the outcome "
                "perfectly, so the maximum is not finite")
        probability = 1.0 / (1.0 + np.exp(-linear))
        weight = probability * (1.0 - probability)
        hessian = matrix.T @ (matrix * weight[:, None])
        if np.linalg.matrix_rank(hessian) < k:
            raise ValueError(
                "the weighted design has lost rank, which is what "
                "separating looks like once the weights collapse")
        step = np.linalg.solve(hessian, matrix.T @ (y - probability))
        beta = beta + step
        if np.abs(step).max() < TOLERANCE:
            break
    else:
        raise ValueError("the fit did not settle within the step limit")

    linear = matrix @ beta
    probability = 1.0 / (1.0 + np.exp(-linear))
    weight = probability * (1.0 - probability)
    bread = np.linalg.inv(matrix.T @ (matrix * weight[:, None]))
    covariance, clusters = _sandwich(
        bread, matrix * (y - probability)[:, None], group, y.size, k)

    share = float(y.mean())
    null = float(np.sum(y * np.log(share) + (1 - y) * np.log(1 - share)))
    full = float(np.sum(y * np.log(probability)
                        + (1 - y) * np.log(1 - probability)))
    return Fit(names=tuple(names), beta=beta, covariance=covariance,
               n=int(y.size), groups=clusters, label=label, kind="logit",
               fit_statistic=1 - full / null if null else float("nan"))


def probability(fit: Fit, row: np.ndarray) -> float:
    """The fitted chance for one design row, on the zero-to-one scale."""
    return float(1.0 / (1.0 + np.exp(-(row @ fit.beta))))


def joint_test(fit: Fit, names: tuple[str, ...]) -> dict:
    """Wald test that a block of coefficients is jointly zero.

    Asked of the circuit terms, this is the question "does the track
    matter at all, once the pace difference is accounted for?" - which a
    column of individually overlapping intervals cannot answer, because
    a set of estimates can each be indistinguishable from zero while
    being jointly very far from it.

    The statistic is referred to an F distribution with the number of
    clusters setting the denominator, since a cluster-robust covariance
    built from a few hundred clusters is itself estimated.
    """
    picked = [fit.index(name) for name in names if name in fit.names]
    if not picked:
        return {"terms": 0}
    beta = fit.beta[picked]
    block = fit.covariance[np.ix_(picked, picked)]
    if np.linalg.matrix_rank(block) < len(picked):
        raise ValueError("the covariance of this block is singular")
    statistic = float(beta @ np.linalg.solve(block, beta))
    degrees = len(picked)
    denominator = max(fit.groups - degrees, 1)
    f_value = statistic / degrees
    return {"terms": degrees, "chi square": statistic, "F": f_value,
            "p": float(stats.f.sf(f_value, degrees, denominator))}


def combination(fit: Fit, weights: dict[str, float]) -> dict:
    """A weighted sum of coefficients, with the covariance carried through.

    The quantity this project most wants is a difference between two
    slopes - what a qualifying slot is worth against what a grid slot is
    worth - and the two come out of the same fit, so their errors are
    correlated. Adding the standard errors in quadrature as though they
    were independent would misstate the interval in whichever direction
    the covariance happens to run.
    """
    vector = np.zeros(len(fit.names))
    for name, weight in weights.items():
        vector[fit.index(name)] = weight
    value = float(vector @ fit.beta)
    error = float(np.sqrt(max(float(vector @ fit.covariance @ vector), 0.0)))
    degrees = max(fit.groups - 1, 1)
    if error == 0.0:
        return {"value": value, "error": 0.0, "lower": value,
                "upper": value, "t": float("nan"), "p": float("nan")}
    half = stats.t.ppf(0.975, degrees) * error
    t_value = value / error
    return {"value": value, "error": error, "lower": value - half,
            "upper": value + half, "t": t_value,
            "p": float(2 * stats.t.sf(abs(t_value), degrees))}
