"""The report, as a printable PDF built out of matplotlib pages.

`paper.py` owns the page furniture; everything here is this project's own
argument, in the order the argument runs.
"""

from __future__ import annotations

from pathlib import Path

from paper import Paper

LADDER = (("apparent, finish on grid", "finishing position on grid alone"),
          ("qualifying slot, pace and position", "a qualifying slot"),
          ("grid slot, position alone", "a grid slot, the experiment"),
          ("within six slots either way", "the same, short moves only"),
          ("demoted by their own penalty", "their own penalty only"),
          ("promoted by somebody else", "somebody else's penalty only"))


def _p(value: float) -> str:
    return "<0.0001" if value < 0.0001 else f"{value:.4f}"


def _ladder(found: dict) -> tuple[list[str], list[list[str]]]:
    rows = []
    for key, label in LADDER:
        row = found[key]
        rows.append([label, f"{row['n']:,}", f"{row['slope']:+.3f}",
                     f"[{row['lower']:+.3f}, {row['upper']:+.3f}]",
                     "yes" if row["lower"] > 0 else "no"])
    return (["what is being measured", "entries", "places a slot",
             "95% interval", "excludes zero"], rows)


def _circuits(by_track: dict, labels: dict
              ) -> tuple[list[str], list[list[str]]]:
    rows = [[labels.get(row["circuit"], row["circuit"])
             + (" (baseline)" if row["baseline"] else ""),
             str(row["entries"]), str(row["moved"]),
             f"{row['slope']:+.3f}", f"{row['error']:.3f}",
             f"{row['shrunk']:+.3f}"]
            for row in by_track["circuits"]]
    return ["circuit", "entries", "moved", "slope", "error", "shrunk"], rows


def _bands(bands: list[dict]) -> tuple[list[str], list[list[str]]]:
    rows = [[f"{row['grid']} ({row['band']})", f"{row['entries']:,}",
             str(row["retired"]), f"{row['share']:.1%}"] for row in bands]
    return ["grid slot", "entries", "retired", "share"], rows


def build(*, census, found, split, shuffle, past, retired, bands, by_track,
          far, where, labels, priced, seasons, figures,
          out_path: Path) -> Path:
    slot = found["grid slot, position alone"]
    apparent = found["apparent, finish on grid"]
    premium = found["pace premium, qualifying minus grid"]
    years = f"{min(seasons)}–{max(seasons)}"
    moved = census["of those, moved by a penalty"]
    symmetry = split["sum"]
    retired_share = 1 - (census["of those, classified at the flag"]
                         / census["in the panel"])
    out = Path(out_path)
    out = out.with_name("report.pdf") if out.suffix != ".pdf" else out
    out.parent.mkdir(parents=True, exist_ok=True)

    with Paper(out, "What a grid slot is worth",
               f"Formula 1, {years}. Measured from grid penalties — "
               f"the one thing in the sport that moves a car without "
               f"changing the car, the driver or the weekend.") as paper:

        paper.cover(
            headline=f"A grid slot is worth "
                     f"{slot['slope']:+.2f} places at the flag",
            small=f"95% interval [{slot['lower']:+.3f}, "
                  f"{slot['upper']:+.3f}]. Regressing on the grid alone "
                  f"says {apparent['slope']:+.3f}, and that is already "
                  f"inside a driver's own season — so a large part "
                  f"of what looks like track position is the car "
                  f"reasserting itself over the race distance.",
            tiles=[("a grid slot is worth", f"{slot['slope']:+.2f}"),
                   ("it looks worth", f"{apparent['slope']:+.2f}"),
                   ("entries moved by a penalty", f"{moved:,}"),
                   ("points it cost them", f"{priced['points']:.0f}")],
            blurb="Where a car starts predicts where it finishes almost "
                  "perfectly, and almost none of that is the starting "
                  "place: quick cars start at the front. Keep both "
                  "numbers — where the car earned its slot in "
                  "qualifying and where it actually started — and "
                  "the difference between them is a shift the car's own "
                  "pace did not cause.",
            figure_path=figures["ladder"])

        paper.section(
            "The experiment",
            note="Within a driver's own season and at a given qualifying "
                 "position, the only thing moving that shift is a steward "
                 "or somebody else's failed gearbox.",
            body=f"The pace premium — what a qualifying slot is "
                 f"worth beyond the track position it comes with — "
                 f"is {premium['value']:+.3f} places a slot, 95% "
                 f"[{premium['lower']:+.3f}, {premium['upper']:+.3f}], "
                 f"p = {premium['p']:.3f}.",
            table=_ladder(found))

        paper.section(
            "All of the evidence",
            note="And the honest limit of the design.",
            body=f"A promotion is nearly always a single slot, so the "
                 f"estimate fitted on promoted cars alone — the only "
                 f"cars moved for a reason that has nothing to do with "
                 f"them — has an interval wide enough to contain "
                 f"both zero and the pooled answer. It is not a "
                 f"refutation and it is not a confirmation.\n\n"
                 f"Fitting both directions in one design makes the "
                 f"comparison testable: backwards "
                 f"{split['backward']['slope']:+.3f}, forwards "
                 f"{split['forward']['slope']:+.3f}. If the effect were "
                 f"symmetric these would sum to zero; they sum to "
                 f"{symmetry['value']:+.3f} ± {symmetry['error']:.3f}, "
                 f"p = {symmetry['p']:.3f} — consistent with "
                 f"symmetry, so the thin promoted estimate is not "
                 f"evidence against the demoted one.",
            figure_path=figures["leverage"])

        paper.section(
            "Two ways to catch this inventing an effect",
            note="Within each race, give the penalties to the wrong cars. "
                 "Every race keeps exactly the penalties it really had; "
                 "only who received them is destroyed.",
            body=f"{shuffle['at least as large']} of {shuffle['draws']} "
                 f"reshuffles reached the real slope, p = "
                 f"{shuffle['p']:.4f}, and they centre on "
                 f"{shuffle['shuffled mean']:+.3f}.\n\n"
                 f"Then the same fit, predicting a race that already "
                 f"happened. A penalty handed out on Saturday cannot "
                 f"change what the same driver did a fortnight earlier, "
                 f"so the slope on the driver's previous finishing "
                 f"position has to be zero: it is {past['slope']:+.3f} "
                 f"± {past['error']:.3f}, p = {past['p']:.3f}. "
                 f"Anything else would mean penalties go to drivers whose "
                 f"results were already moving.",
            figure_path=figures["shuffle"])

        paper.section(
            "The exclusion that could bend it",
            note=f"A retirement has no finishing position, so "
                 f"{retired['retired']:,} of {retired['entries']:,} "
                 f"entries are not in the main fit.",
            warn=f"A grid slot does predict retiring (odds ratio "
                 f"{retired['qualified']['odds ratio']:.3f} a slot, p = "
                 f"{retired['qualified']['p']:.3f}), but a penalty does "
                 f"not (odds ratio "
                 f"{retired['shift']['odds ratio']:.3f}, p = "
                 f"{retired['shift']['p']:.3f}). The first is a selection "
                 f"effect on the outcome and makes the main slope an "
                 f"understatement; the second is the exogeneity the "
                 f"design needs, and it holds.",
            figure_path=figures["retirement"], table=_bands(bands),
            after="The logit carries season effects rather than "
                  "driver-season effects because many driver-seasons "
                  "contain no retirement at all, which predicts the "
                  "outcome perfectly and leaves the likelihood with no "
                  "finite maximum.")

        paper.section(
            "The held-out set that turned out not to exist",
            note="Pit-lane starts are excluded from every fit, because "
                 "the pit lane is not a grid slot. The intention was to "
                 "use them as a held-out set, moved further than any "
                 "penalty in the panel.",
            body=f"Almost none of them were moved at all. Their median "
                 f"distance from where they qualified is "
                 f"{far['median distance']:.0f} slots, and only "
                 f"{far['really moved']} of {far['classified']} "
                 f"classified starts were moved {far['cutoff']} or more, "
                 f"because the failure that earns a pit-lane start is "
                 f"usually the failure that ruined qualifying: these cars "
                 f"had already qualified at the back. For a few the "
                 f"distance is negative — when several cars start "
                 f"from the pit lane the grid is shorter than the "
                 f"qualifying order, so a car that qualified last was "
                 f"going to start last regardless.\n\n"
                 f"A pit-lane start is a severe punishment in every "
                 f"respect except the one measured here. "
                 + ("The implied slope is refused: " + far["refused"] + "."
                    if far["implied slope"] is None else
                    f"Over the moved ones the implied slope is "
                    f"{far['implied slope']:+.3f}.")
                 + f" {far['retired']} of {far['entries']} of these "
                   f"starts retired, against {retired_share:.0%} in the "
                   f"panel.",
            figure_path=figures["pit_lane"])

        paper.section(
            "Track by track",
            body=f"Shrinkage keeps "
                 f"{by_track['circuits'][0]['factor']:.0%} of the spread "
                 f"between circuits and attributes the rest to sampling "
                 f"noise. Jointly the {by_track['joint']['terms']} "
                 f"deviations give F = {by_track['joint']['F']:.2f}, "
                 f"p = {by_track['joint']['p']:.3f}.",
            figure_path=figures["circuits"],
            table=_circuits(by_track, labels))

        busiest = where["circuits"][:4]
        quietest = [one for one in where["circuits"]
                    if one["entries"] >= 40][-4:]
        paper.section(
            "Where the penalties happen is a choice",
            note="A team that must change a power unit decides when, and "
                 "it picks a weekend where starting further back is "
                 "cheap.",
            warn=f"The weighting is not where this bites: pooled over the "
                 f"eligible circuits the slope is "
                 f"{by_track['pooled']:+.3f} and the unweighted mean of "
                 f"their own slopes is {by_track['unweighted']:+.3f}, so "
                 f"the busy circuits are not dragging the pooled number "
                 f"about. What bites is the "
                 f"{len(by_track['left out'])} circuits that cannot be "
                 f"fitted at all — Monaco among them, where a slot "
                 f"should be worth most of anywhere. They are missing "
                 f"rather than down-weighted.",
            body="So the variation this entire project is identified from "
                 "is not spread evenly over the calendar. Every number "
                 "here answers \"what was a slot worth where penalties "
                 "were actually taken\", which is the right question for "
                 "pricing a penalty and a narrower one than pricing a "
                 "grid slot.",
            table=(["circuit", "entries", "moved", "share moved"],
                   [[labels.get(one["circuit"], one["circuit"]),
                     str(one["entries"]), str(one["moved"]),
                     f"{one['share']:.0%}"] for one in busiest]
                   + [["· · ·", "", "", ""]]
                   + [[labels.get(one["circuit"], one["circuit"]),
                       str(one["entries"]), str(one["moved"]),
                       f"{one['share']:.0%}"] for one in quietest]))

        paper.section(
            "What it cost, and what this does not do",
            body=f"{priced['entries']} demoted entries reached the flag "
                 f"inside the {priced['support']}-slot support, "
                 f"{priced['slots']:,} slots between them, with "
                 f"{priced['refused, beyond the support']} moved further "
                 f"and refused rather than extrapolated, for "
                 f"{priced['points']:.1f} championship points — "
                 f"{priced['points each']:.2f} an entry, with only "
                 f"{priced['entries that lost points']} of them losing "
                 f"anything at all, because most penalties land outside "
                 f"the points.",
            warn="This is what the penalised cars gave up, not what the "
                 "grid rearranged. Un-penalising one car moves every car "
                 "it passes, and those counterfactuals are not computed, "
                 "so the gains on the other side of these losses are "
                 "missing.",
            after="It is a local, linear average over the shifts that "
                  "happened, nearly all of them between one and ten "
                  "slots. It cannot say why a car was moved, because the "
                  "feed records no reason: gearbox, power unit, impeding "
                  "and blocking are one column. Sprint weekends are "
                  "dropped entirely. And the promoted-only estimate, the "
                  "one with no contamination in it, is too imprecise to "
                  "settle the question on its own.")

        paper.section(
            "The panel",
            note="Qualifying, grid and race results from the Jolpica "
                 "mirror of the Ergast schema.",
            table=(["", "entries"],
                   [[key, f"{value:,}"] for key, value in census.items()]))

    return out
