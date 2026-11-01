"""The two ways the experiment could be fooling itself, measured.

A grid penalty is not a coin toss, and a retirement has no finishing
position. Both facts attack the main estimate, and both leave a signature
that can be looked for.

**Penalties are handed to cars that are breaking.** A gearbox or
power-unit penalty exists *because* a component failed, and the car that
needed the new component is also the car likelier to lose another one on
Sunday. If that is happening, a demoted car finishes worse for two
reasons - it started further back, and it was already sick - and the slope
fitted on demoted cars blames both on the slot. `retirement` fits whether
a demoted car is likelier to fail to reach the flag; if it is, the demoted
slope is an upper bound and the promoted slope is the one to read.

**A retirement is missing from the outcome, not from the world.** The
main fit keeps only cars classified at the flag, so if starting further
back makes a car likelier to be collected at the first corner, the worst
consequences of a bad slot are silently dropped and the slope understates
the damage. The same logit answers this, on the grid side.

**Why the logit has season effects and not driver-season effects.** Many
driver-seasons contain no retirement at all. Such a column predicts
"classified" perfectly, the likelihood has no finite maximum, and the
coefficients run away while the fit reports a superb pseudo-R squared.
`separates` checks this rather than asserting it: it attempts the fit with
driver-season effects and reports whether it was refused.
"""

from __future__ import annotations

import numpy as np

import linear
import panel

BANDS = ((1, 5, "front five"), (6, 10, "sixth to tenth"),
         (11, 15, "eleventh to fifteenth"), (16, 30, "sixteenth and back"))


def _design(rows, by: str):
    y = np.array([1.0 if one.classified else 0.0 for one in rows])
    columns = {"qualified": np.array([one.qualified for one in rows], float),
               "shift": np.array([one.shift for one in rows], float)}
    matrix, names, cluster = panel.design(rows, columns, by=by)
    return y, matrix, names, cluster


def separates(rows) -> str:
    """Attempt the logit with driver-season effects and report the refusal.

    The claim in this module's docstring is that it cannot be fitted. This
    runs it to find out, so the claim is checked and not just believed.
    """
    try:
        y, matrix, names, cluster = _design(rows, "driver_season")
        linear.logit(y, matrix, names, cluster)
    except ValueError as error:
        return str(error)
    return "fitted, so this module's reason for using season effects is wrong"


def retirement(rows) -> dict:
    """Does the grid, or a penalty, change the chance of seeing the flag?"""
    y, matrix, names, cluster = _design(rows, "season")
    fit = linear.logit(y, matrix, names, cluster, label="reached the flag")
    out = {"fit": fit, "driver effects": separates(rows),
           "retired": int((1 - y).sum()), "entries": int(y.size)}
    for name in ("qualified", "shift"):
        lower, upper = fit.interval(name)
        out[name] = {"log odds": fit[name], "error": fit.error(name),
                     "lower": lower, "upper": upper, "p": fit.p_value(name),
                     "odds ratio": float(np.exp(fit[name]))}
    return out


def chance(fit: linear.Fit, *, qualified: int, shift: int) -> float:
    """The fitted chance of reaching the flag for one hypothetical entry.

    The season effects are averaged rather than one of them picked, since
    the question is about a grid slot and not about 2019.
    """
    row = np.zeros(len(fit.names))
    row[fit.index("qualified")] = qualified
    row[fit.index("shift")] = shift
    seasons = [name for name in fit.names if name.startswith("season:")]
    for name in seasons:
        row[fit.index(name)] = 1.0 / len(seasons)
    return linear.probability(fit, row)


def by_band(rows) -> list[dict]:
    """Raw retirement rate by where on the grid the car started.

    Descriptive, and deliberately so: it is the thing the logit is meant
    to be a careful version of, and the two should agree in sign. They are
    reported together so a reader can see whether they do.
    """
    out = []
    for low, high, name in BANDS:
        here = [one for one in rows if low <= one.grid <= high]
        if not here:
            continue
        retired = sum(1 for one in here if not one.classified)
        out.append({"band": name, "grid": f"{low}-{high}", "entries": len(here),
                    "retired": retired, "share": retired / len(here)})
    return out


def by_movement(rows) -> list[dict]:
    """Raw retirement rate by whether the car was moved, and which way."""
    out = []
    for name in ("promoted", "unmoved", "demoted"):
        here = [one for one in rows if one.moved == name]
        if not here:
            continue
        retired = sum(1 for one in here if not one.classified)
        out.append({"moved": name, "entries": len(here), "retired": retired,
                    "share": retired / len(here),
                    "median shift": float(np.median(
                        [one.shift for one in here]))})
    return out


def cost(rows, slope: float, *, support: int = 10) -> dict:
    """What the penalties cost the cars that took them, in points.

    For every demoted car that was classified, the counterfactual finish
    is its actual finish minus `slope` times the slots it was moved,
    rounded and held inside the classified field, and the cost is the
    difference in championship points.

    **Only inside the support.** The slope is a local average over moves
    of one to ten slots, so applying it to an eighteen-slot penalty is the
    extrapolation this project warns about everywhere else: multiplied out,
    it claims a car would have won a race it finished fourth in. Entries
    moved further than `support` slots are refused and counted.

    **This is not a redistribution.** Un-penalising one car would move
    every car it passes, and their counterfactuals are not computed here,
    so the gains on the other side of these losses are missing. The number
    is what the penalised cars gave up, not what the grid as a whole
    rearranged, and the two are not the same quantity.
    """
    demoted = [one for one in rows if one.classified and one.shift > 0]
    kept = [one for one in demoted if one.shift <= support]
    refused = len(demoted) - len(kept)
    if not kept:
        return {"entries": 0, "points": 0.0, "refused, beyond the support":
                refused, "support": support}
    last = max(one.finish for one in rows if one.classified)
    total = 0.0
    scored = 0
    worst = None
    for one in kept:
        counterfactual = int(round(one.finish - slope * one.shift))
        counterfactual = max(1, min(last, counterfactual))
        lost = panel.points_for(counterfactual) - one.points
        total += lost
        if lost > 0:
            scored += 1
        if worst is None or lost > worst["points"]:
            worst = {"race": f"{one.season} r{one.round}",
                     "circuit": one.circuit, "driver": one.driver,
                     "shift": one.shift, "finish": one.finish,
                     "would have been": counterfactual, "points": lost}
    return {"entries": len(kept), "points": total,
            "entries that lost points": scored,
            "points each": total / len(kept), "worst": worst,
            "slots": sum(one.shift for one in kept),
            "refused, beyond the support": refused, "support": support}
