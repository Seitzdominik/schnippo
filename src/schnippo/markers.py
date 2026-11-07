"""Recording aids (Phase 8, step 5): a spoken retake marker ("nochmal", "Cut", …) or a hand clap right after a slip
marks the segment BEFORE it as a rejection candidate. A hint for Claude, never a cut decision.

Spoken marker = a short utterance of its own (≤ 4 words, between pauses) made of marker words and a few filler words –
so "mehr Action" or "Stopp für Traktor" inside a sentence do not count. Clap = a short broadband peak in the level
envelope: ≥ clap_jump_db above the preceding half second, loud for ≤ 60 ms, unvoiced, not inside a recognised word."""

from __future__ import annotations

import re

import numpy as np

from .config import DEFAULT_RETAKE_WORDS  # noqa: F401  (configurable: [analysis] retake_words)
FILLERS = {"ok", "okay", "so", "ja", "nee", "ne", "nein", "bitte", "sorry", "mist", "äh", "ähm", "hm", "also", "gleich",
           "warte", "moment", "und"}


def _norm(t: str) -> str:
    return re.sub(r"[^\wäöüß ]+", "", t.lower()).strip()


def spoken(segments: list, words: list[str]) -> list[tuple[int, str]]:
    """(segment index, marker text) for utterances that are only a retake marker (+ filler words)."""
    phrases = sorted({_norm(w) for w in words if _norm(w)}, key=len, reverse=True)
    out = []
    for k, s in enumerate(segments):
        if s.n_words > 4:
            continue
        rest = " " + _norm(s.plain) + " "
        hit = None
        for ph in phrases:
            if f" {ph} " in rest:
                hit = hit or ph
                rest = rest.replace(f" {ph} ", " ")
        if hit and all(w in FILLERS for w in rest.split()):
            out.append((k, hit))
    return out


def claps(env_db: np.ndarray, voicing: np.ndarray, word_spans: list[tuple[float, float]], jump_db: float = 25.0,
          min_peak_db: float = -24.0, max_len_frames: int = 6) -> list[float]:
    """Times (s) of clap-like transients in a 10-ms level envelope."""
    n = len(env_db)
    out: list[float] = []
    spans = sorted(word_spans)
    i = 50
    while i < n - 10:
        e = env_db[i]
        if e >= min_peak_db and e - float(np.median(env_db[i - 50:i])) >= jump_db and env_db[i] - env_db[i - 1] >= 12:
            peak = i + int(np.argmax(env_db[i:i + 3]))
            loud = int(np.sum(env_db[peak:peak + 15] > env_db[peak] - 10))
            t = peak / 100
            in_word = any(a - 0.05 <= t <= b + 0.05 for a, b in spans if a - 1 <= t <= b + 1)
            if loud <= max_len_frames and voicing[peak] < 0.5 and not in_word:
                out.append(round(t, 2))
                i = peak + 30  # one clap per 0.3 s
                continue
        i += 1
    return out


def mark(segments: list, words: list[str], clap_times: list[float], window_s: float = 10.0) -> list[dict]:
    """Flags the segments in place: "marker:<text>" on the marker utterance, "retake_before:<text>" on the segment
    before a marker/clap (within window_s). Returns the found markers."""
    found = []
    for k, ph in spoken(segments, words):
        segments[k].flags.append(f"marker:{ph}")
        found.append({"kind": "gesprochen", "text": ph, "t": segments[k].start_s, "segment": segments[k].id})
        prev = next((segments[j] for j in range(k - 1, -1, -1) if not any(f.startswith("marker") for f in segments[j].flags)), None)
        if prev is not None and segments[k].start_s - prev.end_s <= window_s:
            prev.flags.append(f"retake_before:„{ph}“")
            found[-1]["before"] = prev.id
    for t in clap_times:
        prev = next((s for s in reversed(segments) if s.end_s <= t), None)
        found.append({"kind": "Klatscher", "text": "Klatscher", "t": t, "segment": None,
                      "before": prev.id if prev is not None and t - prev.end_s <= window_s else None})
        if found[-1]["before"]:
            prev.flags.append("retake_before:Klatscher")
    return found
