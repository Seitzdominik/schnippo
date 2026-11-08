"""Transcript export of the finished cut: .srt (short blocks for Instagram/Edits/YouTube), .txt (running text with
paragraphs), YouTube chapter suggestions. Word timestamps are mapped onto timeline time via the pieces (from a cutlist
plan or read back from a Resolve timeline); corrections (set_word_text / cutlist) are applied.
"""

from __future__ import annotations

from . import platforms
import re
from pathlib import Path

from pydantic import BaseModel

from .formatting import ts
from .subtitles import Block, blocks_for_plan, write_srt

SENTENCE_END = re.compile(r"[.!?…]$")


class Chapter(BaseModel):
    word: str  # first word of the chapter, e.g. "c01:w0120"
    title: str


def timeline_words(pieces: list, analyzed: dict, fps: float, corrections: dict[str, str], recs: list[int] | None = None,
                   timing: dict | None = None) -> list[dict]:
    """Every spoken word of the cut in timeline order: ref, text (corrected), timeline start/end frame, item index."""
    out, rec = [], 0
    for k, pc in enumerate(pieces):
        r0 = recs[k] if recs else rec
        if pc.manual:
            rec += pc.frames
            continue
        by_id = {e.id: e for e in analyzed[pc.clip].entries}
        for wid in pc.word_ids:
            w = by_id.get(wid)
            if w is None or w.kind != "word":
                continue
            ref = f"{pc.clip}:{wid}"
            if corrections.get(ref) == "":  # merged into the previous word
                continue
            s = r0 + max(0, round(w.start_s * fps) - pc.start_frame)
            e = r0 + min(pc.frames, round(w.end_s * fps) - pc.start_frame)
            if timing and ref in timing:
                s, e = timing[ref]
            out.append({"ref": ref, "text": corrections.get(ref, w.text), "start": s, "end": max(e, s + 1), "item": pc.item,
                        "piece": k})
        rec = r0 + pc.frames
    return out


def paragraphs(words: list[dict], min_sentences: int = 3, max_sentences: int = 6) -> list[str]:
    """Running text; a paragraph ends at a sentence end that is also an item boundary once it has min_sentences, or
    after max_sentences in any case."""
    paras, cur, n_sent = [], [], 0
    for k, w in enumerate(words):
        cur.append(w["text"])
        if SENTENCE_END.search(w["text"]):
            n_sent += 1
            nxt = words[k + 1] if k + 1 < len(words) else None
            boundary = nxt is None or nxt["item"] != w["item"]
            if nxt is None or (boundary and n_sent >= min_sentences) or n_sent >= max_sentences:
                paras.append(" ".join(cur))
                cur, n_sent = [], 0
    if cur:
        paras.append(" ".join(cur))
    return paras


def _sentence_starts(words: list[dict]) -> list[int]:
    return [k for k, w in enumerate(words) if k == 0 or SENTENCE_END.search(words[k - 1]["text"])]


def suggest_chapters(words: list[dict], fps: float, total_frames: int, min_chapters: int = 3, min_len_s: float = 10.0,
                     target_len_s: float = 90.0) -> list[tuple[int, str, str]]:
    """(timeline frame, first word ref, title placeholder) – first at 0:00, ≥ min_chapters if the cut is long enough,
    each ≥ min_len_s; boundaries prefer sentence starts at item boundaries, evenly spread."""
    if not words:
        return []
    total_s = total_frames / fps
    n = max(min_chapters, round(total_s / target_len_s))
    n = min(n, int(total_s // min_len_s))
    starts = _sentence_starts(words)
    item_starts = [k for k in starts if k and words[k]["item"] != words[k - 1]["item"]] or starts[1:]
    picked = [0]
    for j in range(1, n):
        want = total_frames * j / n
        cands = [k for k in item_starts if words[k]["start"] - words[picked[-1]]["start"] >= min_len_s * fps
                 and total_frames - words[k]["start"] >= min_len_s * fps]
        if not cands:
            break
        picked.append(min(cands, key=lambda k: abs(words[k]["start"] - want)))
    out = []
    for k in picked:
        title = " ".join(w["text"] for w in words[k:k + 6]).rstrip(",;:")
        out.append((0 if k == 0 else words[k]["start"], words[k]["ref"], title))
    return out


def chapter_lines(chapters: list[tuple[int, str, str]], fps: float) -> list[str]:
    def yt(fr: int) -> str:
        s = int(fr / fps)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
    return [f"{yt(fr)} {title}" for fr, _, title in chapters]


def check_chapters(chapters: list[tuple[int, str, str]], fps: float, total_frames: int, min_chapters: int = 3,
                   min_len_s: float = 10.0) -> list[str]:
    warn = []
    if len(chapters) < min_chapters:
        warn.append(f"nur {len(chapters)} Kapitel – YouTube zeigt Kapitel erst ab {min_chapters}")
    ends = [c[0] for c in chapters[1:]] + [total_frames]
    for (fr, ref, title), e in zip(chapters, ends):
        if (e - fr) / fps < min_len_s:
            warn.append(f"Kapitel „{title}“ ({ref}) ist {(e - fr) / fps:.1f} s lang (< {min_len_s:g} s)")
    return warn


def export(name: str, pieces: list, analyzed: dict, fps: float, corrections: dict[str, str], out_dir: Path,
           fmt: str = "reel", max_words: int = 4, max_line_chars: int = 18, chapters: list[Chapter] | None = None,
           recs: list[int] | None = None, total_frames: int | None = None, min_s: float = 0.4,
           comma_min_words: int = 1, timing: dict | None = None) -> dict:
    """Write <out_dir>/<name>.srt, .txt (+ _kapitel.txt for youtube or given chapters). Returns paths + previews."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = platforms.safe_filename(name)
    total = total_frames if total_frames is not None else (
        (recs[-1] + pieces[-1].frames) if recs else sum(pc.frames for pc in pieces))
    blocks: list[Block] = blocks_for_plan(pieces, analyzed, fps, corrections, max_words, max_line_chars, recs=recs,
                                          total_frames=total, min_s=min_s, comma_min_words=comma_min_words, timing=timing)
    srt = write_srt(blocks, fps, out_dir / f"{name}.srt")
    words = timeline_words(pieces, analyzed, fps, corrections, recs, timing)
    paras = paragraphs(words)
    txt = out_dir / f"{name}.txt"
    txt.write_text("\n\n".join(paras) + "\n", encoding="utf-8")
    res = {"srt": str(srt), "txt": str(txt), "blocks": len(blocks), "words": len(words), "paragraphs": len(paras),
           "seconds": round(total / fps, 3), "srt_preview": srt.read_text(encoding="utf-8").split("\n\n")[:4],
           "txt_preview": paras[:2], "chapters": [], "chapter_warnings": []}
    if fmt in ("youtube", "course") or chapters:
        if chapters:
            by_ref = {w["ref"]: w for w in words}
            ch, unknown = [], []
            for c in chapters:
                w = by_ref.get(c.word.strip().lower())
                if w is None:
                    unknown.append(c.word)
                else:
                    ch.append((w["start"], w["ref"], c.title))
            ch.sort()
            if ch:
                ch[0] = (0, ch[0][1], ch[0][2])  # YouTube: the first chapter starts at 0:00
            res["chapter_warnings"] += [f"Kapitel-Wort {u} liegt nicht im Schnitt" for u in unknown]
            res["chapter_source"] = "vorgegeben"
        else:
            ch = suggest_chapters(words, fps, total)
            res["chapter_source"] = "Vorschlag (Titel = Satzanfang, bitte formulieren und mit chapters=[…] erneut exportieren)"
        res["chapter_warnings"] += check_chapters(ch, fps, total)
        lines = chapter_lines(ch, fps)
        f = out_dir / f"{name}_kapitel.txt"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        res["chapters"] = [{"at": ts(fr / fps), "word": ref, "title": t} for fr, ref, t in ch]
        res["chapters_file"] = str(f)
    return res


def pieces_from_timeline(items: list[dict], analyzed: dict) -> tuple[list, list[int]]:
    """Pseudo pieces from V1 items read back from Resolve (clip, src_start, frames, rec): a word belongs to the piece
    that shows at least half of it."""
    from .cutlist import Piece

    pieces, recs = [], []
    for k, it in enumerate(items, 1):
        at = analyzed.get(it["clip"])
        if at is None:
            continue
        fps = it["fps"]
        a, b = it["src_start"], it["src_start"] + it["frames"]
        ids = []
        for e in at.entries:
            if e.id[0] != "w" or e.kind != "word":
                continue
            ws, we = e.start_s * fps, e.end_s * fps
            inside = max(0.0, min(we, b) - max(ws, a))
            if inside >= 0.5 * max(we - ws, 1e-6):
                ids.append(e.id)
        pieces.append(Piece(item=it.get("item", k), clip=it["clip"], start_s=a / fps, end_s=b / fps, start_frame=a,
                            end_frame=b, text="", word_ids=ids))
        recs.append(it["rec"])
    return pieces, recs


def report_text(res: dict) -> list[str]:
    out = [f"Export: {res['blocks']} SRT-Blöcke, {res['words']} Wörter, {res['paragraphs']} Absätze, Dauer {ts(res['seconds'])}",
           f"  SRT: {res['srt']}", f"  TXT: {res['txt']}"]
    if res.get("chapters_file"):
        out.append(f"  Kapitel ({res.get('chapter_source')}): {res['chapters_file']}")
        out += [f"    {c['at']} {c['title']}  [{c['word']}]" for c in res["chapters"]]
    out += [f"  Warnung {w}" for w in res["chapter_warnings"]]
    out.append("  SRT-Anfang:")
    out += ["    " + b.replace("\n", " ⏎ ") for b in res["srt_preview"]]
    out.append("  TXT-Anfang:")
    out += ["    " + p[:300] + ("…" if len(p) > 300 else "") for p in res["txt_preview"]]
    return out

