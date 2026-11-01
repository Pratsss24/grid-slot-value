"""One self-contained HTML file: charts inlined, no assets, no server."""

from __future__ import annotations

import base64
from pathlib import Path

CSS = """
body{font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;max-width:1120px;
margin:40px auto;padding:0 20px;color:#16181d}
h1{margin-bottom:4px}h2{margin-top:38px;border-bottom:1px solid #e3e6ea;
padding-bottom:6px}
.sub{color:#5b6472;margin-top:0}
.tiles{display:flex;gap:14px;flex-wrap:wrap;margin:22px 0}
.tile{flex:1;min-width:150px;background:#f6f8fa;border:1px solid #e3e6ea;
border-radius:9px;padding:14px 16px}
.tile .v{font-size:25px;font-weight:650;letter-spacing:-.5px}
.tile .k{font-size:11px;text-transform:uppercase;letter-spacing:.07em;
color:#5b6472;margin-top:3px}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px}
th,td{border:1px solid #e3e6ea;padding:7px 10px;text-align:right}
th:first-child,td:first-child{text-align:left}
th{background:#f6f8fa;font-weight:600}
td.good{color:#17803d}td.bad{color:#b4232c}
img{width:100%;margin:14px 0;border:1px solid #e3e6ea;border-radius:7px}
.note{background:#fff8e6;border-left:3px solid #d9a441;padding:11px 15px;
margin:18px 0;font-size:14px}
code{background:#f0f2f5;padding:1px 5px;border-radius:4px;font-size:13px}
"""

LADDER = (("apparent, finish on grid", "finishing position on grid alone"),
          ("qualifying slot, pace and position", "a qualifying slot"),
          ("grid slot, position alone", "a grid slot, the experiment"),
          ("within six slots either way", "the same, short moves only"),
          ("demoted by their own penalty", "their own penalty only"),
          ("promoted by somebody else", "somebody else's penalty only"))


def _img(path: Path) -> str:
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f'<img src="data:image/png;base64,{encoded}" alt="{Path(path).stem}">'


def _counts(census: dict) -> str:
    return "".join(f"<tr><td>{key}</td><td>{value:,}</td></tr>"
                   for key, value in census.items())


def _ladder_rows(found: dict) -> str:
    out = []
    for key, label in LADDER:
        row = found[key]
        clear = row["lower"] > 0
        cell = ' class="good"' if clear else ""
        verdict = "yes" if clear else "no"
        out.append(
            f"<tr><td>{label}</td><td>{row['n']:,}</td>"
            f"<td>{row['slope']:+.3f}</td>"
            f"<td>{row['lower']:+.3f} to {row['upper']:+.3f}</td>"
            f"<td{cell}>{verdict}</td></tr>")
    return "".join(out)


def _circuit_rows(by_track: dict, labels: dict) -> str:
    return "".join(
        f"<tr><td>{labels.get(row['circuit'], row['circuit'])}{' (baseline)' if row['baseline'] else ''}"
        f"</td><td>{row['entries']}</td><td>{row['moved']}</td>"
        f"<td>{row['slope']:+.3f}</td><td>{row['error']:.3f}</td>"
        f"<td>{row['shrunk']:+.3f}</td></tr>"
        for row in by_track["circuits"])


def _band_rows(bands: list[dict]) -> str:
    return "".join(
        f"<tr><td>{row['grid']} ({row['band']})</td><td>{row['entries']:,}</td>"
        f"<td>{row['retired']}</td><td>{row['share']:.1%}</td></tr>"
        for row in bands)


def build(*, census, found, split, shuffle, past, retired, bands, by_track,
          far, where, labels, priced, seasons, figures,
          out_path: Path) -> Path:
    slot = found["grid slot, position alone"]
    apparent = found["apparent, finish on grid"]
    premium = found["pace premium, qualifying minus grid"]
    years = f"{min(seasons)}-{max(seasons)}"
    moved = census["of those, moved by a penalty"]

    tiles = [("a grid slot is worth", f"{slot['slope']:+.2f} places"),
             ("it looks worth", f"{apparent['slope']:+.2f} places"),
             ("entries moved by a penalty", f"{moved:,}"),
             ("points it cost them", f"{priced['points']:.0f}")]
    tiles_html = "".join(
        f'<div class="tile"><div class="v">{v}</div><div class="k">{k}</div></div>'
        for k, v in tiles)

    symmetry = split["sum"]
    retired_share = 1 - (census["of those, classified at the flag"]
                         / census["in the panel"])
    if far["implied slope"] is None:
        implied = "the implied slope is refused: " + far["refused"]
    else:
        implied = ("over the moved ones the implied slope is "
                   f"{far['implied slope']:+.3f}")
    busiest = where["circuits"][:4]
    quietest = [one for one in where["circuits"] if one["entries"] >= 40][-4:]
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>What a grid slot is worth</title><style>{CSS}</style></head>
<body>
<h1>What a grid slot is worth</h1>
<p class="sub">Formula 1, {years}. Where a car starts predicts where it
finishes almost perfectly, and almost none of that is the starting place:
quick cars start at the front. A grid penalty is the one thing in the sport
that moves a car without changing the car, the driver or the weekend, so
every number here is measured from penalties.</p>
{tiles_html}

<h2>The experiment</h2>
<p>Keep both numbers - where the car earned its slot in qualifying, and
where it actually started - and the difference between them is a shift the
car's own pace did not cause. Within a driver's own season and at a given
qualifying position, the only thing moving that shift is a steward or
somebody else's failed gearbox.</p>
{_img(figures['ladder'])}
<table><tr><th>what is being measured</th><th>entries</th>
<th>places a slot</th><th>95% interval</th><th>excludes zero</th></tr>
{_ladder_rows(found)}</table>
<p>The pace premium - what a qualifying slot is worth beyond the track
position it comes with - is
<b>{premium['value']:+.3f}</b> places a slot, 95%
[{premium['lower']:+.3f}, {premium['upper']:+.3f}], p =
{premium['p']:.3f}.</p>

<h2>All of the evidence</h2>
{_img(figures['leverage'])}
<p>This is the honest limit of the design. A promotion is nearly always a
single slot, so the estimate fitted on promoted cars alone - the only
cars moved for a reason that has nothing to do with them - has an interval
wide enough to contain both zero and the pooled answer. It is not a
refutation and it is not a confirmation.</p>
<p>Fitting both directions in one design makes the comparison testable:
backwards {split['backward']['slope']:+.3f}, forwards
{split['forward']['slope']:+.3f}. If the effect were symmetric these would
sum to zero; they sum to {symmetry['value']:+.3f} &plusmn;
{symmetry['error']:.3f}, p = {symmetry['p']:.3f}.</p>

<h2>Two ways to catch this inventing an effect</h2>
{_img(figures['shuffle'])}
<p>Within each race, give the penalties to the wrong cars. Every race
keeps exactly the penalties it really had; only who received them is
destroyed. <b>{shuffle['at least as large']} of {shuffle['draws']}
reshuffles reached the real slope (p =
{shuffle['p']:.4f})</b>, and they centre on
{shuffle['shuffled mean']:+.3f}.</p>
<p>Then the same fit, predicting a race that already happened. A penalty
handed out on Saturday cannot change what the same driver did a fortnight
earlier, so the slope on the driver's <em>previous</em> finishing position
has to be zero: it is <b>{past['slope']:+.3f}</b> &plusmn;
{past['error']:.3f}, p = {past['p']:.3f}. Anything else would mean
penalties go to drivers whose results were already moving.</p>

<h2>The exclusion that could bend it</h2>
{_img(figures['retirement'])}
<p>A retirement has no finishing position, so {retired['retired']:,} of
{retired['entries']:,} entries are not in the main fit. If starting
further back made a car likelier to be collected at the first corner, the
worst consequences of a bad slot would be quietly missing.</p>
<table><tr><th>grid slot</th><th>entries</th><th>retired</th>
<th>share</th></tr>{_band_rows(bands)}</table>
<div class="note">A grid slot does predict retiring (odds ratio
{retired['qualified']['odds ratio']:.3f} a slot, p =
{retired['qualified']['p']:.3f}), but a <em>penalty</em> does not
(odds ratio {retired['shift']['odds ratio']:.3f}, p =
{retired['shift']['p']:.3f}). The first is a selection effect on the
outcome and makes the main slope an understatement; the second is the
exogeneity the design needs, and it holds.</div>
<p class="sub">The logit carries season effects rather than driver-season
effects because many driver-seasons contain no retirement at all, which
predicts the outcome perfectly and leaves the likelihood with no finite
maximum. Attempting it returns: <code>{retired['driver effects']}</code></p>

<h2>The held-out set that turned out not to exist</h2>
{_img(figures['pit_lane'])}
<p>Pit-lane starts are excluded from every fit, because the pit lane is
not a grid slot and the distance from ninth to it is not a number of
places. The intention was to use them as a held-out set, moved further
than any penalty in the panel.</p>
<p><b>Almost none of them were moved at all.</b> Their median distance
from where they qualified is {far['median distance']:.0f} slots and only
{far['really moved']} of {far['classified']} classified starts were moved
{far['cutoff']} or more, because the failure that earns a pit-lane start
is usually the failure that ruined qualifying: these cars had already
qualified at the back. For a few the distance is negative - when several
cars start from the pit lane the grid is shorter than the qualifying
order, so a car that qualified last was going to start last regardless. A
pit-lane start is a severe punishment in every respect except the one
measured here, and {implied}.</p>
<p>{far['retired']} of {far['entries']} of these starts retired, against
{retired_share:.0%} in the panel.</p>

<h2>Track by track</h2>
{_img(figures['circuits'])}
<table><tr><th>circuit</th><th>entries</th><th>moved</th><th>slope</th>
<th>error</th><th>shrunk</th></tr>{_circuit_rows(by_track, labels)}</table>
<p>Shrinkage keeps {by_track['circuits'][0]['factor']:.0%} of the spread
between circuits and attributes the rest to sampling noise. Jointly the
{by_track['joint']['terms']} deviations give F =
{by_track['joint']['F']:.2f}, p = {by_track['joint']['p']:.3f}.</p>

<h2>Where the penalties happen is a choice</h2>
<p>A team that must change a power unit decides <em>when</em>, and it
picks a weekend where starting further back is cheap. So the variation
this entire project is identified from is not spread evenly over the
calendar.</p>
<table><tr><th>circuit</th><th>entries</th><th>moved</th>
<th>share moved</th></tr>
{"".join(f"<tr><td>{labels.get(one['circuit'], one['circuit'])}</td><td>{one['entries']}</td><td>{one['moved']}</td><td>{one['share']:.0%}</td></tr>" for one in busiest)}
<tr><td colspan="4" style="text-align:center;color:#5b6472">&middot; &middot; &middot;</td></tr>
{"".join(f"<tr><td>{labels.get(one['circuit'], one['circuit'])}</td><td>{one['entries']}</td><td>{one['moved']}</td><td>{one['share']:.0%}</td></tr>" for one in quietest)}
</table>
<div class="note">The weighting is not where this bites: pooled over the
eligible circuits the slope is {by_track['pooled']:+.3f} and the
unweighted mean of their own slopes is {by_track['unweighted']:+.3f},
near enough identical, so the busy circuits are not dragging the pooled
number about. What bites is the {len(by_track['left out'])} circuits that
cannot be fitted at all - Monaco among them, where a slot should be worth
most of anywhere. They are missing rather than down-weighted, and nothing
here can say what a slot was worth at them. Every number on this page is
an answer to "what was a slot worth where penalties were actually taken",
which is the right question for pricing a penalty and a narrower one than
pricing a grid slot.</div>

<h2>What it cost</h2>
<p>{priced['entries']} demoted entries reached the flag inside the
{priced['support']}-slot support, {priced['slots']:,} slots between them,
with {priced['refused, beyond the support']} moved further and refused
rather than extrapolated, for
<b>{priced['points']:.1f} championship points</b> -
{priced['points each']:.2f} an entry, with only
{priced['entries that lost points']} of them losing anything at all,
because most penalties land outside the points.</p>
<div class="note">This is what the penalised cars gave up, not what the
grid rearranged. Un-penalising one car moves every car it passes, and
those counterfactuals are not computed, so the gains on the other side of
these losses are missing.</div>

<h2>What this does not do</h2>
<p>It is a local, linear average over the shifts that happened, nearly all
of them between one and ten slots, and the pit-lane check above is the only
evidence about anything larger. It cannot say <em>why</em> a car was moved,
because the feed records no reason: gearbox, power unit, impeding and
blocking are one column. Sprint weekends are dropped entirely. And the
promoted-only estimate, the one with no contamination in it, is too
imprecise to settle the question on its own.</p>

<p class="sub">Generated by <code>run.py</code>. Qualifying, grid and race
results from the Jolpica mirror of the Ergast schema.</p>
</body></html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
