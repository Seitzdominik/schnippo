"""Reels from the long version (Phase 10): the structure Claude picks from, the cut of one passage, the texts around it. The crop is in reframe.py."""

from __future__ import annotations

import io
import re

from .formatting import ts

NUMBER = re.compile(r"\d|\b(zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|zwölf|zwanzig|dreißig|fünfzig|hundert|tausend|prozent|million\w*|erstens|zweitens|drittens)\b", re.I)
LIST = re.compile(r"\b(erstens|zweitens|drittens|tipps?|fehler|gründe?|schritte?|regeln)\b", re.I)
LAUGH = re.compile(r"\b(haha+|hehe+|lach\w*)\b", re.I)
BACKREF = re.compile(r"^(das|dies\w*|dann|also|und|aber|oder|weil|denn|wie gesagt|er|sie|es|da|dort|deshalb|deswegen|darum|genau|ja)\b", re.I)
SENTENCE_END = re.compile(r"[.!?…]$")


def _mean_db(ac, t0: float, t1: float) -> float | None:
    a, b = max(0, int(t0 * 100)), int(t1 * 100)
    seg = ac.env_db[a:b]
    return float(seg.mean()) if len(seg) else None


def sentences(words: list[dict], speakers: dict, src: dict, energy: dict, fps: float, beats: list) -> list[dict]:
    """Words → sentences with timeline time, speaker, rate, level against the speaker's average, signals, beat after the sentence."""
    beat_at = {b["word"].lower(): b["kind"] for b in beats}
    out, cur = [], []

    def flush():
        if not cur:
            return
        text = " ".join(w["text"] for w in cur)
        t0, t1 = cur[0]["start"] / fps, cur[-1]["end"] / fps
        votes: dict = {}
        for w in cur:
            votes[speakers.get(w["ref"])] = votes.get(speakers.get(w["ref"]), 0) + 1
        levels = []
        for w in cur:
            cid = w["ref"].split(":")[0]
            if w["ref"] in src and cid in energy:
                v = _mean_db(energy[cid], *src[w["ref"]])
                if v is not None:
                    levels.append(v)
        tags = [t for t, rx in (("Zahl", NUMBER), ("Liste", LIST), ("Lachen", LAUGH)) if rx.search(text)]
        if text.endswith("?"):
            tags.append("Frage")
        if BACKREF.search(text):
            tags.append("Bezug?")
        beat = next((beat_at[w["ref"].lower()] for w in cur if w["ref"].lower() in beat_at), None)
        out.append({"from": cur[0]["ref"], "to": cur[-1]["ref"], "t0": t0, "t1": t1, "speaker": max(votes, key=lambda k: votes[k]), "text": text, "words": len(cur),
                    "rate": round(len(cur) / max(t1 - t0, 0.1), 1), "level": sum(levels) / len(levels) if levels else None, "tags": tags, "beat": beat})
        cur.clear()

    for w in words:
        if cur and speakers.get(w["ref"]) != speakers.get(cur[-1]["ref"]):
            flush()
        cur.append(w)
        if SENTENCE_END.search(w["text"]):
            flush()
    flush()
    known = [s["level"] for s in out if s["level"] is not None]
    mid = sorted(known)[len(known) // 2] if known else 0.0
    for s in out:
        s["level_db"] = None if s["level"] is None else round(s["level"] - mid, 1)
    return out


def blocks(sents: list[dict], min_s: float, max_s: float) -> list[dict]:
    """Answers of one speaker between section ends. The main speaker's blocks are what reels are cut from; questions divide them."""
    if not sents:
        return []
    count: dict = {}
    for s in sents:
        count[s["speaker"]] = count.get(s["speaker"], 0) + s["words"]
    main = max(count, key=lambda k: count[k])
    out, cur = [], []

    def flush():
        if cur:
            d = cur[-1]["t1"] - cur[0]["t0"]
            out.append({"from": cur[0]["from"], "to": cur[-1]["to"], "t0": cur[0]["t0"], "t1": cur[-1]["t1"], "duration": d, "sentences": len(cur), "fits": min_s <= d <= max_s,
                        "first": cur[0]["text"]})
            cur.clear()

    for s in sents:
        if s["speaker"] != main:
            flush()
            continue
        cur.append(s)
        if s["beat"] == "section":
            flush()
    flush()
    return out


def candidates_text(timeline: str, data: dict, count: int, min_s: float, max_s: float) -> str:
    lines = [f"Reel-Kandidaten aus „{timeline}“ ({ts(data['total_s'])}): {len(data['sentences'])} Sätze, {len(data['blocks'])} Blöcke. Wähle etwa {count} zusammenhängende Stellen von {min_s:g}–{max_s:g} s.",
             "Bewerte je Stelle Hook, Verständlichkeit ohne Kontext, Abschluss und Wert (Leitfaden reel). „Bezug?“ heißt: Der Satz beginnt mit einem Wort, das sich auf Vorheriges beziehen kann.",
             "", "Blöcke (Antworten einer Person bis zum Abschnittsende; zu lange Blöcke enthalten oft eine gute Stelle):"]
    for k, b in enumerate(data["blocks"], 1):
        lines.append(f"B{k:02d} {ts(b['t0'])}–{ts(b['t1'])} {b['duration']:.0f} s, {b['sentences']} Sätze{'' if b['fits'] else ' (Länge passt nicht)'} {b['from']}–{b['to']} „{b['first'][:70]}“")
    lines += ["", "Sätze (Wörter, Zeit, Dauer, Sprecher, Wörter je s, Pegel zum Mittel, Signale):"]
    for s in data["sentences"]:
        tags = " ".join(s["tags"] + ([f"beat:{s['beat']}"] if s["beat"] else []))
        lvl = "" if s["level_db"] is None else f" {s['level_db']:+.0f} dB"
        lines.append(f"{s['from']}–{s['to'].split(':')[-1]} {ts(s['t0'])} {s['t1'] - s['t0']:.1f} s S{s['speaker']} {s['rate']} W/s{lvl}{' [' + tags + ']' if tags else ''} {s['text']}")
    return "\n".join(lines)


def _item_of(items: list, ref: str) -> tuple[int, str, int]:
    from .cutlist import _word_ref
    cid, n = _word_ref(ref)
    for k, it in enumerate(items):
        if it.clip.strip().lower() == cid and int(it.from_word[1:]) <= n <= int(it.to_word[1:]):
            return k, cid, n
    raise ValueError(f"{ref} liegt nicht in der langen Fassung")


def _cut(spans: list, cid: str, a: int, b: int) -> list:
    out = []
    for c, x, y, note in spans:
        if c != cid or b < x or a > y:
            out.append((c, x, y, note))
            continue
        if x < a:
            out.append((c, x, a - 1, note))
        if b < y:
            out.append((c, b + 1, y, note))
    return out


def spans_between(cl, from_word: str, to_word: str, remove: list, cold_open: dict | None) -> tuple[list, list[str]]:
    """(clip, from, to, note) of a passage of the long version. Words are only removed or moved to the front inside the passage: nothing comes in from elsewhere."""
    from .cutlist import _word_ref
    from .revise import _words_range
    i, c0, n0 = _item_of(cl.items, from_word)
    j, c1, n1 = _item_of(cl.items, to_word)
    spans = []
    if c0 == c1:  # one recording: its order, also where the long version moved a sentence to the front
        if n1 < n0:
            raise ValueError(f"{to_word} liegt vor {from_word}")
        for it in cl.items:
            a, b = int(it.from_word[1:]), int(it.to_word[1:])
            if it.clip.strip().lower() == c0 and a <= n1 and b >= n0:
                spans.append((c0, max(a, n0), min(b, n1), it.note or ""))
        spans.sort(key=lambda s: s[1])
    else:
        if j < i:
            raise ValueError(f"{to_word} liegt vor {from_word}")
        for k in range(i, j + 1):
            it = cl.items[k]
            a, b = int(it.from_word[1:]), int(it.to_word[1:])
            spans.append((it.clip.strip().lower(), n0 if k == i else a, n1 if k == j else b, it.note or ""))
    whole = list(spans)
    notes: list[str] = []
    for r in remove:
        c, a, b = _words_range(r)
        spans = _cut(spans, c, a, b)
    if cold_open:
        c, a = _word_ref(cold_open["from_word"])
        _, b = _word_ref(cold_open["to_word"])
        if not any(s[0] == c and s[1] <= a and b <= s[2] for s in whole):
            raise ValueError("Cold Open muss aus derselben Stelle stammen: Aussagen aus verschiedenen Stellen dürfen keinen neuen Sinn ergeben")
        spans = [(c, a, b, "Cold Open")] + _cut(spans, c, a, b)
        notes.append("Cold Open vorn; beim Lesen prüfen, ob der Rest ohne den Satz noch trägt")
    return spans, notes


def candidate_text(cands: list[dict]) -> str:
    lines = []
    for k, c in enumerate(cands, 1):
        lines.append(f"{k}. {c.get('title', 'ohne Titel')} ({c.get('duration_s', '?')} s, {c.get('from_word')}–{c.get('to_word')}{', ' + c['range'] if c.get('range') else ''})\n"
                     f"   Hook: {c.get('hook', '')}\n   Bewertung: {c.get('rating', '')}")
    return "\n".join(lines)


def candidate_sheet(stills: list) -> bytes | None:
    """stills: (image path, (face box, analysis size) | None). 9:16 crops on the head, numbered, in one row."""
    from PIL import Image, ImageDraw
    tiles = []
    for k, (path, face) in enumerate(stills, 1):
        if path is None:
            continue
        im = Image.open(path).convert("RGB")
        w, h = im.size
        cw = round(h * 9 / 16)
        cx = w / 2
        if face:
            box, (aw, _) = face
            cx = (box[0] + box[2] / 2) / aw * w
        x = int(max(0, min(w - cw, cx - cw / 2)))
        tile = im.crop((x, 0, x + cw, h)).resize((180, 320))
        ImageDraw.Draw(tile).rectangle((0, 0, 30, 22), fill=(0, 0, 0))
        ImageDraw.Draw(tile).text((8, 5), str(k), fill=(255, 255, 255))
        tiles.append(tile)
    if not tiles:
        return None
    sheet = Image.new("RGB", (len(tiles) * 188 - 8, 320), (20, 20, 20))
    for k, t in enumerate(tiles):
        sheet.paste(t, (k * 188, 0))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def slug(title: str) -> str:
    t = title.lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:32] or "reel"


def sheet(frames: list, info: dict) -> tuple[bytes, list[str]]:
    """frames: (timeline frame, label, PIL image 1080×1920). Draws head box and safe zone, looks for empty edges. → JPEG, findings."""
    from PIL import Image, ImageDraw
    import numpy as np
    k = 0.4
    tiles, notes = [], []
    for t, label, im in frames:
        a = np.asarray(im.convert("L"), dtype=np.float32)
        edges = {"links": a[:, :6], "rechts": a[:, -6:], "oben": a[:6, :], "unten": a[-6:, :]}
        dark = [n for n, e in edges.items() if e.mean() < 4 and e.max() < 16]
        if dark:
            notes.append(f"{label}: Rand leer ({', '.join(dark)})")
        tile = im.convert("RGB").resize((round(im.width * k), round(im.height * k)))
        d = ImageDraw.Draw(tile)
        s = info["safe"]
        d.rectangle([v * k for v in s], outline=(0, 220, 255), width=2)
        hb = info["heads"].get(t)
        if hb:
            d.rectangle([hb[0] * k, hb[1] * k, (hb[0] + hb[2]) * k, (hb[1] + hb[3]) * k], outline=(255, 220, 0), width=2)
        d.rectangle((0, 0, 170, 20), fill=(0, 0, 0))
        d.text((6, 4), label, fill=(255, 255, 255))
        tiles.append(tile)
    w, h = tiles[0].size
    out = Image.new("RGB", (len(tiles) * (w + 8) - 8, h), (20, 20, 20))
    for i, t in enumerate(tiles):
        out.paste(t, (i * (w + 8), 0))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=84)
    return buf.getvalue(), notes
