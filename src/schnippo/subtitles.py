"""Subtitle blocks from our word timestamps, mapped onto the finished cut (timeline frames), split into short blocks.

Phase 5: subtitles are no longer placed in Resolve (the platform's own captions are better; the SRT-timeline path had a
crash risk and a frame-rate dependency, see NOTES). Blocks feed export_transcript (.srt next to the material).
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

PUNCT_BREAK = re.compile(r"[.!?,;:…]$")
SENTENCE_BREAK = re.compile(r"[.!?…]$")


class Block(BaseModel):
    start: int  # timeline frame offset
    end: int  # exclusive
    text: str
    words: list[str]


def blocks_for_plan(pieces: list, analyzed: dict, fps: float, corrections: dict[str, str] | None = None,
                    max_words: int = 4, max_line_chars: int = 18, gap_s: float = 0.4, hold_s: float = 0.3,
                    min_s: float = 0.4, recs: list[int] | None = None, total_frames: int | None = None,
                    comma_min_words: int = 1, timing: dict | None = None) -> list[Block]:
    """recs: timeline offset per piece (read back from a timeline, may contain gaps); default = pieces back to back."""
    corrections = corrections or {}
    words_tl: list[tuple[int, int, str, str]] = []  # (start, end, text, ref)
    rec = 0
    for k, pc in enumerate(pieces):
        if recs:
            rec = recs[k]
        if pc.manual:
            rec += pc.frames
            continue
        at = analyzed[pc.clip]
        by_id = {e.id: e for e in at.entries}
        for wid in pc.word_ids:
            w = by_id.get(wid)
            if w is None or w.kind != "word":
                continue
            s = rec + max(0, round(w.start_s * fps) - pc.start_frame)
            e = rec + min(pc.frames, round(w.end_s * fps) - pc.start_frame)
            ref = f"{pc.clip}:{wid}"
            if corrections.get(ref) == "":  # merged into the previous word by a correction ("halber Grassi" → one word)
                continue
            if timing and ref in timing:  # heard in the finished cut (sense_check)
                s, e = timing[ref]
            words_tl.append((s, max(e, s + 1), corrections.get(ref, w.text), ref))
        rec += pc.frames
    total = total_frames if total_frames is not None else rec
    blocks: list[list] = []
    cur: list = []
    for k, wt in enumerate(words_tl):
        if cur:
            prev = cur[-1]
            punct = SENTENCE_BREAK.search(prev[2]) or (PUNCT_BREAK.search(prev[2]) and len(cur) >= comma_min_words)
            too_long = len(" ".join(w[2] for w in cur + [wt])) > 2 * max_line_chars
            if len(cur) >= max_words or punct or too_long or wt[0] - prev[1] > gap_s * fps:
                blocks.append(cur)
                cur = []
        cur.append(wt)
    if cur:
        blocks.append(cur)
    # too short to read (< min_s, e.g. "Und dann dachte ich mir,") → merge with the next block if it still fits
    merged: list[list] = []
    for b in blocks:
        if merged:
            p = merged[-1]
            text = " ".join(w[2] for w in p + b)
            if (p[-1][1] - p[0][0] < min_s * fps and len(p) + len(b) <= max_words and len(text) <= 2 * max_line_chars
                    and b[0][0] - p[-1][1] <= gap_s * fps and not SENTENCE_BREAK.search(p[-1][2])):
                merged[-1] = p + b
                continue
        merged.append(b)
    blocks = merged
    out: list[Block] = []
    for k, b in enumerate(blocks):
        start, end = b[0][0], b[-1][1]
        nxt = blocks[k + 1][0][0] if k + 1 < len(blocks) else total
        end = min(max(end + round(hold_s * fps), start + round(min_s * fps)), nxt, total)
        text = " ".join(w[2] for w in b)
        out.append(Block(start=start, end=max(end, start + 1), text=_two_lines(text, max_line_chars), words=[w[3] for w in b]))
    return out


def _two_lines(text: str, max_chars: int) -> str:
    if len(text) <= max_chars or " " not in text:
        return text
    ws = text.split(" ")
    best = min(range(1, len(ws)), key=lambda i: abs(len(" ".join(ws[:i])) - len(" ".join(ws[i:]))))
    return " ".join(ws[:best]) + "\n" + " ".join(ws[best:])


def _srt_time(frames: int, fps: float) -> str:
    ms = round(frames / fps * 1000)
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(blocks: list[Block], fps: float, path: Path) -> Path:
    lines = []
    for k, b in enumerate(blocks, 1):
        lines += [str(k), f"{_srt_time(b.start, fps)} --> {_srt_time(b.end, fps)}", b.text, ""]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return Path(path)


def suggest_from_script(segments: list, analyzed, script_lines: list) -> list[tuple[str, str, str, str]]:
    """(word ref, current text, suggestion, script line) for 1:1 word substitutions against the matched script line."""
    import difflib

    norm = lambda t: re.sub(r"[^\wäöüß]+", "", t.lower())
    by_line = {ln.id: ln for ln in script_lines}
    by_id = {e.id: e for e in analyzed.entries}
    out = []
    for s in segments:
        if not s.script or s.script[0][1] < 0.7:
            continue
        line = by_line[s.script[0][0]]
        a0, a1 = s.word_range()
        words = [by_id[f"w{n:04d}"] for n in range(a0, a1 + 1) if f"w{n:04d}" in by_id and by_id[f"w{n:04d}"].kind == "word"]
        script_words = line.text.split()
        sm = difflib.SequenceMatcher(a=[norm(w.text) for w in words], b=[norm(w) for w in script_words], autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "replace" and i2 - i1 == j2 - j1:
                for k in range(i2 - i1):
                    out.append((f"{s.clip_id}:{words[i1 + k].id}", words[i1 + k].text, script_words[j1 + k], line.id))
    return out
