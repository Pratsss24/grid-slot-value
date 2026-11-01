"""Two ways to catch this method inventing an effect that is not there.

A slope with a small p value is not evidence that the design works. Both
of these would find a result on data where there is nothing to find, if
the method were broken, and both are run before the main number is
believed.

**The shuffle.** Within each race, give the penalties to the wrong cars.
Every race keeps exactly the shifts it really had, so the distribution of
penalty sizes, how many cars were moved and which weekends they happened
on are all untouched - only the question of *who* got them is destroyed.
If the design is picking up a real consequence of being moved, the real
slope sits outside the shuffled distribution. If it is picking up an
arithmetic relationship between the columns, or a selection effect that
survives any assignment, the shuffled slopes land on the real one.

**The past.** A penalty handed out on Saturday cannot change what the
same driver did at the previous race. So fit the main specification with
the driver's *previous* finishing position as the outcome. The slope on
the shift must be zero. If it is not, penalties are going to drivers whose
results were already moving, and the exogeneity the whole project rests on
is not there.

**Why the shuffle is fitted with demeaning rather than dummy columns.**
Several hundred refits with a hundred fixed-effect columns each is slow
for no gain: by Frisch-Waugh-Lovell, demeaning the outcome and the
regressors within each driver-season gives numerically the same slope.
Only the point estimate is wanted here - the spread of the shuffled
distribution *is* the standard error for this test - so the cluster-robust
covariance that the dummy version also returns would be thrown away.
There is a test that the two agree.
"""

from __future__ import annotations

import numpy as np

import linear
import panel

DRAWS = 400
SEED = 7


def within(values: np.ndarray, groups) -> np.ndarray:
    """Subtract each group's mean, column by column."""
    out = np.array(values, dtype=float)
    labels = np.asarray(groups)
    for one in np.unique(labels):
        mask = labels == one
        out[mask] -= out[mask].mean(axis=0)
    return out


def demeaned_slope(finish: np.ndarray, qualified: np.ndarray,
                   shift: np.ndarray, groups) -> float:
    """The shift slope, by Frisch-Waugh-Lovell: fast, and the same number."""
    y = within(finish, groups)
    x = within(np.column_stack([qualified, shift]), groups)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return float(beta[1])


def shuffled(rows, *, draws: int = DRAWS, seed: int = SEED) -> dict:
    """Give each race's penalties to the wrong cars, and refit."""
    kept = [one for one in rows if one.classified]
    finish = np.array([one.finish for one in kept], float)
    qualified = np.array([one.qualified for one in kept], float)
    shift = np.array([one.shift for one in kept], float)
    groups = np.array([one.driver_season for one in kept])
    races = np.array([f"{one.season}:{one.round}" for one in kept])

    observed = demeaned_slope(finish, qualified, shift, groups)
    blocks = [np.flatnonzero(races == one) for one in np.unique(races)]
    generator = np.random.default_rng(seed)

    fake = np.empty(draws)
    for draw in range(draws):
        swapped = shift.copy()
        for block in blocks:
            swapped[block] = generator.permutation(shift[block])
        fake[draw] = demeaned_slope(finish, qualified, swapped, groups)

    beyond = int(np.sum(np.abs(fake) >= abs(observed)))
    return {"observed": observed, "draws": draws,
            "shuffled mean": float(fake.mean()),
            "shuffled sd": float(fake.std(ddof=1)),
            "lower": float(np.quantile(fake, 0.025)),
            "upper": float(np.quantile(fake, 0.975)),
            "at least as large": beyond,
            "p": (beyond + 1) / (draws + 1),
            "slopes": fake}


def past(rows) -> dict:
    """The same specification, with a result that happened first.

    Every row whose driver has a previous race is used, whether or not the
    car was classified this time: the outcome is last time's finish, so
    this time's retirement is beside the point.
    """
    kept = [one for one in rows if one.previous is not None]
    if len(kept) < 100:
        raise ValueError(f"{len(kept)} rows with a previous race is too few")
    y = np.array([one.previous for one in kept], float)
    columns = {"qualified": np.array([one.qualified for one in kept], float),
               "shift": np.array([one.shift for one in kept], float)}
    matrix, names, cluster = panel.design(kept, columns)
    fit = linear.ols(y, matrix, names, cluster,
                    label="the previous race, on this race's penalty")
    lower, upper = fit.interval("shift")
    return {"fit": fit, "slope": fit["shift"], "error": fit.error("shift"),
            "lower": lower, "upper": upper, "p": fit.p_value("shift"),
            "n": fit.n, "races": fit.groups}
