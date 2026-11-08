"""Project glossary (Phase 9, step 0): names of people, companies, brands, places, technical terms, e-mail and web
addresses in their correct spelling. Proper names are what the transcription gets wrong (MOC AG / Moz AG / CU).

File `glossar.txt` in the material folder, one term per line, `#` = comment, optional known mis-hearings after `=`:

    MOC AG = Moz AG, CU
    Raum Inn-Isar
    support@mondoria.de

Used for: (a) Gladia custom vocabulary – only these names, never fillers (Phase 1: fillers in the vocabulary changed content
words); (b) correction proposals for transcript, graphics and subtitle export; (c) names on graphics need a confirmed term.
"""

from __future__ import annotations

from .platforms import read_text
import difflib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

FILE = "glossar.txt"
_N = re.compile(r"[^\wäöüß]+")
_EDGE = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)
MIN_RATIO, MIN_RATIO_SHORT, MIN_RATIO_ADDRESS = 0.8, 0.86, 0.62


def norm(t: str) -> str:
    return _N.sub("", t.lower())


@dataclass
class Term:
    value: str
    aliases: list[str] = field(default_factory=list)

    @property
    def address(self) -> bool:
        return "@" in self.value or bool(re.search(r"\.\w{2,}$", self.value))


def parse(lines: list[str]) -> list[Term]:
    out, seen = [], set()
    for ln in lines:
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        value, _, rest = ln.partition("=")
        value = value.strip()
        if value and norm(value) not in seen:
            seen.add(norm(value))
            out.append(Term(value, [a.strip() for a in rest.split(",") if a.strip()]))
    return out


def load(folder: Path | None, stored: list[str] | None = None) -> list[Term]:
    """The file in the material folder plus terms given in the chat (set_glossary)."""
    lines = list(stored or [])
    f = Path(folder) / FILE if folder else None
    if f is not None and f.is_file():
        lines = read_text(f).splitlines() + lines
    return parse(lines)


def vocabulary(terms: list[Term]) -> list[str]:
    """Gladia custom vocabulary: the names only. Addresses as their distinctive word (mondoria), not as a whole."""
    out = []
    for t in terms:
        v = t.value
        if "@" in v:
            v = v.split("@", 1)[1].rsplit(".", 1)[0]
        elif t.address:
            v = v.rsplit(".", 1)[0].removeprefix("www.")
        if v not in out:
            out.append(v)
    return out


def _with_edges(word: str, value: str) -> str:
    """Keep the punctuation that followed the recognised word ("Moz AG," → "MOC AG,")."""
    tail = _EDGE.match(word).group(3)
    return value + (tail if tail and not value.endswith(tail) and tail[0] in ",;:!?" else "")


def find(words: list[dict], terms: list[Term]) -> list[dict]:
    """Spots in a word list ({"ref", "text"}) that look like a glossary term but are spelled differently. Result per spot:
    refs, text, value, score, sure (known alias or nearly identical)."""
    hits, used = [], set()
    cand = []
    for t in terms:
        target = norm(t.value)
        n = len(t.value.split())
        forms = [(norm(a), True) for a in t.aliases] + [(target, False)]
        for size in sorted({max(1, n - 1), n, n + 1}, reverse=True):
            for i in range(0, max(0, len(words) - size) + 1):
                win = words[i:i + size]
                if t.address and size > n and any("@" in w["text"] for w in win):  # a heard address is one word
                    continue
                text = " ".join(w["text"] for w in win)
                j = norm(text)
                if not j or target in j or j in target:  # already correct (inside a longer window, or a part of the term)
                    continue
                for form, alias in forms:
                    if not form:
                        continue
                    score = 1.0 if j == form else difflib.SequenceMatcher(a=j, b=form, autojunk=False).ratio()
                    need = MIN_RATIO_ADDRESS if t.address and "@" in text else MIN_RATIO_SHORT if len(form) < 6 else MIN_RATIO
                    if (alias and score == 1.0) or (not alias and score >= need):
                        cand.append((score, i, size, t, text, alias))
    for score, i, size, t, text, alias in sorted(cand, key=lambda c: (-c[0], -c[2], c[1])):
        span = set(range(i, i + size))
        if span & used:
            continue
        used |= span
        hits.append({"refs": [w["ref"] for w in words[i:i + size]], "text": text, "value": t.value, "score": round(score, 2),
                     "sure": alias or score >= 0.9, "t": words[i].get("t")})
    return sorted(hits, key=lambda h: h["refs"][0])


def corrections(hit: dict, last_text: str) -> dict[str, str]:
    """First word takes the term, the rest of the span disappears."""
    out = {r: "" for r in hit["refs"]}
    out[hit["refs"][0]] = _with_edges(last_text, hit["value"])
    return out


def check_text(text: str, terms: list[Term]) -> list[str]:
    """Text on a graphic: a word that looks like a term but is spelled differently."""
    words = [{"ref": str(k), "text": w} for k, w in enumerate(str(text).split())]
    return [f"„{h['text']}“ → „{h['value']}“" for h in find(words, terms)]


def known(name: str, terms: list[Term]) -> bool:
    """Is this name confirmed? Whole term, or part of one (Max in "Max Muster")."""
    n = norm(name)
    return any(n == norm(t.value) or n in [norm(x) for x in t.value.split()] for t in terms)


COMMON = {"was", "wie", "wer", "wo", "wann", "warum", "das", "die", "der", "dem", "den", "ich", "sie", "er", "es", "wir", "ihr", "und",
          "aber", "also", "dann", "wenn", "hier", "da", "ja", "nein", "okay", "ok", "so", "nun", "ne", "gut"}


def _variant(a: str, b: str) -> bool:
    """Two spellings of the same name? Not inflection or compounds (Boot/Boote, Schleim/Schleimhaut) – one word contains the
    other – and not two different short words (Mal/Mai): those need one changed letter and a mixed-case or short brand look."""
    if a.startswith(b) or b.startswith(a) or a[:1] != b[:1]:
        return False
    r = difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio()
    return r >= 0.7 if min(len(a), len(b)) >= 5 else (len(a) == len(b) and r >= 0.6)


def unsure_names(tokens: list, terms: list[Term], limit: int = 8) -> list[dict]:
    """Proper names worth asking about instead of guessing. German capitalises every noun, so capitals alone say little.
    Signals: spellings that vary with low confidence (MOC / Moz, Segelwerk / SegelWerft), or a capitalised word inside a
    sentence with very low confidence. tokens: Word objects of all A-roll clips."""
    ok = {norm(x) for t in terms for x in [t.value, *t.value.split(), *t.aliases]}
    count, conf, spelled = Counter(), {}, {}
    prev_end = True
    for w in tokens:
        raw = w.text.strip()
        core = _EDGE.match(raw).group(2)
        k = norm(core)
        capital = core[:1].isupper() and not prev_end
        prev_end = bool(re.search(r"[.!?…:]$", raw))
        if len(k) < 3 or k in ok or k in COMMON or not capital:
            continue
        count[k] += 1
        spelled.setdefault(k, core)
        conf.setdefault(k, []).append(w.confidence if w.confidence is not None else 1.0)
    keys = sorted(count, key=lambda k: -count[k])
    groups, seen = [], set()
    for a in keys:
        if a in seen:
            continue
        same = [b for b in keys if b != a and b not in seen and _variant(a, b) and min(conf[a] + conf[b]) < 0.6]
        low = min(conf[a]) < 0.45 and sum(conf[a]) / len(conf[a]) < 0.5
        if same or low:
            seen |= {a, *same}
            groups.append({"spellings": [spelled[x] for x in [a, *same]], "count": sum(count[x] for x in [a, *same]),
                           "confidence": round(min(min(conf[x]) for x in [a, *same]), 2), "varies": bool(same)})
    groups.sort(key=lambda g: (not g["varies"], g["confidence"]))
    return groups[:limit]
