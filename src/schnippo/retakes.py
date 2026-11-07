"""Retake candidates: segments that are probably attempts at the same content. Hints, not decisions.

Edge between two segments of the same clip if, within ``window_s``:
  * LCS of normalised word sequences >= ``min_lcs`` and LCS / shorter length >= ``min_sim``, or
  * both have the same best script line with score >= ``script_min`` (when a script is loaded).
Groups = connected components (may chain unrelated segments – Claude corrects).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .segments import Segment

NUM = {"null": "0", "eins": "1", "ein": "1", "eine": "1", "zwei": "2", "drei": "3", "vier": "4", "fünf": "5", "sechs": "6",
       "sieben": "7", "acht": "8", "neun": "9", "zehn": "10", "zwanzig": "20", "dreißig": "30", "vierzig": "40",
       "fünfzig": "50", "sechzig": "60", "siebzig": "70", "achtzig": "80", "neunzig": "90", "hundert": "100"}


def tokens(text: str) -> list[str]:
    out = []
    for w in unicodedata.normalize("NFC", text.lower()).split():
        w = re.sub(r"[^\wäöüß]+", "", w)
        if w:
            out.append(NUM.get(w, w) if w not in ("ein", "eine") else w)  # keep articles as words
    return out


def lcs(x: list[str], y: list[str]) -> int:
    prev = [0] * (len(y) + 1)
    for a in x:
        cur = [0]
        for j, b in enumerate(y):
            cur.append(prev[j] + 1 if a == b else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


@dataclass
class Edge:
    a: str
    b: str
    score: float
    why: str  # "text" | "script"


@dataclass
class Group:
    id: str
    members: list[str]
    score: float
    edges: list[Edge] = field(default_factory=list)


def find(segs: list[Segment], window_s: float = 90.0, min_lcs: int = 3, min_sim: float = 0.5,
         script_min: float = 0.7) -> tuple[list[Edge], list[Group]]:
    toks = {s.id: tokens(s.plain) for s in segs}
    edges: list[Edge] = []
    for i, s in enumerate(segs):
        for t in segs[i + 1:]:
            if t.start_s - s.end_s > window_s:
                break
            x, y = toks[s.id], toks[t.id]
            best = None
            if x and y:
                l = lcs(x, y)
                sim = l / min(len(x), len(y))
                if l >= min_lcs and sim >= min_sim:
                    best = Edge(s.id, t.id, round(sim, 2), "text")
            if best is None and s.script and t.script and s.script[0][0] == t.script[0][0] \
                    and min(s.script[0][1], t.script[0][1]) >= script_min:
                best = Edge(s.id, t.id, round(min(s.script[0][1], t.script[0][1]), 2), "script")
            if best:
                edges.append(best)
    # connected components
    parent = {s.id: s.id for s in segs}

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        parent[root(e.a)] = root(e.b)
    comps: dict[str, list[str]] = {}
    for s in segs:
        comps.setdefault(root(s.id), []).append(s.id)
    groups = []
    for members in sorted((m for m in comps.values() if len(m) > 1), key=lambda m: m[0]):
        es = [e for e in edges if e.a in members]
        groups.append(Group(id=f"G{len(groups) + 1:02d}", members=members,
                            score=round(sum(e.score for e in es) / len(es), 2), edges=es))
    return edges, groups


def evaluate(segs: list[Segment], edges: list[Edge], groups: list[Group], gt: list[dict]) -> dict:
    """Recall/precision against ground-truth relations given as word ranges ({"a": [w, w], "b": [w, w]})."""
    def seg_of(wid: str) -> str:
        n = int(wid[1:])
        return next(s.id for s in segs if s.word_range()[0] <= n <= s.word_range()[1])

    rel = [(seg_of(r["a"][0]), seg_of(r["b"][0])) for r in gt]
    gid = {m: g.id for g in groups for m in g.members}
    eset = {frozenset((e.a, e.b)) for e in edges}
    # ground-truth clusters (transitive closure)
    cl: dict[str, set] = {}
    for a, b in rel:
        merged = cl.get(a, {a}) | cl.get(b, {b})
        for m in merged:
            cl[m] = merged
    same = lambda a, b: a in cl and b in cl[a]
    pairs_in_groups = [(a, b) for g in groups for i, a in enumerate(g.members) for b in g.members[i + 1:]]
    found_edge = [frozenset(r) in eset or r[0] == r[1] for r in rel]
    found_group = [r[0] == r[1] or (r[0] in gid and gid.get(r[0]) == gid.get(r[1])) for r in rel]
    return {
        "relations": len(rel),
        "recall_edge": round(sum(found_edge) / len(rel), 2),
        "recall_group": round(sum(found_group) / len(rel), 2),
        "precision_edge": round(sum(same(e.a, e.b) for e in edges) / max(1, len(edges)), 2),
        "precision_group_pairs": round(sum(same(a, b) for a, b in pairs_in_groups) / max(1, len(pairs_in_groups)), 2),
        "missed": [gt[i]["n"] for i, f in enumerate(found_group) if not f],
        "false_edges": [(e.a, e.b) for e in edges if not same(e.a, e.b)],
        "edges": len(edges),
    }
