"""Turn race entries into the panel the estimates are made on.

The whole project rests on one accident of the sport: a grid penalty
moves a car without changing the car, the driver or the weekend. So the
panel keeps, for every entry, both where the car *earned* its slot and
where it *started*, and the difference between them.

Four exclusions, all counted rather than assumed:

* **Sprint weekends.** From 2021 the sprint result sets the grid, so the
  gap between qualifying and the start is a race result rather than a
  penalty. Keeping them would put a race on the right-hand side.
* **Entries with no qualifying record.** Without one there is no slot the
  car earned, so there is no shift to measure.
* **Pit-lane starts.** The feed records these as grid 0. A pit-lane start
  is not a grid slot and the distance from, say, ninth to the pit lane is
  not a number of places. They are set aside and reported on their own.
* **Cars not classified.** A retirement has no finishing position, so it
  cannot be in a model of finishing position. It is not thrown away: the
  same rows are what the retirement check in `confound` is fitted on,
  because whether the back of the grid retires more often is the one way
  this exclusion could bend the main result.

`previous` is the driver's finishing position in their own previous race,
in season-and-round order. Nothing in the main estimate uses it. It is
there for the placebo in `placebo.past`, which asks whether a penalty
predicts a result that happened before it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# The scoring system in force for every season here (2010 onwards). The
# point for the fastest lap is not in the feed and is not counted.
POINTS = (25.0, 18.0, 15.0, 12.0, 10.0, 8.0, 6.0, 4.0, 2.0, 1.0)


def points_for(position: int | None) -> float:
    """Championship points for a finishing position, 0 outside the top ten."""
    if position is None or position < 1 or position > len(POINTS):
        return 0.0
    return POINTS[position - 1]


@dataclass(frozen=True)
class Row:
    """One car in one race, with the shift that makes it useful."""

    season: int
    round: int
    race: str
    circuit: str
    driver: str
    team: str
    qualified: int
    grid: int
    shift: int                  # grid - qualified; positive is backwards
    finish: int | None
    status: str
    previous: int | None        # this driver's finish in their previous race

    @property
    def race_id(self) -> tuple[int, int]:
        return (self.season, self.round)

    @property
    def driver_season(self) -> str:
        return f"{self.driver}:{self.season}"

    @property
    def classified(self) -> bool:
        return self.finish is not None

    @property
    def moved(self) -> str:
        if self.shift > 0:
            return "demoted"
        if self.shift < 0:
            return "promoted"
        return "unmoved"

    @property
    def points(self) -> float:
        return points_for(self.finish)


def _previous(entries) -> dict[tuple[str, int, int], int | None]:
    """Each entry's driver's finishing position in their own previous race."""
    by_driver: dict[str, list] = {}
    for one in entries:
        by_driver.setdefault(one.driver, []).append(one)
    out: dict[tuple[str, int, int], int | None] = {}
    for driver, rows in by_driver.items():
        rows.sort(key=lambda one: (one.season, one.round))
        last: int | None = None
        for one in rows:
            out[(driver, one.season, one.round)] = last
            last = one.finish
    return out


def build(entries, sprints: dict[int, set[int]]
          ) -> tuple[list[Row], list, dict[str, int]]:
    """The analysis panel, the pit-lane starts, and a census of the rest."""
    before = _previous(entries)
    panel: list[Row] = []
    pit_lane: list = []
    census = {"entries in the feed": len(entries),
              "dropped, sprint weekend": 0,
              "dropped, no qualifying record": 0,
              "set aside, started from the pit lane": 0,
              "in the panel": 0,
              "of those, classified at the flag": 0,
              "of those, moved by a penalty": 0}

    for one in entries:
        if one.round in sprints.get(one.season, set()):
            census["dropped, sprint weekend"] += 1
            continue
        if one.qualified is None:
            census["dropped, no qualifying record"] += 1
            continue
        if one.pit_lane:
            census["set aside, started from the pit lane"] += 1
            pit_lane.append(one)
            continue
        panel.append(Row(
            season=one.season, round=one.round, race=one.race,
            circuit=one.circuit, driver=one.driver, team=one.team,
            qualified=one.qualified, grid=one.grid,
            shift=one.grid - one.qualified, finish=one.finish,
            status=one.status,
            previous=before.get((one.driver, one.season, one.round))))

    census["in the panel"] = len(panel)
    census["of those, classified at the flag"] = sum(
        1 for one in panel if one.classified)
    census["of those, moved by a penalty"] = sum(
        1 for one in panel if one.shift != 0)
    return panel, pit_lane, census


def names(rows) -> dict[str, str]:
    """Circuit id to something readable: `rodriguez` is Mexico City.

    The feed's circuit ids are what the fits are keyed on, and they are
    not names a reader knows. The race name is, so each circuit takes the
    one it most often ran under, with the words every race shares removed.
    """
    seen: dict[str, dict[str, int]] = {}
    for one in rows:
        tally = seen.setdefault(one.circuit, {})
        label = one.race.replace("Grand Prix", "").strip()
        tally[label] = tally.get(label, 0) + 1
    return {circuit: max(tally, key=lambda one: tally[one])
            for circuit, tally in seen.items()}


def dummies(labels) -> tuple[np.ndarray, tuple[str, ...]]:
    """One column per distinct label, with no column left out.

    Used without a separate intercept, so every level gets a column and
    the design keeps full rank. These absorb the fixed effects, and the
    degrees-of-freedom correction in `linear.ols` counts them, which is
    the reason for spending the columns instead of demeaning by hand.
    """
    names = tuple(sorted(set(labels)))
    index = {name: spot for spot, name in enumerate(names)}
    matrix = np.zeros((len(labels), len(names)))
    for row, label in enumerate(labels):
        matrix[row, index[label]] = 1.0
    return matrix, names


def design(rows, columns: dict[str, np.ndarray], *, by: str = "driver_season"
           ) -> tuple[np.ndarray, tuple[str, ...], np.ndarray]:
    """Stack named columns onto fixed-effect dummies, and the race labels.

    `by` names the attribute whose levels are absorbed. The returned
    cluster labels are always the race, because a penalty to one car
    promotes every car behind it: the shifts inside one race are the same
    event seen from twenty cars, not twenty events.
    """
    blocks = [value.reshape(-1, 1).astype(float) for value in columns.values()]
    effects, levels = dummies([getattr(one, by) for one in rows])
    names = tuple(columns) + tuple(f"{by}:{one}" for one in levels)
    matrix = np.hstack(blocks + [effects]) if blocks else effects
    cluster = np.array([f"{one.season}:{one.round}" for one in rows])
    return matrix, names, cluster
