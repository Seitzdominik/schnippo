"""Natural word edges from the signal (Phase 8.5, step 3). Gladia's word times sit on the voiced part (±30–60 ms, long
words up to 260 ms too early), so quiet decays and consonant onsets would be cut off. Everything here reads the 10-ms
level envelope of acoustic.py:

- decay_end: follow the level after a word until it falls below noise floor + 6 dB (capped, stops before the next word).
- onset_start: go back from a word start until the level was at the floor (plosive/fricative onset), max 120 ms.
- quiet_at / nearest_quiet: an edge is clean when the level in the last/first 10 ms is close to the noise floor.
"""

from __future__ import annotations

import math

DECAY_DB = 6.0  # "the word has ended" = level below noise floor + this
ONSET_MAX_S = 0.12
GUARD_S = 0.02  # never closer than this to the next/previous word


def _env(ac, t: float) -> float:
    i = min(max(int(round(t * 100)), 0), len(ac.env_db) - 1)
    return float(ac.env_db[i])


def decay_end(ac, t0: float, limit: float, rise_db: float = DECAY_DB) -> float:
    """Time at which the sound of a word ending at t0 has faded (two 10-ms frames below the threshold), at most `limit`."""
    thr = ac.floor_db + rise_db
    t = t0
    while t < limit:
        if _env(ac, t) < thr and _env(ac, t + 0.01) < thr:
            return t
        t += 0.01
    return max(limit, t0)


def onset_start(ac, t0: float, limit: float, rise_db: float = DECAY_DB) -> float:
    """Where the sound of a word starting (per ASR) at t0 really begins, not before `limit`."""
    thr = ac.floor_db + rise_db
    t = t0
    while t > limit:
        if _env(ac, t) < thr and _env(ac, t - 0.01) < thr:
            return t
        t -= 0.01
    return min(limit, t0)


def edge_level(ac, frame: int, fps: float, side: str) -> float:
    """Level (dBFS) in the 10 ms inside a piece at its edge: side "end" = before the frame boundary, "start" = after."""
    t = frame / fps
    return _env(ac, t - 0.005) if side == "end" else _env(ac, t + 0.005)


def is_quiet(ac, frame: int, fps: float, side: str, edge_db: float) -> bool:
    return edge_level(ac, frame, fps, side) <= ac.floor_db + edge_db


def nearest_quiet(ac, frame: int, fps: float, side: str, edge_db: float, lo: int, hi: int) -> int | None:
    """Nearest frame boundary in [lo, hi] with a clean edge; later wins a tie for ends, earlier for starts."""
    if lo > hi:
        return None
    order = sorted(range(lo, hi + 1), key=lambda f: (abs(f - frame), -f if side == "end" else f))
    return next((f for f in order if is_quiet(ac, f, fps, side, edge_db)), None)


def quietest(ac, frame: int, fps: float, side: str, lo: int, hi: int, gain_db: float = 3.0) -> int | None:
    """No clean edge in reach: the quietest frame boundary in [lo, hi] if it beats the current one by gain_db."""
    if lo > hi:
        return None
    best = min(range(lo, hi + 1), key=lambda f: edge_level(ac, f, fps, side))
    return best if edge_level(ac, best, fps, side) <= edge_level(ac, frame, fps, side) - gain_db else None


STRETCH_MAX_S = 0.28  # voiced sound attached to a word up to this long = stretched word, not a filler
ATTACHED_S = 0.03  # "attached": no gap to the word
TAIL_OF_LONG_S = 0.10  # a longer attached sound stays a filler, but the word keeps this much of it


def unclamp(entries: list, ac) -> list:
    """The analysis shortens word edges that seem stretched over silence (activity threshold = noise floor + 25 dB). On a
    quiet recording soft syllables fall below that threshold: "kurzfristige" kept 120 ms, "weiterführen?" 60 ms (Phase 8.5:
    46 of 63 shortened edges cut into real sound). For cutting, the edge goes back as far as the level really stays above
    the noise floor, at most to Gladia's original time."""
    out = []
    for e in entries:
        for fl in e.flags:
            if fl.startswith("end_clamped:"):
                e = e.model_copy(update={"end_s": round(decay_end(ac, e.end_s, float(fl.split(":")[1])), 3)})
            elif fl.startswith("start_clamped:"):
                e = e.model_copy(update={"start_s": round(onset_start(ac, e.start_s, float(fl.split(":")[1])), 3)})
        out.append(e)
    return out


def merge_stretches(entries: list) -> list:
    """Gladia's word times sit on the voiced part: a stretched end ("Rezepte-e") shows up as a {?} directly after the
    word (Phase 8.5: 90 of 143 {?} had no gap and no level dip). Short ones become part of the word, at its end or – when
    attached to the following word – at its start. Longer ones stay fillers, the word keeps 100 ms of them."""
    out = list(entries)
    words = [k for k, e in enumerate(out) if e.id[0] == "w"]
    drop = set()
    for k, e in enumerate(out):
        if e.kind != "filler" or "inferred" not in e.flags:
            continue
        prev = max((i for i in words if i < k), default=None)
        nxt = min((i for i in words if i > k), default=None)
        dur = e.end_s - e.start_s
        if prev is not None and e.start_s - out[prev].end_s <= ATTACHED_S:
            if dur <= STRETCH_MAX_S:
                out[prev] = out[prev].model_copy(update={"end_s": e.end_s})
                drop.add(k)
            else:
                cut = e.start_s + TAIL_OF_LONG_S
                out[prev] = out[prev].model_copy(update={"end_s": cut})
                out[k] = e.model_copy(update={"start_s": cut})
        elif nxt is not None and out[nxt].start_s - e.end_s <= ATTACHED_S and dur <= STRETCH_MAX_S:
            out[nxt] = out[nxt].model_copy(update={"start_s": e.start_s})
            drop.add(k)
    return [e for k, e in enumerate(out) if k not in drop]


def frames(t: float, fps: float, up: bool) -> int:
    return math.ceil(t * fps - 1e-9) if up else math.floor(t * fps + 1e-9)
