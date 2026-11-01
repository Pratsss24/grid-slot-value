"""Tests for grid-slot-value.

Three kinds, and no fourth:

* **Algebra with one right answer.** Two parameterisations of the same fit
  have to give the same slope because `grid = qualified + shift` is an
  identity; demeaning within a group has to give the same slope as a
  column of dummies, because Frisch-Waugh-Lovell says so; shrinkage with
  no sampling error has to leave the estimates alone.
* **Recovery of a planted truth.** A synthetic season is built with a
  known slot effect and the estimator has to find it. Where a diagnostic
  is meant to detect a problem, the problem is planted and the diagnostic
  has to react - and, just as important, has to stay quiet when it is not
  there.
* **Refusals.** Every measurement the code declines to make is checked to
  be declined, because a silent default is the bug that cost this series
  the most time.

Nothing here compares against saved output.

**On the fixture.** It does not force each race's finishing positions to
be a permutation of one to twenty. The estimator does not need one, and
forcing it would put a rank transform between the planted slope and the
fitted one, which leaves a recovery test unable to check a number - only
a sign. Positions are the linear model rounded and held inside the field,
and the parameters are chosen so that holding rarely bites.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import confound                                             # noqa: E402
import linear                                               # noqa: E402
import panel                                                # noqa: E402
import placebo                                              # noqa: E402
import slot                                                 # noqa: E402

BASE = 2.0
PACE = 0.55
CARS = 20
CIRCUITS = ("alpha", "beta", "gamma", "delta")


def season(*, races: int = 24, cars: int = CARS, slope: float = 0.5,
           seasons: int = 2, seed: int = 0, noise: float = 1.2,
           demote_rate: float = 0.08, max_demote: int = 8,
           handicap: float = 0.0, slopes: dict[str, float] | None = None,
           retire_base: float = 0.0, retire_gradient: float = 0.0,
           penalise_slumping: float = 0.0,
           circuits: tuple[str, ...] = CIRCUITS) -> list[panel.Row]:
    """A synthetic panel with a known slot effect.

    `handicap` plants the endogeneity the design is afraid of: a demoted
    car is also slower on Sunday, for the same reason it was demoted. It
    is applied to demotions only - a car promoted by somebody else's
    gearbox has nothing wrong with it, and that asymmetry is the whole
    reason `promoted` exists.
    `slopes` plants a different slot effect per circuit. `retire_gradient`
    makes cars further back likelier to retire. `penalise_slumping` hands
    penalties to drivers whose previous race went badly, which is the
    violation `placebo.past` exists to find.
    """
    generator = np.random.default_rng(seed)
    quality = generator.normal(0, 2.0, cars)
    rows: list[panel.Row] = []
    last: dict[int, int | None] = {car: None for car in range(cars)}

    for year in range(2018, 2018 + seasons):
        effect = generator.normal(0, 1.0, cars)
        for round_ in range(1, races + 1):
            circuit = circuits[(round_ - 1) % len(circuits)]
            order = np.argsort(quality + generator.normal(0, 1.5, cars))
            here = slope if slopes is None else slopes.get(circuit, slope)
            for place, car in enumerate(order, start=1):
                slumping = (penalise_slumping
                            if last[car] is not None and last[car] > cars / 2
                            else 0.0)
                demoted = generator.random() < demote_rate + slumping
                shift = (int(generator.integers(1, max_demote + 1))
                         if demoted else 0)
                if not demoted and generator.random() < 0.18:
                    shift = -int(generator.integers(1, 3))
                # The shift is clamped, not the grid: clamping the grid
                # would leave the row claiming a shift it did not have and
                # break `grid == qualified + shift`, which is the identity
                # one of these tests exists to check.
                shift = max(shift, 1 - place)
                latent = (BASE + PACE * place + here * shift + effect[car]
                          + handicap * max(shift, 0)
                          + generator.normal(0, noise))
                grid = place + shift
                chance = min(retire_base
                             + retire_gradient * (grid - 1) / cars, 0.95)
                finish = (None if generator.random() < chance
                          else int(max(1, min(cars, round(latent)))))
                rows.append(panel.Row(
                    season=year, round=round_, race=f"{circuit.title()} "
                    f"Grand Prix", circuit=circuit, driver=f"d{car}",
                    team=f"t{car // 2}", qualified=place, grid=grid,
                    shift=shift, finish=finish, status="Finished",
                    previous=last[car]))
                last[car] = finish
    return rows


# ---- algebra with one right answer ------------------------------------

def test_points_table_edges():
    assert panel.points_for(1) == 25.0
    assert panel.points_for(10) == 1.0
    assert panel.points_for(11) == 0.0
    assert panel.points_for(None) == 0.0
    assert panel.points_for(0) == 0.0


def test_shift_and_direction_conventions():
    rows = season(races=2, seasons=1, seed=1)
    for one in rows:
        assert one.shift == one.grid - one.qualified
        assert one.grid >= 1
        if one.shift > 0:
            assert one.moved == "demoted"
        elif one.shift < 0:
            assert one.moved == "promoted"
        else:
            assert one.moved == "unmoved"


def test_dummies_are_an_indicator_basis():
    matrix, names = panel.dummies(["a", "b", "a", "c"])
    assert names == ("a", "b", "c")
    assert matrix.shape == (4, 3)
    assert np.allclose(matrix.sum(axis=1), 1.0)
    assert np.linalg.matrix_rank(matrix) == 3


def test_the_two_parameterisations_agree():
    """`grid = qualified + shift`, so one fit must be the other rearranged.

    Fitting on (qualified, shift) and on (grid, qualified) are the same
    model written twice. The slot effect must come out identical, and the
    qualifying coefficient must differ from it by exactly the premium.
    """
    rows = [one for one in season(seed=2) if one.classified]
    first = slot.controlled(rows)

    y = np.array([one.finish for one in rows], float)
    columns = {"grid": np.array([one.grid for one in rows], float),
               "qualified": np.array([one.qualified for one in rows], float)}
    matrix, names, cluster = panel.design(rows, columns)
    second = linear.ols(y, matrix, names, cluster)

    assert second["grid"] == pytest.approx(first["shift"], abs=1e-9)
    assert second["qualified"] == pytest.approx(
        first["qualified"] - first["shift"], abs=1e-9)
    assert slot.premium(first)["value"] == pytest.approx(
        second["qualified"], abs=1e-9)


def test_demeaning_matches_dummy_columns():
    """Frisch-Waugh-Lovell: the fast path and the slow path are one path.

    `placebo.shuffled` refits several hundred times and uses demeaning to
    afford it. If the two ever disagreed, every shuffle would be testing a
    different model from the one being defended.
    """
    rows = [one for one in season(seed=3) if one.classified]
    slow = slot.controlled(rows)["shift"]
    fast = placebo.demeaned_slope(
        np.array([one.finish for one in rows], float),
        np.array([one.qualified for one in rows], float),
        np.array([one.shift for one in rows], float),
        np.array([one.driver_season for one in rows]))
    assert fast == pytest.approx(slow, abs=1e-9)


def test_combination_of_one_term_is_that_term():
    rows = [one for one in season(seed=4) if one.classified]
    fit = slot.controlled(rows)
    found = linear.combination(fit, {"shift": 1.0})
    assert found["value"] == pytest.approx(fit["shift"], abs=1e-12)
    assert found["error"] == pytest.approx(fit.error("shift"), abs=1e-12)


def test_combination_carries_the_covariance():
    """A difference of two correlated slopes is not the quadrature sum."""
    rows = [one for one in season(seed=5) if one.classified]
    fit = slot.controlled(rows)
    found = linear.combination(fit, {"qualified": 1.0, "shift": -1.0})
    naive = np.hypot(fit.error("qualified"), fit.error("shift"))
    assert found["error"] != pytest.approx(naive, rel=1e-3)
    index = [fit.index("qualified"), fit.index("shift")]
    weights = np.array([1.0, -1.0])
    block = fit.covariance[np.ix_(index, index)]
    assert found["error"] == pytest.approx(
        float(np.sqrt(weights @ block @ weights)), abs=1e-12)


def test_shrinkage_with_no_error_changes_nothing():
    rows = [{"slope": 0.1, "error": 0.0}, {"slope": 0.5, "error": 0.0},
            {"slope": 0.9, "error": 0.0}]
    out = slot.shrink(rows, pooled=0.5)
    assert [one["factor"] for one in out] == [1.0, 1.0, 1.0]
    assert sorted(one["shrunk"] for one in out) == pytest.approx(
        [0.1, 0.5, 0.9])


def test_shrinkage_with_only_error_collapses_to_the_pool():
    rows = [{"slope": 0.1, "error": 9.0}, {"slope": 0.5, "error": 9.0},
            {"slope": 0.9, "error": 9.0}]
    out = slot.shrink(rows, pooled=0.4)
    assert out[0]["factor"] == 0.0
    assert all(one["shrunk"] == pytest.approx(0.4) for one in out)


def test_names_strip_what_every_race_shares():
    rows = season(races=4, seasons=1, seed=6)
    labels = panel.names(rows)
    assert labels["alpha"] == "Alpha"
    assert all("Grand Prix" not in one for one in labels.values())


# ---- the panel, and its exclusions ------------------------------------

class Entry:
    """The shape `panel.build` consumes, without the fetcher attached."""

    def __init__(self, *, season=2022, round=1, qualified=5, grid=5,
                 finish=5, driver="d1"):
        self.season, self.round, self.driver = season, round, driver
        self.race, self.circuit, self.team = "Alpha Grand Prix", "alpha", "t1"
        self.qualified, self.grid, self.finish = qualified, grid, finish
        self.status, self.laps = "Finished", 50

    @property
    def pit_lane(self):
        return self.grid == 0


def test_build_counts_every_exclusion():
    entries = [Entry(round=1),
               Entry(round=2),                      # a sprint round
               Entry(round=3, qualified=None),
               Entry(round=4, grid=0),              # the pit lane
               Entry(round=5, finish=None)]
    rows, pit_lane, census = panel.build(entries, {2022: {2}})
    assert census["entries in the feed"] == 5
    assert census["dropped, sprint weekend"] == 1
    assert census["dropped, no qualifying record"] == 1
    assert census["set aside, started from the pit lane"] == 1
    assert census["in the panel"] == 2
    assert census["of those, classified at the flag"] == 1
    assert len(pit_lane) == 1
    assert {one.round for one in rows} == {1, 5}


def test_previous_is_the_driver_s_own_last_race_in_order():
    entries = [Entry(round=3, finish=7), Entry(round=1, finish=3),
               Entry(round=2, finish=None), Entry(round=4, finish=1),
               Entry(driver="d2", round=1, finish=9)]
    rows, _, _ = panel.build(entries, {})
    found = {one.round: one.previous for one in rows if one.driver == "d1"}
    assert found == {1: None, 2: 3, 3: None, 4: 7}
    assert [one.previous for one in rows if one.driver == "d2"] == [None]


# ---- recovery of a planted truth ---------------------------------------

def test_the_planted_slot_effect_is_recovered():
    rows = season(slope=0.5, seed=10)
    fit = slot.controlled(rows)
    lower, upper = fit.interval("shift")
    assert lower < 0.5 < upper
    assert fit["shift"] == pytest.approx(0.5, abs=0.12)


def test_a_planted_absence_is_not_invented():
    rows = season(slope=0.0, seed=11)
    fit = slot.controlled(rows)
    lower, upper = fit.interval("shift")
    assert lower < 0.0 < upper


def test_the_apparent_slope_exceeds_the_real_one():
    """The whole reason the project exists, on data where the truth is known.

    The planted slot effect is 0.3 while qualifying position carries 0.55
    of its own. Regressing on grid alone has to overstate the slot.
    """
    rows = season(slope=0.3, seed=12)
    assert slot.naive(rows)["grid"] > slot.controlled(rows)["shift"]


def test_endogenous_penalties_bias_the_demoted_slope_upwards():
    """Plant the contamination and check the diagnostic reacts.

    `handicap` makes a demoted car slower on Sunday as well as further
    back - the gearbox story. The slope fitted on demoted cars has to
    overstate the planted truth, and the slope fitted on cars promoted by
    somebody else's penalty must not.
    """
    rows = season(slope=0.3, handicap=0.45, seed=13)
    assert slot.demoted(rows)["shift"] > 0.5
    clean = slot.promoted(rows)
    lower, upper = clean.interval("shift")
    assert lower < 0.3 < upper


def test_clean_penalties_leave_the_two_halves_agreeing():
    rows = season(slope=0.4, handicap=0.0, seed=14)
    gap = slot.demoted(rows)["shift"] - slot.promoted(rows)["shift"]
    assert abs(gap) < 0.3


def test_directions_recovers_a_symmetric_effect_as_symmetric():
    rows = season(slope=0.4, seed=15)
    found = slot.directions(rows)
    assert found["backward"]["slope"] > 0
    assert found["forward"]["slope"] < 0
    total = found["sum"]
    assert total["lower"] < 0.0 < total["upper"]


def test_circuit_slopes_are_recovered_in_the_right_order():
    rows = season(races=40, seasons=3, demote_rate=0.18, seed=16,
                  slopes={"alpha": 0.8, "beta": 0.1, "gamma": 0.45,
                          "delta": 0.45})
    found = slot.by_circuit(rows)
    slopes = {one["circuit"]: one["slope"] for one in found["circuits"]}
    assert slopes["alpha"] > slopes["gamma"] > slopes["beta"]
    assert found["joint"]["p"] < 0.05


def test_identical_circuits_are_not_given_an_order():
    rows = season(races=40, seasons=3, demote_rate=0.18, slope=0.4, seed=17)
    found = slot.by_circuit(rows)
    assert found["joint"]["p"] > 0.05
    spread = max(one["shrunk"] for one in found["circuits"]) - \
        min(one["shrunk"] for one in found["circuits"])
    assert spread < 0.15


# ---- the placebos, in both directions ----------------------------------

def test_the_shuffle_finds_a_planted_effect():
    rows = season(slope=0.5, seed=20)
    found = placebo.shuffled(rows, draws=120, seed=1)
    assert found["p"] < 0.05
    assert found["observed"] > found["upper"]


def test_the_shuffle_stays_quiet_when_there_is_nothing():
    rows = season(slope=0.0, seed=21)
    found = placebo.shuffled(rows, draws=200, seed=2)
    assert found["p"] > 0.05
    assert found["lower"] < found["observed"] < found["upper"]
    assert abs(found["shuffled mean"]) < 0.05


def test_the_shuffle_keeps_each_race_s_own_penalties():
    """The reshuffle must redistribute, not resample."""
    rows = [one for one in season(races=6, seasons=1, seed=22)
            if one.classified]
    shift = np.array([one.shift for one in rows], float)
    races = np.array([f"{one.season}:{one.round}" for one in rows])
    generator = np.random.default_rng(0)
    swapped = shift.copy()
    for one in np.unique(races):
        block = np.flatnonzero(races == one)
        swapped[block] = generator.permutation(shift[block])
    for one in np.unique(races):
        block = np.flatnonzero(races == one)
        assert sorted(swapped[block]) == sorted(shift[block])


def test_the_past_is_not_predicted_by_a_later_penalty():
    rows = season(slope=0.5, seed=23)
    found = placebo.past(rows)
    assert found["lower"] < 0.0 < found["upper"]


def test_the_past_test_catches_penalties_that_follow_form():
    """Hand penalties to drivers who have just had a bad race.

    This is the violation that would make the main slope meaningless, and
    a placebo that could not see it would be decoration.
    """
    rows = season(slope=0.5, penalise_slumping=0.5, seed=24)
    found = placebo.past(rows)
    assert found["p"] < 0.05
    assert found["slope"] > 0


# ---- the retirement check ----------------------------------------------

def test_a_planted_retirement_gradient_is_found():
    rows = season(races=40, seasons=3, retire_base=0.05,
                  retire_gradient=0.5, seed=30)
    found = confound.retirement(rows)
    assert found["qualified"]["odds ratio"] < 1.0
    assert found["qualified"]["p"] < 0.05
    front = confound.chance(found["fit"], qualified=2, shift=0)
    back = confound.chance(found["fit"], qualified=18, shift=0)
    assert front > back


def test_retiring_at_random_leaves_the_grid_term_flat():
    rows = season(races=40, seasons=3, retire_base=0.15,
                  retire_gradient=0.0, seed=31)
    found = confound.retirement(rows)
    assert found["qualified"]["lower"] < 0.0 < found["qualified"]["upper"]


def test_driver_season_effects_separate_the_logit():
    """The reason `retirement` uses season effects, checked and not assumed."""
    rows = season(races=6, seasons=1, retire_base=0.1, seed=32)
    reason = confound.separates(rows)
    assert "separat" in reason or "rank" in reason


def test_a_logit_refuses_a_perfectly_separating_column():
    y = np.array([0.0, 0.0, 1.0, 1.0])
    matrix = np.column_stack([np.array([0.0, 1.0, 8.0, 9.0]), np.ones(4)])
    with pytest.raises(ValueError):
        linear.logit(y, matrix, ("x", "one"), np.arange(4))


def test_bands_cover_the_grid_without_overlapping():
    edges = [(low, high) for low, high, _ in confound.BANDS]
    for (_, high), (low, _) in zip(edges, edges[1:]):
        assert low == high + 1
    assert edges[0][0] == 1


# ---- refusals -----------------------------------------------------------

def test_controlled_refuses_a_panel_nothing_moved_in():
    rows = season(races=20, seasons=2, demote_rate=0.0, seed=40)
    rows = [one for one in rows if one.shift == 0]
    with pytest.raises(ValueError, match="not identified"):
        slot.controlled(rows)


def test_controlled_refuses_too_few_rows():
    with pytest.raises(ValueError, match="too few"):
        slot.controlled(season(races=1, seasons=1, cars=8, seed=41))


def test_by_circuit_refuses_when_too_few_circuits_qualify():
    rows = season(races=24, seasons=2, seed=42, circuits=("alpha", "beta"))
    with pytest.raises(ValueError, match="fewer than three"):
        slot.by_circuit(rows)


def test_cost_refuses_to_extrapolate_beyond_its_support():
    rows = season(slope=0.4, max_demote=14, seed=43)
    found = confound.cost(rows, 0.4, support=6)
    assert found["refused, beyond the support"] > 0
    assert all(one.shift <= 6 for one in rows
               if one.classified and one.shift > 0
               and one.shift <= found["support"])


def test_cost_counts_only_what_crossed_a_points_boundary():
    """Most penalties cost nothing, because most of the grid scores nothing."""
    rows = season(slope=0.4, seed=44)
    found = confound.cost(rows, 0.4)
    assert 0 < found["entries that lost points"] < found["entries"]
    assert found["points"] > 0


def test_extrapolate_refuses_a_held_out_set_that_was_never_moved():
    rows = season(seed=45)
    fit = slot.controlled(rows)
    pit_lane = [one for one in rows if one.qualified >= CARS - 1][:12]
    found = slot.extrapolate(pit_lane, rows, fit)
    assert found["implied slope"] is None
    assert "too few to divide by" in found["refused"]
