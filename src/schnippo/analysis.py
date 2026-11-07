"""Deterministic base analysis: fillers, pauses, gap fallback, repetitions, restart candidates.

Output is flags + findings only. Nothing here decides what gets cut.
"""

from __future__ import annotations

import re
import unicodedata

from .acoustic import Acoustic
from .config import Config
from .models import AnalyzedTranscript, Finding, RawTranscript, Word

_PUNCT = re.compile(r"[^\wäöüß']+", re.UNICODE)


def norm(text: str) -> str:
    t = unicodedata.normalize("NFC", text).lower().strip()
    return _PUNCT.sub("", t)


def _gap_id(prefix: str, prev_num: int, k: int) -> str:
    return f"{prefix}{prev_num:04d}" + (f".{k}" if k > 1 else "")


def analyze(clip_id: str, raw: RawTranscript, cfg: Config, acoustic: Acoustic | None = None,
            clip_duration_s: float | None = None) -> AnalyzedTranscript:
    from .config import EN_HARD_FILLERS
    hard = {norm(f) for f in cfg.hard_fillers} | ({norm(f) for f in EN_HARD_FILLERS}
                                                   if (raw.language or "").lower().startswith("en") else set())
    soft = {norm(f) for f in cfg.soft_fillers}

    tokens: list[Word] = []
    for t in raw.tokens:
        w = t.model_copy(deep=True)
        n = norm(w.text)
        if n in hard or re.fullmatch(r"(ä+h+m*|ö+h+m*|e+h+m+|h+m+|m+h+m+)", n or "-"):
            w.kind = "filler"
        elif n in soft:
            w.flags.append("soft_filler")
        tokens.append(w)

    # --- word edges stretched over silence (Gladia sometimes adds a pause to a word, see NOTES) ---
    if acoustic is not None:
        for w in tokens:
            runs = acoustic.silent_runs(w.start_s, w.end_s, cfg.clamp_silence_s)
            if not runs:
                continue
            # silence followed by at most a short onset of the next word -> the word really ended before it
            if w.end_s - runs[-1][1] <= 0.3:
                w.flags.append(f"end_clamped:{w.end_s:.2f}")
                w.end_s = round(runs[-1][0], 3)
            elif runs[0][0] - w.start_s <= 0.3:
                w.flags.append(f"start_clamped:{w.start_s:.2f}")
                w.start_s = round(runs[0][1], 3)

    # --- gaps: pauses and speech without a recognised word (filler fallback) ---
    entries: list[Word] = []
    findings: list[Finding] = []
    n_inferred = 0
    bounds = [(0.0, None)] + [(t.end_s, t) for t in tokens]
    for i, (gap_start, prev) in enumerate(bounds):
        nxt = tokens[i] if i < len(tokens) else None
        gap_end = nxt.start_s if nxt else (clip_duration_s if clip_duration_s is not None else gap_start)
        prev_num = int(prev.id[1:]) if prev else 0
        if prev:
            entries.append(prev)
        if gap_end - gap_start <= 1e-3:
            continue
        pieces: list[tuple[str, float, float, dict]] = []  # (kind, t0, t1, info)
        cur = gap_start
        for a, b in (acoustic.regions(gap_start, gap_end) if acoustic is not None else []):
            # activity that merely continues a neighbouring word (ASR edges are tight) is not an event
            tp, tn = bool(prev) and a - gap_start <= 0.04, bool(nxt) and gap_end - b <= 0.04
            if tp and tn and b - a < cfg.bridge_min_s:  # voice runs through the whole gap: coarticulation
                continue
            if (tp or tn) and b - a < cfg.hug_max_s:
                continue
            info = acoustic.classify(a, b)
            if info["class"] == "click":
                continue
            if info["class"] == "voiced" and b - a < cfg.gap_speech_min_s:
                continue
            if a - cur > 0:
                pieces.append(("pause", cur, a, {}))
            pieces.append((info["class"], a, b, info))
            cur = b
        if gap_end - cur > 0:
            pieces.append(("pause", cur, gap_end, {}))
        kp = ku = kb = 0
        for kind, a, b, info in pieces:
            if kind == "pause":
                if b - a < cfg.pause_threshold_s:
                    continue
                kp += 1
                flags = ["long_pause"] if b - a >= cfg.long_pause_s else []
                if prev is None:
                    flags.append("leading")
                if nxt is None:
                    flags.append("trailing")
                entries.append(Word(id=_gap_id("p", prev_num, kp), text=f"{b - a:.1f}s", start_s=round(a, 3),
                                    end_s=round(b, 3), kind="pause", flags=flags))
            elif kind == "breath":
                kb += 1
                entries.append(Word(id=_gap_id("b", prev_num, kb), text="breath", start_s=round(a, 3), end_s=round(b, 3),
                                    kind="breath", flags=["inferred"]))
            else:
                ku += 1
                n_inferred += 1
                uid = _gap_id("u", prev_num, ku)
                entries.append(Word(id=uid, text="?", start_s=round(a, 3), end_s=round(b, 3), kind="filler",
                                    flags=["inferred", "filler?"]))
                findings.append(Finding(type="unrecognized_speech", first=(uid, uid),
                                        note=f"stimmhaft ohne Wort {a:.2f}-{b:.2f}s, {info['peak_db']} dB (Füllwort/Dehnung?)"))

    # --- repetitions / restarts over content tokens (fillers + gap entries ignored) ---
    content = [t for t in tokens if t.kind == "word"]
    keys = [norm(t.text) for t in content]
    flagged_until = -1
    for i in range(len(content)):
        if i <= flagged_until:
            continue
        best = None
        for n in range(6, 0, -1):
            if i + n > len(keys):
                continue
            gram = keys[i:i + n]
            if not all(gram):
                continue
            # the repeat must start soon after the first occurrence ends (restart = "Neuanfang")
            window = 3 if n == 1 else n + 8
            for j in range(i + n, min(i + n + window, len(keys) - n + 1)):
                if keys[j:j + n] == gram:
                    if content[j].start_s - content[i + n - 1].end_s > 12.0:
                        break
                    best = (n, j)
                    break
            if best:
                break
        if not best:
            continue
        n, j = best
        first = (content[i].id, content[i + n - 1].id)
        second = (content[j].id, content[j + n - 1].id)
        between = j - (i + n)
        if n == 1 and between == 0:
            ftype, flag = "repeat", "repeat"
            note = f"„{content[i].text} {content[j].text}“"
        elif n == 1:
            continue  # single word recurring a few words later: too common in normal speech
        else:
            ftype, flag = "restart_candidate", "restart_candidate"
            note = f"„{' '.join(t.text for t in content[i:i + n])}“ wiederholt" + (
                f" nach {between} Wort/Wörtern" if between else "")
        for t in content[i:j] if ftype == "restart_candidate" else content[i:i + n]:
            if flag not in t.flags:
                t.flags.append(flag)
        findings.append(Finding(type=ftype, first=first, second=second, note=note))
        flagged_until = i + n - 1

    for e in entries:
        if "long_pause" in e.flags:
            findings.append(Finding(type="long_pause", first=(e.id, e.id), note=e.text))

    stats = {
        "words": sum(1 for t in tokens if t.kind == "word"),
        "fillers_asr": sum(1 for t in tokens if t.kind == "filler"),
        "fillers_inferred": n_inferred,
        "soft_fillers": sum(1 for t in tokens if "soft_filler" in t.flags),
        "breaths": sum(1 for e in entries if e.kind == "breath"),
        "pauses": sum(1 for e in entries if e.kind == "pause"),
        "repeats": sum(1 for f in findings if f.type == "repeat"),
        "restart_candidates": sum(1 for f in findings if f.type == "restart_candidate"),
    }
    findings.sort(key=lambda f: _sort_key(f.first[0]))
    return AnalyzedTranscript(clip_id=clip_id, provider=raw.provider, language=raw.language,
                              entries=entries, findings=findings, stats=stats)


def _sort_key(entry_id: str) -> tuple[int, int]:
    m = re.match(r"[wpub](\d+)(?:\.(\d+))?", entry_id)
    return (int(m.group(1)), 0 if entry_id[0] == "w" else int(m.group(2) or 1)) if m else (0, 0)
