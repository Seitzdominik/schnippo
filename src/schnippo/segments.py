"""Deterministic segmentation of an analysed transcript into utterances.

Boundaries: gap between two ASR words >= ``segment_pause_s`` (default 0.7 s) or sentence punctuation.
Segment IDs (``s001`` …) are stable for a given transcript + parameters, like word IDs.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .config import Config
from .models import AnalyzedTranscript, Word

SENT_END = re.compile(r"[.!?…]$")


class Segment(BaseModel):
    id: str  # s001
    clip_id: str
    from_word: str
    to_word: str
    start_s: float
    end_s: float
    text: str  # with inline {?} for voiced gaps, fillers in {}
    plain: str  # words only (for matching)
    n_words: int
    pause_before_s: float
    pause_after_s: float
    flags: list[str] = Field(default_factory=list)  # aborted | mumbled? | filler
    script: list[tuple[str, float]] = Field(default_factory=list)  # [(L07, 0.82), ...]
    speaker: str | None = None  # S1, S2 … (diarization; majority of the words)

    @property
    def ref(self) -> str:
        return f"{self.clip_id}:{self.id}"

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    def word_range(self) -> tuple[int, int]:
        return int(self.from_word[1:]), int(self.to_word[1:])


def segment(at: AnalyzedTranscript, cfg: Config, clip_duration_s: float) -> list[Segment]:
    tokens = [e for e in at.entries if e.id[0] == "w"]
    if not tokens:
        return []
    groups: list[list[Word]] = [[tokens[0]]]
    for a, b in zip(tokens, tokens[1:]):
        if (b.start_s - a.end_s >= cfg.segment_pause_s or SENT_END.search(a.text)
                or (a.speaker is not None and b.speaker is not None and a.speaker != b.speaker)):
            groups.append([])
        groups[-1].append(b)
    gaps_by_prev: dict[int, list[Word]] = {}
    for e in at.entries:
        if e.id[0] in "pub":
            gaps_by_prev.setdefault(int(e.id[1:5]), []).append(e)

    segs: list[Segment] = []
    for i, g in enumerate(groups):
        first, last = g[0], g[-1]
        prev_end = groups[i - 1][-1].end_s if i else 0.0
        next_start = groups[i + 1][0].start_s if i + 1 < len(groups) else clip_duration_s
        parts, n_fill = [], 0
        for k, w in enumerate(g):
            parts.append(f"{{{w.text}}}" if w.kind == "filler" else w.text)
            if k + 1 < len(g):
                for e in gaps_by_prev.get(int(w.id[1:]), []):
                    if e.kind == "filler":
                        parts.append("{?}")
                        n_fill += 1
        flags = []
        if not SENT_END.search(last.text) and (next_start - last.end_s >= cfg.long_pause_s or i + 1 == len(groups)):
            flags.append("aborted")
        if any(w.confidence == 0.0 for w in g):
            flags.append("mumbled?")
        if n_fill or any(w.kind == "filler" for w in g):
            flags.append("filler")
        spk = [w.speaker for w in g if w.speaker is not None]
        speaker = f"S{max(set(spk), key=spk.count) + 1}" if spk else None
        segs.append(Segment(
            id=f"s{i + 1:03d}", clip_id=at.clip_id, from_word=first.id, to_word=last.id, speaker=speaker,
            start_s=first.start_s, end_s=last.end_s, text=" ".join(parts),
            plain=" ".join(w.text for w in g if w.kind == "word"), n_words=len(g),
            pause_before_s=round(first.start_s - prev_end, 2), pause_after_s=round(next_start - last.end_s, 2), flags=flags))
    return segs
