"""Six figures, written straight to PNG so the README renders on GitHub."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402

INK = "#16181d"
MUTED = "#5b6472"
GRID = "#e3e6ea"
GOOD = "#17803d"
BAD = "#b4232c"
LINE = "#1f5fa8"
WARM = "#d9a441"
SOFT = "#aab4c0"

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.titlesize": 12, "figure.dpi": 130, "savefig.bbox": "tight"})

LADDER = (("apparent, finish on grid", "finish on grid alone", SOFT),
          ("qualifying slot, pace and position", "a qualifying slot", SOFT),
          ("grid slot, position alone", "a grid slot, the experiment", LINE),
          ("within six slots either way", "the same, short moves only", LINE),
          ("demoted by their own penalty", "their own penalty only", WARM),
          ("promoted by somebody else", "somebody else's penalty only", GOOD))


def _frame(axis, title: str, subtitle: str = "") -> None:
    axis.set_title(title, loc="left", pad=22 if subtitle else 8,
                   fontweight="bold")
    if subtitle:
        axis.text(0, 1.02, subtitle, transform=axis.transAxes,
                  fontsize=9, color=MUTED, va="bottom")
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.set_axisbelow(True)


def ladder(path: Path, found: dict) -> Path:
    """Every slope the argument uses, with the interval each one supports."""
    figure, axis = plt.subplots(figsize=(8.6, 4.4))
    spots = np.arange(len(LADDER))
    for spot, (key, label, colour) in enumerate(LADDER):
        row = found[key]
        axis.plot([row["lower"], row["upper"]], [spot, spot], color=colour,
                  linewidth=3.2, solid_capstyle="round", zorder=3)
        axis.scatter([row["slope"]], [spot], s=110, color=colour,
                     edgecolor="white", linewidth=1.2, zorder=4)
        axis.text(row["upper"] + 0.015, spot, f"{row['slope']:+.2f}",
                  va="center", fontsize=9.5, color=colour, fontweight="bold")
    axis.axvline(0, color=INK, linewidth=1.2, zorder=2)
    axis.set_yticks(spots)
    axis.set_yticklabels([f"{label}\n({found[key]['n']:,} entries)"
                          for key, label, _ in LADDER], fontsize=9)
    axis.invert_yaxis()
    axis.set_xlabel("places worse at the flag, per slot further back")
    axis.grid(axis="x", color=GRID, linewidth=0.8)
    _frame(axis, "What a grid slot is worth, and what it looks like it is worth",
           "driver-season effects throughout; errors clustered on the race")
    out = path / "ladder.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def leverage(path: Path, rows) -> Path:
    """Where the evidence actually comes from, and how little of it there is."""
    figure, axis = plt.subplots(figsize=(8.6, 4.0))
    shifts = np.array([one.shift for one in rows])
    edges = np.arange(shifts.min() - 0.5, shifts.max() + 1.5, 1.0)
    counts, _ = np.histogram(shifts, bins=edges)
    centres = edges[:-1] + 0.5
    colours = [SOFT if value == 0 else (WARM if value > 0 else GOOD)
               for value in centres]
    axis.bar(centres, counts, color=colours, width=0.84)
    for centre, count in zip(centres, counts):
        if count:
            axis.text(centre, count * 1.12, f"{count:,}", ha="center",
                      fontsize=8, color=MUTED)
    axis.set_yscale("log")
    axis.set_ylim(0.7, counts.max() * 3)
    axis.set_xlabel("slots between where the car qualified and where it "
                    "started\n(left: promoted by somebody else    "
                    "right: demoted by its own penalty)")
    axis.set_ylabel("entries (log)")
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    promoted = int((shifts < 0).sum())
    demoted = int((shifts > 0).sum())
    _frame(axis, "All of the evidence, and most of it is one slot",
           f"{promoted:,} promoted and {demoted:,} demoted entries carry "
           f"every estimate here")
    out = path / "leverage.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def shuffle(path: Path, found: dict) -> Path:
    """Give the penalties to the wrong cars and the slope should vanish."""
    figure, axis = plt.subplots(figsize=(8.0, 3.8))
    slopes = found["slopes"]
    axis.hist(slopes, bins=36, color=SOFT, edgecolor="white", linewidth=0.6)
    for edge in (found["lower"], found["upper"]):
        axis.axvline(edge, color=MUTED, linewidth=1.0, linestyle=(0, (4, 3)))
    axis.axvline(found["observed"], color=BAD, linewidth=2.2, zorder=4)
    top = axis.get_ylim()[1]
    axis.text(found["observed"], top * 0.96,
              f"the real penalties  \n{found['observed']:+.3f}  ",
              color=BAD, fontsize=9.5, va="top", ha="right",
              fontweight="bold")
    axis.text(found["shuffled mean"], top * 0.45,
              f"{found['draws']} reshuffles\ncentre {found['shuffled mean']:+.3f}",
              color=MUTED, fontsize=9, ha="center")
    axis.set_xlabel("slope on the shift, places a slot")
    axis.set_ylabel("reshuffles")
    axis.grid(axis="y", color=GRID, linewidth=0.8)
    _frame(axis, "The penalties given to the wrong cars",
           "each race keeps its own penalties; only who received them changes")
    out = path / "shuffle.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def retirement(path: Path, found: dict, bands: list[dict]) -> Path:
    """Whether the dropped rows are dropped for a reason that matters."""
    figure, (left, right) = plt.subplots(1, 2, figsize=(9.2, 3.6))

    shares = [100 * one["share"] for one in bands]
    left.bar([one["grid"] for one in bands], shares, color=LINE, width=0.6)
    for spot, value in enumerate(shares):
        left.text(spot, value + 0.5, f"{value:.0f}%", ha="center",
                  fontsize=9.5, fontweight="bold")
    left.set_ylim(0, max(shares) * 1.3)
    left.set_xlabel("grid slot")
    left.set_ylabel("per cent retired")
    left.grid(axis="y", color=GRID, linewidth=0.8)
    _frame(left, "Retirements by where the car started",
           "raw rates, no model")

    one = found["shift"]
    bars = ["a slot further\nback on the grid", "a slot of it\nfrom a penalty"]
    values = [found["qualified"]["log odds"], one["log odds"]]
    errors = [1.96 * found["qualified"]["error"], 1.96 * one["error"]]
    right.bar(bars, values, yerr=errors, color=[SOFT, WARM], width=0.5,
              capsize=6, error_kw={"ecolor": MUTED, "elinewidth": 1.2})
    right.axhline(0, color=INK, linewidth=1.2)
    right.set_ylabel("log odds of reaching the flag")
    right.grid(axis="y", color=GRID, linewidth=0.8)
    _frame(right, "The same question, with the season held fixed",
           "a penalty does not predict retiring; the grid does")

    figure.tight_layout()
    out = path / "retirement.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def circuits(path: Path, found: dict, labels: dict) -> Path:
    """The slope track by track, before and after shrinkage."""
    figure, axis = plt.subplots(figsize=(8.6, 6.2))
    rows = found["circuits"]
    spots = np.arange(len(rows))
    for spot, row in enumerate(rows):
        axis.plot([row["slope"], row["shrunk"]], [spot, spot], color=SOFT,
                  linewidth=1.0, zorder=2)
        axis.scatter([row["slope"]], [spot], s=28, color=SOFT, zorder=3)
        axis.scatter([row["shrunk"]], [spot], s=80, color=LINE,
                     edgecolor="white", linewidth=1.0, zorder=4)
    axis.axvline(found["pooled"], color=INK, linewidth=1.4, zorder=1)
    axis.text(found["pooled"], len(rows) - 0.42,
              f" pooled {found['pooled']:+.2f}", fontsize=9, color=INK,
              va="top")
    axis.set_yticks(spots)
    axis.set_yticklabels(
        [f"{labels.get(row['circuit'], row['circuit'])[:20]} "
         f"({row['moved']})" for row in rows], fontsize=8.5)
    axis.invert_yaxis()
    axis.set_xlabel("places a slot, raw (small) and shrunk (large)")
    axis.grid(axis="x", color=GRID, linewidth=0.8)
    joint = found["joint"]
    _frame(axis, "Track by track, almost all of the spread is noise",
           f"shrinkage keeps {rows[0]['factor']:.0%} of it; the "
           f"{joint['terms']} deviations jointly give p = {joint['p']:.2f}")
    out = path / "circuits.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def pit_lane(path: Path, found: dict, pooled: float) -> Path:
    """The held-out set: cars moved further than any penalty in the panel."""
    figure, axis = plt.subplots(figsize=(8.2, 4.6))
    rows = found["rows"]
    distance = np.array([one["distance"] for one in rows], float)
    lost = np.array([one["lost"] for one in rows], float)
    inside = distance < found["cutoff"]
    axis.scatter(distance[inside], lost[inside], s=46, color=SOFT, alpha=0.9,
                 edgecolor="white", linewidth=0.8, zorder=3,
                 label="had already qualified at the back")
    axis.scatter(distance[~inside], lost[~inside], s=58, color=LINE, alpha=0.9,
                 edgecolor="white", linewidth=0.8, zorder=4,
                 label=f"genuinely moved {found['cutoff']} slots or more")
    reach = np.linspace(0, distance.max() * 1.05, 50)
    axis.plot(reach, pooled * reach, color=MUTED, linewidth=1.6,
              linestyle=(0, (5, 3)), zorder=2,
              label=f"the panel's slope, {pooled:+.2f} a slot")
    axis.axvline(found["cutoff"], color=WARM, linewidth=1.2, zorder=1)
    axis.axhline(0, color=INK, linewidth=1.0, zorder=1)
    axis.set_xlabel("slots between where the car qualified and the pit lane")
    axis.set_ylabel("places worse than the fit expected of this car")
    axis.grid(color=GRID, linewidth=0.8)
    axis.legend(frameon=False, fontsize=8.5, loc="upper left")
    _frame(axis, "The held-out test that turned out not to exist",
           f"{found['really moved']} of {found['classified']} classified "
           f"pit-lane starts were moved at all; {found['retired']} more "
           f"retired and are not plotted")
    out = path / "pit_lane.png"
    figure.savefig(out)
    plt.close(figure)
    return out


def draw(path: Path, **kwargs) -> dict[str, Path]:
    path.mkdir(parents=True, exist_ok=True)
    pooled = kwargs["found"]["grid slot, position alone"]["slope"]
    return {
        "ladder": ladder(path, kwargs["found"]),
        "leverage": leverage(path, kwargs["rows"]),
        "shuffle": shuffle(path, kwargs["shuffle"]),
        "retirement": retirement(path, kwargs["retired"], kwargs["bands"]),
        "circuits": circuits(path, kwargs["by_track"], kwargs["labels"]),
        "pit_lane": pit_lane(path, kwargs["far"], pooled),
    }
