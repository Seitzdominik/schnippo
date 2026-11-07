"""Sense check of the finished cut (Phase 8.5, step 4): hear it again.

The sound of the finished timeline is transcribed once more. What was heard is compared with what the cutlist expects:
- at every seam (±2 words): swallowed, doubled or mangled words = "unsaubere Naht" (an objective test of the cut points),
- the text as a whole goes to Claude, who reads it like a viewer (broken sentences, references without a referent,
  unfinished thoughts, jumps, contradictions).
Heard words are cached per piece (clip + frames): after revise only changed pieces are transcribed again. The word times
also serve export_transcript (more exact in the finished cut than source times mapped through the pieces).
"""

from __future__ import annotations

import difflib
import re

_NORM = re.compile(r"[^\wäöüß]+")
SAME = 0.72  # two words with this similarity are the same word (recognition spelling, not a seam problem)


def norm(t: str) -> str:
    return _NORM.sub("", t.lower())


def piece_key(p) -> str:
    return f"{p.clip}:{p.start_frame}-{p.end_frame}"


def recs(pieces: list) -> list[int]:
    out, r = [], 0
    for p in pieces:
        out.append(r)
        r += p.frames
    return out


def split_by_piece(tokens: list[dict], pieces: list, fps: float) -> dict[str, list[dict]]:
    """Heard words (timeline seconds) → per piece key, times relative to the piece start (assigned by the word's middle)."""
    out: dict[str, list[dict]] = {piece_key(p): [] for p in pieces}
    rs = recs(pieces)
    k = 0
    for t in sorted(tokens, key=lambda x: x["s"]):
        mid = (t["s"] + t["e"]) / 2
        while k + 1 < len(pieces) and mid * fps >= rs[k + 1]:
            k += 1
        base = rs[k] / fps
        out[piece_key(pieces[k])].append({"text": t["text"], "s": round(t["s"] - base, 3), "e": round(t["e"] - base, 3),
                                          "c": t.get("c")})
    return out


def join_pieces(cache: dict, pieces: list, fps: float) -> list[dict]:
    """Back to timeline seconds, in timeline order."""
    out = []
    for p, r in zip(pieces, recs(pieces)):
        for t in cache.get(piece_key(p), []):
            out.append({"text": t["text"], "s": round(r / fps + t["s"], 3), "e": round(r / fps + t["e"], 3), "c": t.get("c")})
    return out


def missing_regions(cache: dict, pieces: list, fps: float, pad_s: float = 0.6) -> list[tuple[float, float]]:
    """Timeline seconds that still need transcribing (pieces not in the cache), merged, with padding for context."""
    rs = recs(pieces)
    total = (rs[-1] + pieces[-1].frames) / fps if pieces else 0.0
    spans = [(max(0.0, r / fps - pad_s), min(total, (r + p.frames) / fps + pad_s))
             for p, r in zip(pieces, rs) if piece_key(p) not in cache]
    merged: list[list[float]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def align(expected: list[str], heard: list[str]) -> list[tuple[str, int, int, int, int]]:
    a, b = [norm(x) for x in expected], [norm(x) for x in heard]
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()


def word_map(expected: list[dict], heard: list[dict]) -> dict[int, int]:
    """Expected index → heard index for words heard as (nearly) the same."""
    out = {}
    for op, i1, i2, j1, j2 in align([w["text"] for w in expected], [h["text"] for h in heard]):
        if op == "equal":
            out.update({i1 + k: j1 + k for k in range(i2 - i1)})
        elif op == "replace" and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                if _similar(expected[i1 + k]["text"], heard[j1 + k]["text"]):
                    out[i1 + k] = j1 + k
    return out


def _similar(x: str, y: str) -> bool:
    return difflib.SequenceMatcher(a=norm(x), b=norm(y), autojunk=False).ratio() >= SAME


def seams(expected: list[dict], heard: list[dict], cuts: list[float], window: int = 2) -> tuple[list[dict], dict]:
    """expected: words with timeline seconds "s"/"e"; cuts: timeline seconds of the cuts. Differences within ±window words of
    a cut are seam problems; differences elsewhere only measure how much the two transcriptions disagree anyway."""
    ops = align([w["text"] for w in expected], [h["text"] for h in heard])
    near: set[int] = set()
    for c in cuts:
        i = next((k for k, w in enumerate(expected) if w["s"] >= c - 0.02), len(expected))  # first word after the cut
        near.update(range(max(0, i - window), min(len(expected), i + window)))
    found, far = [], 0
    for op, i1, i2, j1, j2 in ops:
        if op == "equal":
            continue
        exp = " ".join(w["text"] for w in expected[i1:i2])
        hrd = " ".join(h["text"] for h in heard[j1:j2])
        if op == "replace" and _similar(exp, hrd):
            continue
        hit = any(k in near for k in range(i1, max(i2, i1 + 1)))
        if not hit:
            far += max(i2 - i1, j2 - j1)
            continue
        t = expected[min(i1, len(expected) - 1)]["s"] if expected else 0.0
        if op == "delete":
            kind = "verschluckt"
        elif op == "insert":
            prev = expected[i1 - 1]["text"] if i1 else ""
            nxt = expected[i1]["text"] if i1 < len(expected) else ""
            kind = "verdoppelt" if any(_similar(h["text"], prev) or _similar(h["text"], nxt) for h in heard[j1:j2]) else "Zusatzlaut"
        else:
            kind = "verstümmelt"
        cut = min(cuts, key=lambda c: abs(c - t)) if cuts else t
        found.append({"t": round(t, 2), "cut": round(cut, 2), "kind": kind, "expected": exp, "heard": hrd})
    stats = {"words": len(expected), "heard": len(heard), "elsewhere": far, "cuts": len(cuts)}
    return found, stats


def sections(heard: list[dict], every_s: float = 60.0) -> list[str]:
    """The heard text in blocks with time stamps, for reading like a viewer."""
    def mmss(s):
        return f"{int(s // 60)}:{int(s % 60):02d}"
    out, cur, t0 = [], [], 0.0
    for h in heard:
        if not cur:
            t0 = h["s"]
        cur.append(h["text"])
        if h["s"] - t0 >= every_s and re.search(r"[.!?…]$", h["text"]):
            out.append(f"[{mmss(t0)}] " + " ".join(cur))
            cur = []
    if cur:
        out.append(f"[{mmss(t0)}] " + " ".join(cur))
    return out
