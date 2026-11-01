"""Fetch and cache qualifying, grid and race results.

Three endpoints of the open Jolpica mirror of the Ergast schema, none of
which needs a key:

    /{season}/{round}/qualifying/   where each car earned its slot
    /{season}/{round}/results/      where it actually started, and finished
    /{season}/sprint/               which rounds had a sprint race

This project needs no lap times, so the fetch is small: two requests per
race and one per season, about 280 in all for 2018-2023.

**Why the sprint rounds are fetched only to be thrown away.** From 2021 a
sprint weekend sets the grid by the sprint result, not by qualifying. On
those weekends the gap between where a car qualified and where it started
is a race result, not a penalty, and it is exactly the variation this
project is built on. Including them would mean regressing finishing
position on a number that already contains a race. They are excluded, and
counted, in `build`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

API = "https://api.jolpi.ca/ergast/f1"
PAGE = 100
PAUSE = 1.1
RETRIES = 5

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data"

PIT_LANE = 0            # how the feed records a pit-lane start


@dataclass(frozen=True)
class Entry:
    """One car in one race: where it earned its slot, started and finished."""

    season: int
    round: int
    race: str
    circuit: str
    driver: str
    team: str
    qualified: int | None       # position in qualifying, None if no record
    grid: int                   # where it actually started; 0 = pit lane
    finish: int | None          # classified position, None if not classified
    status: str
    laps: int

    @property
    def race_id(self) -> tuple[int, int]:
        return (self.season, self.round)

    @property
    def pit_lane(self) -> bool:
        return self.grid == PIT_LANE

    @property
    def shift(self) -> int | None:
        """Slots the car was moved back between qualifying and the start.

        Positive is backwards. None when it cannot be stated as a number of
        slots: no qualifying record, or a pit-lane start, which is not a
        grid slot at all.
        """
        if self.qualified is None or self.pit_lane:
            return None
        return self.grid - self.qualified


def _request(url: str) -> dict:
    """GET with backoff on the mirror's rate limit."""
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == RETRIES - 1:
                raise
            time.sleep(2.0 * (attempt + 1))
        except urllib.error.URLError:
            if attempt == RETRIES - 1:
                raise
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"gave up on {url}")


def _rounds(season: int) -> list[dict]:
    payload = _request(f"{API}/{season}/races/?limit=100")
    return payload["MRData"]["RaceTable"]["Races"]


def sprint_rounds(season: int) -> set[int]:
    """The rounds whose grid was set by a sprint race rather than qualifying."""
    payload = _request(f"{API}/{season}/sprint/?limit=100")
    races = payload["MRData"]["RaceTable"]["Races"]
    return {int(race["round"]) for race in races}


def fetch_qualifying(season: int, round_: int) -> dict[str, int]:
    """driverId -> qualifying position. Empty if the feed has no record."""
    payload = _request(f"{API}/{season}/{round_}/qualifying/?limit={PAGE}")
    races = payload["MRData"]["RaceTable"]["Races"]
    if not races:
        return {}
    return {row["Driver"]["driverId"]: int(row["position"])
            for row in races[0].get("QualifyingResults", [])}


def fetch_results(season: int, round_: int, race: str, circuit: str,
                  qualifying: dict[str, int]) -> list[Entry]:
    payload = _request(f"{API}/{season}/{round_}/results/?limit={PAGE}")
    races = payload["MRData"]["RaceTable"]["Races"]
    if not races:
        return []
    out = []
    for row in races[0]["Results"]:
        driver = row["Driver"]["driverId"]
        shown = row["positionText"]
        out.append(Entry(
            season=season, round=round_, race=race, circuit=circuit,
            driver=driver, team=row["Constructor"]["constructorId"],
            qualified=qualifying.get(driver), grid=int(row["grid"]),
            finish=int(shown) if shown.isdigit() else None,
            status=row["status"], laps=int(row["laps"])))
    return out


def fetch_season(season: int, *, verbose: bool = True) -> dict:
    entries: list[Entry] = []
    sprints = sorted(sprint_rounds(season))
    time.sleep(PAUSE)

    for race in _rounds(season):
        round_ = int(race["round"])
        name = race["raceName"]
        circuit = race["Circuit"]["circuitId"]
        qualifying = fetch_qualifying(season, round_)
        time.sleep(PAUSE)
        rows = fetch_results(season, round_, name, circuit, qualifying)
        time.sleep(PAUSE)
        if not rows:
            if verbose:
                print(f"  {season} r{round_:2d} {name:30s} no results")
            continue
        entries.extend(rows)
        if verbose:
            mark = " sprint" if round_ in sprints else ""
            print(f"  {season} r{round_:2d} {name:30s} "
                  f"{len(rows):3d} cars, {len(qualifying):3d} qualified{mark}")

    return {"entries": [asdict(one) for one in entries], "sprints": sprints}


def load(seasons: tuple[int, ...], *, refresh: bool = False
         ) -> tuple[list[Entry], dict[int, set[int]]]:
    """Cached per season, so a re-run costs nothing."""
    CACHE.mkdir(exist_ok=True)
    entries: list[Entry] = []
    sprints: dict[int, set[int]] = {}

    for season in seasons:
        path = CACHE / f"season_{season}.json"
        if refresh or not path.exists():
            print(f"fetching {season}")
            payload = fetch_season(season)
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
        entries.extend(Entry(**row) for row in payload["entries"])
        sprints[season] = set(payload["sprints"])

    return entries, sprints
