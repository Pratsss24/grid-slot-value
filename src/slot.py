"""What one grid slot is worth, separated from what the pace is worth.

The raw relationship between where a car starts and where it finishes is
nearly an identity, and it is nearly all the wrong thing. Quick cars start
at the front and finish at the front. Regressing finishing position on
grid position measures the car and then calls the answer track position.

**The experiment.** A grid penalty moves a car without changing the car,
the driver, the circuit or the weather. Keep both numbers - where the car
earned its slot in qualifying, and where it actually started - and the
difference between them is a shift the car's own pace did not cause:

    finish  =  a  +  b * qualified  +  c * shift  +  driver-season effects

`b` collects everything that being quick on Saturday implies about being
quick on Sunday. `c` is what a slot is worth on its own, because within a
driver-season and at a given qualifying position the only thing moving
`shift` is a steward's decision or somebody else's failed gearbox.

Since `grid = qualified + shift`, the same fit rewrites as

    finish  =  a  +  c * grid  +  (b - c) * qualified  +  effects

so `b - c` is the pace premium: the part of a qualifying slot that is not
track position at all. If a grid slot were the whole story, `b` and `c`
would be equal.

**Which way the bias runs.** A penalty is not a coin toss. Gearbox and
power-unit penalties are handed out because a car is breaking, and a
breaking car is also slower on Sunday and likelier to retire, so a slope
fitted on demoted cars alone is an upper bound on the damage. The repair
is in the data: a penalty to one car *promotes* every car behind it, and
those cars were moved by somebody else's problem. `promoted` fits the
same slope on them alone, and that is the estimate to trust.

**What the slope is not.** It is a local, linear average over the shifts
that actually happened, nearly all of them between one and ten slots. It
does not extrapolate to being sent to the back of the grid, and pit-lane
starts are not in the panel at all.
"""

from __future__ import annotations

import numpy as np

import linear
import panel

MIN_ROWS = 60             # below this a slope is not worth reporting
MIN_MOVED = 15            # and nor is one with too little shift to use


def _classified(rows) -> list:
    return [one for one in rows if one.classified]


def _columns(rows) -> dict[str, np.ndarray]:
    return {"qualified": np.array([one.qualified for one in rows], float),
            "shift": np.array([one.shift for one in rows], float)}


def _slope(fit: linear.Fit, name: str) -> dict:
    lower, upper = fit.interval(name)
    return {"slope": fit[name], "error": fit.error(name), "lower": lower,
            "upper": upper, "p": fit.p_value(name), "n": fit.n,
            "races": fit.groups}


def naive(rows) -> linear.Fit:
    """Finishing position on grid position alone: the answer to beat."""
    kept = _classified(rows)
    y = np.array([one.finish for one in kept], float)
    columns = {"grid": np.array([one.grid for one in kept], float)}
    matrix, names, cluster = panel.design(kept, columns)
    return linear.ols(y, matrix, names, cluster, label="finish on grid")


def controlled(rows, *, label: str = "") -> linear.Fit:
    """The experiment: both numbers in, so `shift` carries the slot effect."""
    kept = _classified(rows)
    if len(kept) < MIN_ROWS:
        raise ValueError(f"{len(kept)} classified rows is too few to fit")
    moved = sum(1 for one in kept if one.shift != 0)
    if moved < MIN_MOVED:
        raise ValueError(
            f"only {moved} of {len(kept)} rows were moved at all, so a slot "
            f"effect is not identified here")
    y = np.array([one.finish for one in kept], float)
    matrix, names, cluster = panel.design(kept, _columns(kept))
    return linear.ols(y, matrix, names, cluster,
                      label=label or "finish on qualifying and shift")


def promoted(rows) -> linear.Fit:
    """The clean half: cars moved forward by somebody else's penalty.

    A car promoted from ninth to eighth because the car ahead of it took a
    gearbox has no gearbox problem of its own. Nothing about its own
    reliability, pace or driving moved it. Cars whose shift is zero stay
    in, since they are the baseline the moved ones are measured against.
    """
    return controlled([one for one in rows if one.shift <= 0],
                      label="promoted or unmoved only")


def demoted(rows) -> linear.Fit:
    """The contaminated half, fitted so the contamination can be seen."""
    return controlled([one for one in rows if one.shift >= 0],
                      label="demoted or unmoved only")


def directions(rows) -> dict:
    """Backwards and forwards slopes in one fit, so they can be compared.

    `promoted` and `demoted` are separate fits on separate rows, which
    makes the difference between them impossible to test: they have no
    joint covariance. Here both appear as columns of the same design -
    `backward` is the slots lost and `forward` the slots gained, each zero
    for the other kind - so the difference is a contrast with an interval.

    It also keeps the two from being confused with magnitude. Nearly every
    promotion is a single slot while demotions run to ten and more, so a
    gap between the two slopes could be contamination, or could be that
    the effect is not linear in how far the car was moved. `matched`
    exists to take the magnitudes apart from the directions.
    """
    kept = _classified(rows)
    shift = np.array([one.shift for one in kept], float)
    columns = {"qualified": np.array([one.qualified for one in kept], float),
               "backward": np.maximum(shift, 0.0),
               "forward": np.maximum(-shift, 0.0)}
    y = np.array([one.finish for one in kept], float)
    matrix, names, cluster = panel.design(kept, columns)
    fit = linear.ols(y, matrix, names, cluster, label="by direction")
    return {"fit": fit, "backward": _slope(fit, "backward"),
            "forward": _slope(fit, "forward"),
            "sum": linear.combination(fit, {"backward": 1.0, "forward": 1.0})}


def matched(rows, *, reach: int = 6) -> linear.Fit:
    """The pooled slope over only the range promotions actually cover.

    Promotions never exceed a handful of slots. Comparing a demoted slope
    fitted partly on an eighteen-slot penalty against a promoted slope
    fitted on single slots compares two different questions. This drops
    every row moved further than `reach` in either direction so that both
    directions are asked about the same distances.
    """
    return controlled([one for one in rows if abs(one.shift) <= reach],
                      label=f"within {reach} slots either way")


FAR = 5               # a pit-lane start this far back is a real move
MIN_SLOTS = 40        # fewer slots than this and an implied slope is noise


def extrapolate(pit_lane, rows, fit: linear.Fit) -> dict:
    """The pit-lane starts, which no fit here has seen - and a surprise.

    They are excluded from every slope because the pit lane is not a grid
    slot and the distance from ninth to it is not a number of places. The
    intention was to use them as a held-out set: a car sent to the pit lane
    has been moved further than any penalty in the panel, so comparing what
    it actually lost against the fitted slope would test whether a slope
    estimated on shifts of one to ten slots says anything about being sent
    to the back.

    **It mostly cannot be done, and finding that out is the result.** Of
    the pit-lane starts here, nearly all belong to cars that had already
    qualified at the very back, because the failure that earned the
    penalty is usually the same failure that ruined qualifying. Their
    median distance from where they qualified is a couple of slots, and
    for some of it is negative: when several cars start from the pit lane
    the grid is shorter than the qualifying order, so a car that qualified
    last was going to start last either way. A pit-lane start is a severe
    punishment in every respect except the one measured here.

    What can still be done is reported for the few genuinely moved: the
    counterfactual is this car's own fitted driver-season effect plus the
    qualifying slope, which is where the fit says it would have finished
    had it started where it earned. An implied slope is only returned when
    the moved cars carry enough slots between them to support one.
    """
    starters: dict[tuple[int, int], int] = {}
    for one in rows:
        starters[one.race_id] = max(starters.get(one.race_id, 0), one.grid)

    pace = fit["qualified"]
    out_rows = []
    missing = 0
    for one in pit_lane:
        if one.qualified is None or one.race_id not in starters:
            continue
        name = f"driver_season:{one.driver}:{one.season}"
        if one.finish is None or name not in fit.names:
            missing += 1
            continue
        expected = fit[name] + pace * one.qualified
        out_rows.append({
            "race": f"{one.season} r{one.round}", "circuit": one.circuit,
            "driver": one.driver, "qualified": one.qualified,
            "distance": starters[one.race_id] + 1 - one.qualified,
            "finish": one.finish, "expected": expected,
            "lost": one.finish - expected})

    seen = [one for one in pit_lane if one.qualified is not None]
    retired = sum(1 for one in seen if one.finish is None)
    far = [one for one in out_rows if one["distance"] >= FAR]
    found = {"entries": len(seen), "classified": len(out_rows),
             "retired": retired,
             "retirement rate": retired / len(seen) if seen else float("nan"),
             "unmatched": missing - retired,
             "median distance": float(np.median(
                 [one["distance"] for one in out_rows])) if out_rows else 0.0,
             "really moved": len(far), "cutoff": FAR, "rows": out_rows}
    slots = sum(one["distance"] for one in far)
    if slots < MIN_SLOTS:
        found["implied slope"] = None
        found["refused"] = (
            f"the {len(far)} starts moved {FAR} slots or more carry "
            f"{slots} slots between them, which is too few to divide by")
        return found
    found["implied slope"] = float(
        sum(one["lost"] for one in far) / slots)
    found["median lost, moved starts"] = float(
        np.median([one["lost"] for one in far]))
    return found


def where_penalties_land(rows) -> dict:
    """Which circuits the penalties happen at, which is not an accident.

    A team that must change a power unit chooses *when*, and it chooses a
    circuit where starting further back is cheap. So the circuits carrying
    the variation this project is identified from are, by construction,
    disproportionately the circuits where a grid slot is worth least -
    Spa, Monza, Austin, Sochi - while Monaco, where a slot is worth most,
    carries almost none and drops out of the per-circuit fit entirely.

    That makes the pooled slope an answer to "what was a slot worth where
    penalties were actually taken", which is the right question for
    pricing a penalty and the wrong one for pricing a grid slot. The
    unweighted mean over the circuits that do carry a slope is reported
    beside it, not because it is unbiased - eligibility is selected too -
    but because the gap between the two is the size of the problem.
    """
    counts: dict[str, list[int]] = {}
    for one in rows:
        here = counts.setdefault(one.circuit, [0, 0])
        here[0] += 1
        here[1] += 1 if one.shift != 0 else 0
    table = [{"circuit": name, "entries": total, "moved": moved,
              "share": moved / total}
             for name, (total, moved) in counts.items()]
    table.sort(key=lambda one: -one["share"])
    return {"circuits": table,
            "share overall": sum(one["moved"] for one in table)
            / sum(one["entries"] for one in table)}


def premium(fit: linear.Fit) -> dict:
    """b - c: the part of a qualifying slot that is pace, not position."""
    return linear.combination(fit, {"qualified": 1.0, "shift": -1.0})


def summary(rows) -> dict:
    """Every slope the argument needs, in one place."""
    whole = controlled(rows)
    out = {"apparent, finish on grid": _slope(naive(rows), "grid"),
           "qualifying slot, pace and position": _slope(whole, "qualified"),
           "grid slot, position alone": _slope(whole, "shift"),
           "promoted by somebody else": _slope(promoted(rows), "shift"),
           "demoted by their own penalty": _slope(demoted(rows), "shift"),
           "within six slots either way": _slope(matched(rows), "shift")}
    out["pace premium, qualifying minus grid"] = premium(whole)
    return out


# ---- the same slope, circuit by circuit --------------------------------

def eligible(rows) -> list[str]:
    """Circuits carrying enough shift of their own to support a slope."""
    kept = _classified(rows)
    out = []
    for circuit in sorted({one.circuit for one in kept}):
        here = [one for one in kept if one.circuit == circuit]
        moved = sum(1 for one in here if one.shift != 0)
        if len(here) >= MIN_ROWS and moved >= MIN_MOVED:
            out.append(circuit)
    return out


def shrink(rows: list[dict], pooled: float) -> list[dict]:
    """James-Stein shrinkage of each circuit's slope towards the pooled one.

    Thirty slopes each fitted on a handful of penalised entries will have
    a spread that is mostly noise, and the extremes of that spread are
    exactly where a reader's eye goes. The factor is the share of the
    observed spread that the sampling errors cannot account for, so if the
    circuits do not really differ then every slope collapses onto the
    pooled value and the chart says so instead of inventing an order.
    """
    slopes = np.array([one["slope"] for one in rows], float)
    errors = np.array([one["error"] for one in rows], float)
    spread = float(slopes.var(ddof=1)) if slopes.size > 1 else 0.0
    noise = float((errors ** 2).mean())
    real = max(spread - noise, 0.0)
    factor = real / spread if spread > 0 else 0.0
    out = [dict(one, shrunk=pooled + factor * (one["slope"] - pooled),
                factor=factor, signal=real, noise=noise) for one in rows]
    return sorted(out, key=lambda one: -one["shrunk"])


def by_circuit(rows) -> dict:
    """One shift slope per circuit, fitted as deviations from a pooled slope.

    Parameterised as one `shift` slope plus a `shift x circuit` deviation
    for every eligible circuit bar the busiest, which is the baseline.
    Deviations are what let `linear.joint_test` ask the question a column
    of overlapping intervals cannot answer: whether the circuit matters
    *at all*, jointly, rather than whether any one circuit's slope is
    separable from the baseline.

    **The fit is restricted to the eligible circuits.** An earlier version
    kept every row, which left the bare `shift` term meaning "the baseline
    circuit and also the twenty-one circuits with too little penalty
    variation to earn a column" - a quantity with no interpretation, which
    was then reported as the pooled slope and shrunk towards. The pooled
    slope here is the plain one from `controlled` on the same restricted
    rows, so the per-circuit slopes and the thing they are compared with
    are estimated on the same data.
    """
    circuits = eligible(rows)
    if len(circuits) < 3:
        raise ValueError("fewer than three circuits carry enough shift")
    everywhere = sorted({one.circuit for one in _classified(rows)})
    kept = [one for one in _classified(rows) if one.circuit in circuits]

    counts = {one: sum(1 for row in kept if row.circuit == one)
              for one in circuits}
    baseline = max(counts, key=lambda one: counts[one])
    others = [one for one in circuits if one != baseline]

    shift = np.array([one.shift for one in kept], float)
    columns = {"qualified": np.array([one.qualified for one in kept], float),
               "shift": shift}
    for circuit in others:
        here = np.array([one.circuit == circuit for one in kept], float)
        columns[f"shift x {circuit}"] = shift * here

    y = np.array([one.finish for one in kept], float)
    matrix, names, cluster = panel.design(kept, columns)
    fit = linear.ols(y, matrix, names, cluster, label="shift by circuit")
    pooled = controlled(kept, label="pooled over the eligible circuits")

    raw = []
    for circuit in circuits:
        if circuit == baseline:
            slope, error = fit["shift"], fit.error("shift")
        else:
            found = linear.combination(
                fit, {"shift": 1.0, f"shift x {circuit}": 1.0})
            slope, error = found["value"], found["error"]
        raw.append({"circuit": circuit, "slope": slope, "error": error,
                    "entries": counts[circuit], "baseline": circuit == baseline,
                    "moved": sum(1 for one in kept if one.circuit == circuit
                                 and one.shift != 0)})

    return {"fit": fit, "pooled": pooled["shift"], "pooled fit": pooled,
            "baseline": baseline, "baseline slope": fit["shift"],
            "unweighted": float(np.mean([one["slope"] for one in raw])),
            "circuits": shrink(raw, pooled["shift"]),
            "left out": [one for one in everywhere if one not in circuits],
            "joint": linear.joint_test(
                fit, tuple(f"shift x {one}" for one in others))}
