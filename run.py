"""What one grid slot is worth, measured from grid penalties.

Run with no arguments; the seasons are cached, so a second run costs
nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import charts                                              # noqa: E402
import confound                                            # noqa: E402
import data                                                # noqa: E402
import panel                                               # noqa: E402
import placebo                                             # noqa: E402
import report                                              # noqa: E402
import slot                                                # noqa: E402

SEASONS = (2018, 2019, 2020, 2021, 2022, 2023)
OUT = ROOT / "out"

_log: list[str] = []


def say(line: str = "") -> None:
    print(line)
    _log.append(line)


def show(name: str, found: dict, unit: str = "places a slot") -> None:
    say(f"  {name:38s} {found['slope']:+6.3f} +- {found['error']:.3f}  "
        f"95% [{found['lower']:+6.3f}, {found['upper']:+6.3f}]  "
        f"n={found['n']:5d}  {unit}")


def main() -> None:
    entries, sprints = data.load(SEASONS)
    rows, pit_lane, census = panel.build(entries, sprints)
    labels = panel.names(rows)
    say(f"{len(entries):,} race entries over {len(SEASONS)} seasons")
    say()
    say("building the panel")
    for key, value in census.items():
        say(f"  {key:44s} {value:6,d}")
    say("  a sprint weekend sets the grid by the sprint result, so the gap "
        "between qualifying and the start is a race result there and not a "
        "penalty. Keeping those rows would put a race on the right-hand side")

    moved = [one for one in rows if one.shift != 0]
    say()
    say(f"the variation everything rests on: {len(moved):,} of {len(rows):,} "
        f"entries started somewhere other than where they qualified")
    for row in confound.by_movement(rows):
        say(f"  {row['moved']:9s} {row['entries']:5d} entries, median shift "
            f"{row['median shift']:+.0f} slots, {row['share']:.1%} retired")

    # ---- what a slot is worth -----------------------------------------
    say()
    say("what one slot is worth, with driver-season effects throughout and "
        "errors clustered on the race")
    found = slot.summary(rows)
    for name in ("apparent, finish on grid",
                 "qualifying slot, pace and position",
                 "grid slot, position alone",
                 "promoted by somebody else",
                 "demoted by their own penalty",
                 "within six slots either way"):
        show(name, found[name])
    premium = found["pace premium, qualifying minus grid"]
    say(f"  {'pace premium (qualifying - grid)':38s} "
        f"{premium['value']:+6.3f} +- {premium['error']:.3f}  "
        f"95% [{premium['lower']:+6.3f}, {premium['upper']:+6.3f}]  "
        f"p={premium['p']:.3f}")
    apparent = found["apparent, finish on grid"]["slope"]
    honest = found["grid slot, position alone"]["slope"]
    say(f"  a grid slot looks worth {apparent:.3f} places and is worth "
        f"{honest:.3f}, so {1 - honest / apparent:.0%} of the apparent "
        f"relationship between starting and finishing is the car reasserting "
        f"itself, even after a driver's own season is held fixed")

    split = slot.directions(rows)
    say()
    say("backwards and forwards in the same fit, so the difference has an "
        "interval")
    show("moved backwards, per slot", split["backward"])
    show("moved forwards, per slot", split["forward"])
    total = split["sum"]
    say(f"  if the effect were symmetric these would sum to zero: "
        f"{total['value']:+.3f} +- {total['error']:.3f}, p={total['p']:.3f}")
    say("  so losing a slot and gaining one cost and pay about the same, and "
        "the thin promoted-only estimate is not evidence against the demoted "
        "one. That is the question the two separate fits could not answer, "
        "because they share no covariance")

    # ---- is the experiment an experiment? ------------------------------
    say()
    say("placebo 1: give each race's penalties to the wrong cars")
    shuffle = placebo.shuffled(rows)
    say(f"  real slope {shuffle['observed']:+.3f}; {shuffle['draws']} "
        f"shuffles centre on {shuffle['shuffled mean']:+.3f} with sd "
        f"{shuffle['shuffled sd']:.3f}, 95% of them inside "
        f"[{shuffle['lower']:+.3f}, {shuffle['upper']:+.3f}]")
    say(f"  {shuffle['at least as large']} of {shuffle['draws']} shuffles "
        f"reached the real slope, so p = {shuffle['p']:.4f}")

    say()
    say("placebo 2: the same fit, predicting a race that already happened")
    past = placebo.past(rows)
    say(f"  this race's penalty on the driver's previous finish: "
        f"{past['slope']:+.3f} +- {past['error']:.3f}, "
        f"95% [{past['lower']:+.3f}, {past['upper']:+.3f}], p={past['p']:.3f}")
    say("  a penalty handed out on Saturday cannot change what the same "
        "driver did a fortnight earlier, so anything but zero here would "
        "mean penalties go to drivers whose results were already moving")

    # ---- the two things that could still be wrong ----------------------
    say()
    say("the exclusion that could bend the answer: a retirement has no "
        "finishing position")
    retired = confound.retirement(rows)
    say(f"  {retired['retired']:,} of {retired['entries']:,} entries did not "
        f"reach the flag")
    for name in ("qualified", "shift"):
        one = retired[name]
        say(f"  {name:10s} log odds of finishing {one['log odds']:+.4f} "
            f"+- {one['error']:.4f}  odds ratio {one['odds ratio']:.3f}  "
            f"p={one['p']:.3f}")
    fit = retired["fit"]
    for where, shift in ((2, 0), (18, 0), (8, 0), (8, 5)):
        say(f"  a car that qualified {where:2d} and was moved {shift:+d}: "
            f"{confound.chance(fit, qualified=where, shift=shift):.1%} "
            f"chance of being classified")
    say(f"  driver-season effects: {retired['driver effects']}")
    for row in confound.by_band(rows):
        say(f"  started {row['grid']:5s} ({row['band']:22s}) "
            f"{row['retired']:4d} of {row['entries']:5d} retired, "
            f"{row['share']:.1%}")

    # ---- the held-out set ----------------------------------------------
    say()
    say("the pit-lane starts, which were meant to be the held-out set")
    pooled = found["grid slot, position alone"]["slope"]
    far = slot.extrapolate(pit_lane, rows, slot.controlled(rows))
    retired_share = 1 - (census["of those, classified at the flag"]
                         / census["in the panel"])
    say(f"  {far['entries']} starts, {far['retired']} of them retired "
        f"({far['retirement rate']:.0%}, against {retired_share:.0%} in the "
        f"panel)")
    say(f"  median distance from where they qualified: "
        f"{far['median distance']:.0f} slots, and only "
        f"{far['really moved']} of them were moved {far['cutoff']} slots or "
        f"more")
    say("  almost every car sent to the pit lane had already qualified at "
        "the back, because the failure that earns the penalty is usually the "
        "failure that ruined qualifying. A pit-lane start is severe in every "
        "respect except the one measured here")
    if far["implied slope"] is None:
        say(f"  no implied slope: {far['refused']}")
    else:
        say(f"  over the {far['really moved']} that were moved the implied "
            f"slope is {far['implied slope']:+.3f} against the panel's "
            f"{pooled:+.3f}, which hints that a long move costs more a slot "
            f"than a short one. It is {far['really moved']} cars whose "
            f"scatter is many times the effect, and it settles nothing")

    # ---- circuit by circuit ---------------------------------------------
    say()
    by_track = slot.by_circuit(rows)
    joint = by_track["joint"]
    say(f"the same slope circuit by circuit, on the "
        f"{len(by_track['circuits'])} circuits with enough penalties to "
        f"carry one")
    say(f"  pooled over those circuits {by_track['pooled']:+.3f}; baseline "
        f"{labels[by_track['baseline']]} {by_track['baseline slope']:+.3f}")
    say(f"  {'circuit':24s} {'entries':>7s} {'moved':>5s} {'slope':>7s} "
        f"{'error':>6s} {'shrunk':>7s}")
    for row in by_track["circuits"]:
        say(f"  {labels[row['circuit']][:24]:24s} {row['entries']:7d} "
            f"{row['moved']:5d} "
            f"{row['slope']:+7.3f} {row['error']:6.3f} {row['shrunk']:+7.3f}")
    factor = by_track["circuits"][0]["factor"]
    say(f"  shrinkage keeps {factor:.0%} of the spread between circuits; the "
        f"rest of it is sampling noise")
    say(f"  jointly, the {joint['terms']} circuit deviations give "
        f"F={joint['F']:.2f}, p={joint['p']:.3f}, so the circuits do differ")
    say("  the order they differ in is not readable, though, and it does not "
        "line up with where overtaking is hard: Austria and Montreal sit "
        "high, Spa and Monza in the middle, Sochi at the bottom. Three "
        "quarters of the spread is noise and the remaining quarter is not "
        "a ranking")
    if by_track["left out"]:
        say(f"  {len(by_track['left out'])} circuits carried too little "
            f"shift to fit: "
            f"{', '.join(labels[one] for one in by_track['left out'])}")

    say()
    where = slot.where_penalties_land(rows)
    say("where the penalties happen, which is a choice and not an accident")
    say(f"  {'circuit':20s} {'moved':>6s} {'entries':>8s} {'share':>7s}")
    for row in where["circuits"][:8]:
        say(f"  {labels[row['circuit']][:20]:20s} {row['moved']:6d} "
            f"{row['entries']:8d} "
            f"{row['share']:7.0%}")
    say("  ...")
    for row in where["circuits"][-4:]:
        say(f"  {labels[row['circuit']][:20]:20s} {row['moved']:6d} "
            f"{row['entries']:8d} "
            f"{row['share']:7.0%}")
    top = ", ".join(labels[one["circuit"]] for one in where["circuits"][:5])
    say(f"  overall {where['share overall']:.0%}. A team changing a power "
        f"unit chooses which weekend to take the penalty, and it chooses a "
        f"circuit where starting further back is cheap. So the variation "
        f"this whole project is identified from piles up at {top}, while "
        f"Monaco - where a slot should be worth most of all - carries so "
        f"little that it cannot be fitted")
    say(f"  the weighting is not where this bites. Pooled over the eligible "
        f"circuits {by_track['pooled']:+.3f}, unweighted mean of their own "
        f"slopes {by_track['unweighted']:+.3f}: near enough identical, so "
        f"the busy circuits are not dragging the pooled number about")
    say(f"  what bites is the {len(by_track['left out'])} circuits that "
        f"cannot be fitted at all. They are missing, not down-weighted, and "
        f"nothing here can say what a slot was worth at them")

    # ---- what it cost ----------------------------------------------------
    say()
    priced = confound.cost(rows, pooled)
    say(f"what the penalties cost the cars that took them, at "
        f"{pooled:+.3f} places a slot")
    say(f"  {priced['entries']} demoted entries reached the flag inside the "
        f"{priced['support']}-slot support, {priced['slots']:,} slots between "
        f"them; {priced['refused, beyond the support']} were moved further "
        f"and are refused rather than extrapolated")
    say(f"  {priced['points']:.1f} championship points, "
        f"{priced['points each']:.2f} an entry, "
        f"{priced['entries that lost points']} of them losing anything at all")
    worst = priced["worst"]
    say(f"  worst single one: {worst['driver']} at {worst['circuit']} "
        f"{worst['race']}, moved {worst['shift']} slots, finished "
        f"{worst['finish']} where the slope says {worst['would have been']}, "
        f"{worst['points']:.0f} points")
    say("  this is what the penalised cars gave up, not what the grid "
        "rearranged: un-penalising one car moves every car it passes, and "
        "those counterfactuals are not computed")

    # ---- output -----------------------------------------------------------
    figures = charts.draw(
        OUT, rows=rows, found=found, shuffle=shuffle, retired=retired,
        bands=confound.by_band(rows), by_track=by_track, far=far,
        labels=labels)
    path = report.build(
        census=census, found=found, split=split, shuffle=shuffle, past=past,
        retired=retired, bands=confound.by_band(rows), by_track=by_track,
        far=far, where=where, labels=labels, priced=priced,
        seasons=SEASONS, figures=figures,
        out_path=OUT / "report.pdf")

    say()
    say(f"report  {path}")
    for name, figure in figures.items():
        say(f"figure  {figure}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_run.txt").write_text("\n".join(_log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
