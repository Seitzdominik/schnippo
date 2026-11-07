"""Compact, token-lean transcript text for Claude.

Example::

    c01 take1.mp4 | 0:00.00–0:41.20 | 29.97fps | gladia/de | 98 Wörter · 3 Füllw. (+1 per Lücke) · 7 Pausen
    Zahl = Wort-ID (17 → c01:w0017). {äh} Füllwort · {?0.3s} Sprache ohne Wort · <0.9s> Pause · ~ weiches Füllwort · * Wiederholung · ^ Neuanfang-Kandidat
    @0:00.42 1 Hallo 2 und 3 willkommen 4 zu 5 {äh} 6 meinem 7 Kanal. <0.9s>
    @0:03.10 8 Heute^ 9 zeige^ ...
    Hinweise:
    ^ w8–w11 → w13–w16 „Heute zeige ich euch“ wiederholt
"""

from __future__ import annotations

import re

from .models import AnalyzedTranscript, Clip, Word

LEGEND = ("Zahl = Wort-ID (17 → {cid}:w0017). {{äh}} Füllwort · {{?0.3s}} stimmhaft ohne Wort (äh/hm?) · {{breath}} Atmer · <0.9s> Pause · "
          "~ weiches Füllwort · * Wiederholung · ^ Neuanfang-Kandidat")
MAX_LINE_WORDS = 16
SENTENCE_END = re.compile(r"[.!?…]$")


def ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}" if h >= 1 else f"{int(m)}:{s:05.2f}"


def parse_word_ref(ref: str | int | None) -> int | None:
    if ref is None or ref == "":
        return None
    if isinstance(ref, int):
        return ref
    m = re.fullmatch(r"(?:c\d+:)?w?0*(\d+)", str(ref).strip(), re.I)
    if not m:
        raise ValueError(f"invalid word reference {ref!r} (expected e.g. w0017 or 17)")
    return int(m.group(1))


def _num(e: Word) -> int:
    return int(re.match(r"[wpub](\d+)", e.id).group(1))


def _render(e: Word) -> str:
    if e.kind == "pause":
        return f"<{e.text}>"
    if e.kind == "breath":
        return "{breath}"
    if "inferred" in e.flags:
        return f"{{?{e.end_s - e.start_s:.1f}s}}"
    n = _num(e)
    if e.kind == "filler":
        return f"{n} {{{e.text}}}"
    marks = ("~" if "soft_filler" in e.flags else "") + ("*" if "repeat" in e.flags else "") + (
        "^" if "restart_candidate" in e.flags else "")
    return f"{n} {e.text}{marks}"


def format_transcript(clip: Clip, at: AnalyzedTranscript, from_word: int | None = None, to_word: int | None = None,
                      with_header: bool = True) -> str:
    lo = from_word or 1
    hi = to_word or 10**9
    sel: list[Word] = []
    for e in at.entries:
        n = _num(e)
        if e.id[0] == "w":
            if lo <= n <= hi:
                sel.append(e)
        elif lo <= n + 1 and n < hi:  # gap entry after word n lies inside the range
            if not (n == 0 and lo > 1):
                sel.append(e)
    out: list[str] = []
    if with_header:
        st = at.stats
        span = f"{ts(sel[0].start_s)}–{ts(sel[-1].end_s)}" if sel else "leer"
        rng = "" if from_word is None and to_word is None else f" | Ausschnitt w{lo:04d}–" + (f"w{hi:04d}" if to_word else "Ende")
        out.append(f"{clip.id} {clip.name} | {span} | {clip.fps:.3f}".rstrip("0").rstrip(".") + "fps"
                   + (" VFR" if clip.vfr else "") + f" | {at.provider}/{at.language} | {st.get('words', 0)} Wörter · "
                   f"{st.get('fillers_asr', 0)} Füllw. (+{st.get('fillers_inferred', 0)} per Lücke) · {st.get('pauses', 0)} Pausen{rng}")
        out.append(LEGEND.format(cid=clip.id))
    line: list[str] = []
    line_start: float | None = None
    nwords = 0

    def flush():
        nonlocal line, line_start, nwords
        if line:
            out.append(f"@{ts(line_start or 0)} " + " ".join(line))
        line, line_start, nwords = [], None, 0

    for e in sel:
        if e.kind == "pause" and line == [] and out and not out[-1].startswith("Zahl"):
            out[-1] += f" <{e.text}>"  # attach pause to previous line
            continue
        if line_start is None:
            line_start = e.start_s
        line.append(_render(e))
        if e.kind != "pause":
            nwords += 1
        if e.kind == "pause" or nwords >= MAX_LINE_WORDS or (nwords >= 8 and SENTENCE_END.search(e.text)):
            flush()
    flush()

    hints = [f for f in at.findings if f.type != "long_pause" and _in_range(f.first[0], lo, hi)]
    if with_header and hints:
        out.append("Hinweise:")
        sym = {"repeat": "*", "restart_candidate": "^", "unrecognized_speech": "?"}
        for f in hints:
            a, b = f.first
            span = f"{a}" if a == b else f"{a}–{b}"
            if f.second:
                c, d = f.second
                span += f" → {c}" if c == d else f" → {c}–{d}"
            out.append(f"{sym.get(f.type, '-')} {span} {f.note}")
    return "\n".join(out)


def _in_range(entry_id: str, lo: int, hi: int) -> bool:
    n = int(re.match(r"[wpub](\d+)", entry_id).group(1))
    return lo <= (n if entry_id[0] == "w" else n + 1) <= hi
