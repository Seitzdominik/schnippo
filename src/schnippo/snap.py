"""Overlay/graphic edges vs. cuts in V1 (deterministic).

An edge close to a cut makes the picture jump: a few frames of face flash up before/after the still, or the cut under it
shows right next to the overlay edge. Rules:
  * snap: an edge closer than `thr` frames to a cut is moved onto that cut (extend or shorten);
  * no slivers: no visible A-roll piece shorter than `sliver` frames between an edge and the neighbouring cut;
  * covered jump cuts: an edge never lands 1…margin frames next to a cut;
  * duration stays within [dmin, dmax] – else the other cut edge / the whole clip, else a warning.
Candidates for every edge: the original position and all cuts within `reach`; the cheapest valid pair wins (fewest
moved frames, edges on cuts preferred, whole clips covered preferred).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Snap:
    start: int
    end: int
    moved: tuple[int, int]  # frames moved (start, end); + = later
    on_cut: tuple[bool, bool]
    gaps: dict = field(default_factory=dict)  # distances to the nearest cuts before/after each edge
    warnings: list[str] = field(default_factory=list)


def _nearest(x: int, cuts: list[int]) -> tuple[int | None, int | None]:
    before = max((c for c in cuts if c <= x), default=None)
    after = min((c for c in cuts if c >= x), default=None)
    return before, after


def edge_gaps(a: int, b: int, cuts: list[int]) -> dict:
    sb, sa = _nearest(a, cuts)
    eb, ea = _nearest(b, cuts)
    return {"start_after_cut": None if sb is None else a - sb, "start_before_cut": None if sa is None else sa - a,
            "end_after_cut": None if eb is None else b - eb, "end_before_cut": None if ea is None else ea - b}


def _problems(a: int, b: int, cuts: list[int], sliver: int, margin: int) -> list[str]:
    out = []
    for edge, name in ((a, "Anfang"), (b, "Ende")):
        if edge in cuts:
            continue
        before, after = _nearest(edge, cuts)
        # visible A-roll next to the edge: before the start, after the end
        vis = (edge - before) if (name == "Anfang" and before is not None) else (after - edge) if after is not None else None
        if vis is not None and 0 < vis < sliver:
            out.append(f"{name}: {vis} F A-Roll-Splitter bis zum Schnitt")
        hidden = (after - edge) if name == "Anfang" and after is not None else (edge - before) if before is not None else None
        if hidden is not None and 0 < hidden <= margin and ((name == "Anfang" and after < b) or (name == "Ende" and before > a)):
            out.append(f"{name}: nur {hidden} F neben dem überdeckten Schnitt")
    return out


def snap_span(a: int, b: int, cuts: list[int], thr: int, sliver: int, margin: int, dmin: int, dmax: int, reach: int | None = None,
              total: int | None = None) -> Snap:
    cuts = sorted(set(cuts))
    reach = reach if reach is not None else max(thr, sliver) * 2
    total = total if total is not None else (cuts[-1] if cuts else b)

    def cands(x: int) -> list[int]:
        near = [c for c in cuts if abs(c - x) <= reach]
        snapped = [c for c in near if abs(c - x) <= thr]
        return sorted(set([x] + near)), set(snapped)

    sc, s_snap = cands(a)
    ec, e_snap = cands(b)
    # fallbacks when the span would get too short/long: the other cut edge (whole clip) or the plain minimum length
    if dmax < 10**8:
        ec = sorted(set(ec) | {c for c in cuts if a + dmin <= c <= a + dmax} | {a + dmin})
        sc = sorted(set(sc) | {c for c in cuts if b - dmax <= c <= b - dmin} | {max(0, b - dmin)})
    else:
        ec = sorted(set(ec) | {min(c for c in cuts + [10**9] if c >= a + dmin)} | {a + dmin})
    best = None
    for s in sc:
        for e in ec:
            if e <= s or s < 0 or e > total:
                continue
            d = e - s
            probs = _problems(s, e, cuts, sliver, margin)
            cost = (abs(s - a) + abs(e - b)) * 1.0
            # an edge within thr of a cut that is NOT moved onto it counts like a problem
            if a in sc and s == a and s_snap and a not in cuts:
                cost += 400
            if e == b and e_snap and b not in cuts:
                cost += 400
            cost += 1000 * len(probs)
            if d < dmin:
                cost += 600 + 10 * (dmin - d)
            if d > dmax:
                cost += 600 + 10 * (d - dmax)
            cost -= 5 * ((s in cuts) + (e in cuts))
            if best is None or cost < best[0]:
                best = (cost, s, e, probs)
    if best is None:
        return Snap(a, b, (0, 0), (a in cuts, b in cuts), edge_gaps(a, b, cuts), ["kein gültiger Zeitraum"])
    _, s, e, probs = best
    warn = list(probs)
    if e - s < dmin:
        warn.append(f"nach dem Einrasten {e - s} F < Minimum {dmin} F")
    if e - s > dmax:
        warn.append(f"nach dem Einrasten {e - s} F > Maximum {dmax} F")
    return Snap(s, e, (s - a, e - b), (s in cuts, e in cuts), edge_gaps(s, e, cuts), warn)


def describe(sn: Snap, fps: float) -> str:
    g = sn.gaps
    f = lambda v: "–" if v is None else (f"{v} F" if v else "0 (auf dem Schnitt)")
    mv = []
    for (d, name) in zip(sn.moved, ("Anfang", "Ende")):
        if d:
            mv.append(f"{name} {d:+d} F ({d / fps:+.2f} s)")
    return (f"Anfang: {f(g['start_after_cut'])} nach / {f(g['start_before_cut'])} vor Schnitt · "
            f"Ende: {f(g['end_after_cut'])} nach / {f(g['end_before_cut'])} vor Schnitt · "
            + ("eingerastet: " + ", ".join(mv) if mv else "unverändert"))
