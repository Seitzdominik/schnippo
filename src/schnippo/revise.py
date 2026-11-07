"""Correction loop (Phase 8, step 2): find what the user means, change it, show what changed, adopt manual edits.

- locate: "#05" (item marker), a timecode ("0:23", "1:02.5", "00:00:23:12") or a quote → item, word IDs, position.
- revise: change requests as operations on the built cutlist of a timeline → a new version "<timeline>_r2" (never
  overwrites); the diff (new / removed / moved / changed items, duration) is part of validate_cutlist.
- timeline_changes: compares a Resolve timeline (V1 read back) with the cutlist it was built from and turns it into a
  cutlist that reproduces the edited timeline 1:1 (explicit frames, no re-tightening). Nothing manual is dropped
  silently: whatever cannot be expressed (unknown media, partly cut words, changed overlays) is listed as unclear.
"""

from __future__ import annotations

import difflib
import re

from .cutlist import Beat, Correction, Cutlist, CutItem, Overlay, Plan, SfxCue

_NORM = re.compile(r"[^\wäöüß]+")


def norm(t: str) -> str:
    return _NORM.sub("", t.lower())


def recs_of(pieces: list) -> list[int]:
    out, r = [], 0
    for p in pieces:
        out.append(r)
        r += p.frames
    return out


def parse_timecode(ref: str, fps: float) -> int | None:
    """"0:23", "1:02.5", "23s", "00:00:23:12" (HH:MM:SS:FF), "f575" → timeline frame; None if not a timecode."""
    t = ref.strip().lower()
    m = re.fullmatch(r"f(\d+)", t)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*s", t)
    if m:
        return round(float(m.group(1).replace(",", ".")) * fps)
    m = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2}):(\d{2})", t)
    if m:
        h, mi, s, f = map(int, m.groups())
        return round((h * 3600 + mi * 60 + s) * fps) + f
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2}(?:[.,]\d+)?)", t)
    if m:
        h = int(m.group(1) or 0)
        return round((h * 3600 + int(m.group(2)) * 60 + float(m.group(3).replace(",", "."))) * fps)
    return None


def spoken_words(plan: Plan, analyzed: dict, fps: float, corrections: dict | None = None) -> list[dict]:
    """Every word of the cut in timeline order: ref, text, timeline start/end frame, item number."""
    corrections = corrections or {}
    out = []
    for pc, r0 in zip(plan.pieces, recs_of(plan.pieces)):
        by_id = {e.id: e for e in analyzed[pc.clip].entries}
        for wid in pc.word_ids:
            w = by_id.get(wid)
            if w is None or w.kind != "word":
                continue
            ref = f"{pc.clip}:{wid}"
            s = r0 + max(0, round(w.start_s * fps) - pc.start_frame)
            e = r0 + min(pc.frames, round(w.end_s * fps) - pc.start_frame)
            out.append({"ref": ref, "text": corrections.get(ref, w.text), "start": s, "end": max(e, s + 1), "item": pc.item})
    return out


def find_quote(words: list[dict], quote: str, min_ratio: float = 0.6) -> list[tuple[float, int, int]]:
    """Best windows (ratio, i, j) in the spoken words for a quote (fuzzy: recognition errors, missing commas)."""
    q = [norm(x) for x in quote.split() if norm(x)]
    if not q:
        return []
    toks = [norm(w["text"]) for w in words]
    n, hits = len(q), []
    for size in {max(1, n - 1), n, n + 1}:
        for i in range(0, max(0, len(toks) - size) + 1):
            r = difflib.SequenceMatcher(a=q, b=toks[i:i + size], autojunk=False).ratio()
            if r >= min_ratio:
                hits.append((r, i, i + size - 1))
    hits.sort(key=lambda h: (-h[0], h[1]))
    out: list[tuple[float, int, int]] = []
    for h in hits:  # no overlapping duplicates
        if all(h[2] < o[1] or h[1] > o[2] for o in out):
            out.append(h)
    return out[:3]


def resolve_ref(ref: str, cl: Cutlist, plan: Plan, words: list[dict], fps: float) -> dict:
    """→ {"kind": item|time|quote, "item": n, "words": (ref0, ref1), "start": f, "end": f, "text": …, "alternatives": […]}"""
    ref = ref.strip()
    recs = recs_of(plan.pieces)
    m = re.fullmatch(r"#\s*0*(\d+)", ref)
    if m:
        n = int(m.group(1))
        if not 1 <= n <= len(cl.items):
            raise KeyError(f"#{n:02d} gibt es nicht (#01–#{len(cl.items):02d})")
        ps = [(p, r) for p, r in zip(plan.pieces, recs) if p.item == n]
        ws = [w for w in words if w["item"] == n]
        it = cl.items[n - 1]
        return {"kind": "item", "item": n, "words": (f"{it.clip}:{it.from_word}", f"{it.clip}:{it.to_word}"),
                "start": ps[0][1] if ps else None, "end": (ps[-1][1] + ps[-1][0].frames) if ps else None,
                "text": " ".join(w["text"] for w in ws), "alternatives": []}
    f = parse_timecode(ref, fps)
    if f is not None:
        if not words:
            raise LookupError("keine Wörter im Schnitt")
        w = min(words, key=lambda x: 0 if x["start"] <= f < x["end"] else min(abs(x["start"] - f), abs(x["end"] - f)))
        k = words.index(w)
        sent = _sentence(words, k)
        return {"kind": "time", "item": w["item"], "words": (w["ref"], w["ref"]), "start": w["start"], "end": w["end"],
                "text": w["text"], "sentence": (words[sent[0]]["ref"], words[sent[1]]["ref"]),
                "sentence_text": " ".join(x["text"] for x in words[sent[0]:sent[1] + 1]), "frame": f, "alternatives": []}
    quote = ref.strip("„“\"'»«")
    hits = find_quote(words, quote)
    if not hits:
        raise LookupError(f"„{quote}“ kommt im Schnitt nicht vor (auch nicht ähnlich)")
    r, i, j = hits[0]
    return {"kind": "quote", "item": words[i]["item"], "words": (words[i]["ref"], words[j]["ref"]), "start": words[i]["start"],
            "end": words[j]["end"], "text": " ".join(x["text"] for x in words[i:j + 1]), "score": round(r, 2),
            "alternatives": [{"words": (words[a]["ref"], words[b]["ref"]), "start": words[a]["start"], "score": round(s, 2),
                              "text": " ".join(x["text"] for x in words[a:b + 1])} for s, a, b in hits[1:]]}


def _sentence(words: list[dict], k: int) -> tuple[int, int]:
    end_re = re.compile(r"[.!?…]$")
    a = k
    while a > 0 and not end_re.search(words[a - 1]["text"]):
        a -= 1
    b = k
    while b < len(words) - 1 and not end_re.search(words[b]["text"]):
        b += 1
    return a, b


# ---------------------------------------------------------------- revise
def _wnum(ref: str) -> tuple[str, int]:
    m = re.fullmatch(r"(c\d+):w0*(\d+)", ref.strip().lower())
    if not m:
        raise ValueError(f"Wort-ID {ref!r} ungültig (z. B. c01:w0120)")
    return m.group(1), int(m.group(2))


def _words_range(spec: str) -> tuple[str, int, int]:
    m = re.fullmatch(r"(c\d+):w0*(\d+)\s*[-–]\s*(?:c\d+:)?w0*(\d+)", spec.strip().lower())
    if not m:
        raise ValueError(f"Wortbereich {spec!r} ungültig (z. B. c01:w0100-w0120)")
    return m.group(1), int(m.group(2)), int(m.group(3))


def apply_ops(base: Cutlist, ops: list[dict], locate) -> tuple[Cutlist, list[str]]:
    """Operations (applied in order; "#NN" always means the numbering of the BASE timeline):
    remove {ref | words}, trim {ref, from_word?, to_word?}, move {ref, after | before}, insert {after | before, clip,
    from_word, to_word, note?}, replace {ref, clip, from_word, to_word}, zoom {ref, zoom}, note {ref, note},
    remove_overlay {ref: "O2"}, add_overlay {overlay fields}, correct {word, text}, beat {after, beat}, add_sfx {cue fields},
    remove_sfx {ref: "S2"}. ref = "#05", timecode
    or quote (resolved via locate)."""
    cl = base.model_copy(deep=True)
    items: list[tuple[int | None, CutItem]] = [(k, it) for k, it in enumerate(cl.items, 1)]  # (base number, item)
    log: list[str] = []

    def pos_of(n: int) -> int:
        for k, (bn, _) in enumerate(items):
            if bn == n:
                return k
        raise KeyError(f"#{n:02d} ist nicht mehr da (schon entfernt oder ersetzt)")

    def item_ref(op: dict, key: str = "ref") -> tuple[int, dict]:
        loc = locate(op[key])
        return loc["item"], loc

    def cut_words(clip: str, a: int, b: int, why: str) -> None:
        """Remove words a..b of clip from every item that contains them (an item may split in two)."""
        hit = False
        k = 0
        while k < len(items):
            bn, it = items[k]
            if it.clip != clip:
                k += 1
                continue
            f, t = int(it.from_word[1:]), int(it.to_word[1:])
            if b < f or a > t:
                k += 1
                continue
            hit = True
            parts = []
            if f < a:
                parts.append(it.model_copy(update={"to_word": f"w{a - 1:04d}", "end_frame": None}))
            if t > b:
                parts.append(it.model_copy(update={"from_word": f"w{b + 1:04d}", "start_frame": None}))
            items[k:k + 1] = [(bn if i == 0 else None, p) for i, p in enumerate(parts)]
            log.append(f"#{bn:02d}: {clip}:w{a:04d}–w{b:04d} entfernt ({why})"
                       + (" – Item geteilt" if len(parts) == 2 else " – Item ganz entfernt" if not parts else ""))
            k += len(parts)
        if not hit:
            raise LookupError(f"{clip}:w{a:04d}–w{b:04d} liegt nicht im Schnitt")

    for op in ops:
        kind = (op.get("op") or "").lower()
        if kind == "remove":
            if op.get("words"):
                c, a, b = _words_range(op["words"])
                cut_words(c, a, b, op.get("why", "Änderungswunsch"))
                continue
            n, loc = item_ref(op)
            if loc["kind"] == "item":
                del items[pos_of(n)]
                log.append(f"#{n:02d} entfernt")
            else:  # a quote or a timecode removes exactly those words (timecode: the whole sentence)
                w0, w1 = (loc.get("sentence") or loc["words"]) if loc["kind"] == "time" else loc["words"]
                c, a = _wnum(w0)
                _, b = _wnum(w1)
                cut_words(c, a, b, f"„{loc.get('sentence_text') or loc['text']}“")
        elif kind == "trim":
            n, _ = item_ref(op)
            k = pos_of(n)
            bn, it = items[k]
            upd = {}
            if op.get("from_word"):
                upd.update(from_word=op["from_word"].split(":")[-1], start_frame=None)
            if op.get("to_word"):
                upd.update(to_word=op["to_word"].split(":")[-1], end_frame=None)
            items[k] = (bn, it.model_copy(update=upd))
            log.append(f"#{n:02d} getrimmt → {upd.get('from_word', it.from_word)}–{upd.get('to_word', it.to_word)}")
        elif kind == "move":
            n, _ = item_ref(op)
            entry = items.pop(pos_of(n))
            target_key = "after" if op.get("after") else "before"
            m, _ = item_ref(op, target_key)
            k = pos_of(m)
            items.insert(k + 1 if target_key == "after" else k, entry)
            log.append(f"#{n:02d} verschoben {'hinter' if target_key == 'after' else 'vor'} #{m:02d}")
        elif kind == "insert":
            new = CutItem(clip=op["clip"], from_word=op["from_word"].split(":")[-1], to_word=op["to_word"].split(":")[-1],
                          note=op.get("note", "eingefügt (Änderungswunsch)"))
            target_key = "after" if op.get("after") else "before"
            if op.get(target_key) in (None, "start", "end"):
                k = len(items) if op.get(target_key) == "end" or target_key == "after" and op.get(target_key) is None else 0
            else:
                m, _ = item_ref(op, target_key)
                k = pos_of(m) + (1 if target_key == "after" else 0)
            items.insert(k, (None, new))
            log.append(f"neu: {new.clip} {new.from_word}–{new.to_word} an Position {k + 1}")
        elif kind == "replace":
            n, _ = item_ref(op)
            k = pos_of(n)
            bn, it = items[k]
            items[k] = (None, CutItem(clip=op["clip"], from_word=op["from_word"].split(":")[-1],
                                      to_word=op["to_word"].split(":")[-1], note=op.get("note", f"ersetzt #{n:02d}")))
            log.append(f"#{n:02d} ersetzt durch {op['clip']} {op['from_word']}–{op['to_word']}")
        elif kind in ("zoom", "note"):
            n, _ = item_ref(op)
            k = pos_of(n)
            bn, it = items[k]
            items[k] = (bn, it.model_copy(update={kind: op[kind]}))
            log.append(f"#{n:02d}: {kind} = {op[kind]}")
        elif kind == "correct":
            cl.corrections = [c for c in cl.corrections if c.word != op["word"]] + [Correction(word=op["word"], text=op["text"])]
            log.append(f"Korrektur {op['word']} → „{op['text']}“")
        elif kind == "beat":
            cl.beats = [b for b in cl.beats if b.after != op["after"]]
            if op.get("beat"):
                cl.beats.append(Beat(after=op["after"], beat=op["beat"]))
            log.append(f"Beat nach {op['after']}: {op.get('beat') or 'entfernt'}")
        elif kind == "remove_overlay":
            m = re.fullmatch(r"o0*(\d+)", str(op["ref"]).strip().lower())
            if not m or not 1 <= int(m.group(1)) <= len(cl.overlays):
                raise KeyError(f"Overlay {op['ref']} unbekannt (O1–O{len(cl.overlays)})")
            cl.overlays[int(m.group(1)) - 1] = None  # type: ignore[call-overload]
            log.append(f"Overlay {op['ref']} entfernt")
        elif kind == "add_overlay":
            ov = Overlay(**{k: v for k, v in op.items() if k != "op"})
            cl.overlays.append(ov)
            log.append(f"Overlay neu: {ov.media} über {ov.from_word}–{ov.to_word}")
        elif kind == "add_sfx":
            cue = SfxCue(**{k: v for k, v in op.items() if k != "op"})
            cl.sfx.append(cue)
            log.append(f"Effekt neu: {cue.file or cue.category} auf {cue.at}")
        elif kind == "remove_sfx":
            m = re.fullmatch(r"s0*(\d+)", str(op["ref"]).strip().lower())
            if not m or not 1 <= int(m.group(1)) <= len(cl.sfx) or cl.sfx[int(m.group(1)) - 1] is None:
                raise KeyError(f"Effekt {op['ref']} unbekannt (S1–S{len(cl.sfx)})")
            cl.sfx[int(m.group(1)) - 1] = None  # type: ignore[call-overload]
            log.append(f"Effekt {op['ref']} entfernt")
        else:
            raise ValueError(f"unbekannte Operation {kind!r} (remove, trim, move, insert, replace, zoom, note, "
                             f"correct, beat, remove_overlay, add_overlay, add_sfx, remove_sfx)")
    cl.items = [it for _, it in items]
    # removing an overlay renumbers the others: effects follow their overlay, or go with it
    renum = {f"O{k}": f"O{sum(1 for o in cl.overlays[:k] if o is not None)}" for k, o in enumerate(cl.overlays, 1) if o is not None}
    gone = {f"O{k}" for k, o in enumerate(cl.overlays, 1) if o is None}
    cues = []
    for s in cl.sfx:
        if s is None:
            continue
        ref = re.sub(r"^O0*", "O", s.at.strip().upper())
        if ref in gone:
            log.append(f"Effekt auf {ref} entfernt (Overlay ist weg)")
            continue
        cues.append(s.model_copy(update={"at": renum[ref]}) if ref in renum else s)
    cl.sfx = cues
    cl.overlays = [o for o in cl.overlays if o is not None]
    return cl, log


def next_revision_name(base_timeline: str, existing: set[str]) -> str:
    stem = re.sub(r"_r\d+$", "", base_timeline)
    n = 2
    while f"{stem}_r{n}" in existing:
        n += 1
    return f"{stem}_r{n}"


# ---------------------------------------------------------------- diff
def _key(it: CutItem) -> tuple:
    return (it.clip, it.from_word, it.to_word)


def diff(old: Cutlist, new: Cutlist, old_s: float, new_s: float) -> list[str]:
    """New / removed / moved / changed items (old numbering #NN → new numbering) and the duration change."""
    ok, nk = [_key(i) for i in old.items], [_key(i) for i in new.items]
    lines = [f"Änderungen gegenüber „{old.timeline_name}“: Dauer {_ts(old_s)} → {_ts(new_s)} ({new_s - old_s:+.2f} s), "
             f"Items {len(ok)} → {len(nk)}"]
    sm = difflib.SequenceMatcher(a=ok, b=nk, autojunk=False)
    same_pos = {i for blk in sm.get_matching_blocks() for i in range(blk.a, blk.a + blk.size)}
    used_new: set[int] = set()
    for i, k in enumerate(ok):
        if k in nk:
            j = nk.index(k)
            used_new.add(j)
            if i not in same_pos:
                nb = new.items[j + 1] if j + 1 < len(new.items) else None
                where = f"jetzt vor {nb.clip} {nb.from_word}" if nb else "jetzt am Ende"
                lines.append(f"  ↕ verschoben: alt #{i + 1:02d} → neu #{j + 1:02d} {k[0]} {k[1]}–{k[2]} ({where})")
            continue
        o = old.items[i]
        cand = [j for j, n in enumerate(new.items) if j not in used_new and n.clip == o.clip
                and int(n.from_word[1:]) <= int(o.to_word[1:]) and int(o.from_word[1:]) <= int(n.to_word[1:])]
        if cand:
            for j in cand:
                used_new.add(j)
                n = new.items[j]
                lines.append(f"  ✎ geändert: #{i + 1:02d} {o.from_word}–{o.to_word} → #{j + 1:02d} {n.from_word}–{n.to_word}")
        else:
            lines.append(f"  − entfernt: #{i + 1:02d} {o.clip} {o.from_word}–{o.to_word}" + (f" ({o.note[:60]})" if o.note else ""))
    for j, n in enumerate(new.items):
        if j not in used_new:
            lines.append(f"  + neu: #{j + 1:02d} {n.clip} {n.from_word}–{n.to_word}" + (f" ({n.note[:60]})" if n.note else ""))
    if len(old.overlays) != len(new.overlays):
        lines.append(f"  Overlays {len(old.overlays)} → {len(new.overlays)}")
    if len(old.sfx) != len(new.sfx):
        lines.append(f"  Sound-Effekte {len(old.sfx)} → {len(new.sfx)}")
    if len(lines) == 1:
        lines.append("  (keine Änderungen an den Items)")
    return lines


def _ts(s: float) -> str:
    m, s = divmod(s, 60)
    return f"{int(m)}:{s:05.2f}"


# ---------------------------------------------------------------- manual changes in Resolve
def timeline_changes(built: Cutlist, plan: Plan, timeline: dict, analyzed: dict, clips: dict) -> dict:
    """Compare V1 of a Resolve timeline with the pieces it was built from; build a cutlist that reproduces it 1:1.
    Returns {"lines": report, "unclear": [...], "cutlist": Cutlist | None, "changed": bool}."""
    v1 = timeline["v1"]
    recs = recs_of(plan.pieces)
    built_p = [(p.clip, p.start_frame, p.frames) for p in plan.pieces]
    lines, unclear = [], []
    status: list[str] = []
    matched: set[int] = set()
    trim_of: dict[int, int] = {}  # V1 index → built piece index it was trimmed from
    for k, it in enumerate(v1):
        if it["clip"] is None:
            status.append("unbekannt")
            unclear.append(f"V1 {k + 1}: „{it['name']}“ ist kein Clip dieses Ordners – bleibt nur in Resolve "
                           f"(Position {it['rec']}, {it['frames']} Frames)")
            continue
        key = (it["clip"], it["src_start"], it["frames"])
        if key in built_p and built_p.index(key) not in matched:
            j = built_p.index(key)
            matched.add(j)
            status.append("gleich")
            continue
        over = [j for j, (c, s, n) in enumerate(built_p) if j not in matched and c == it["clip"]
                and s < it["src_start"] + it["frames"] and it["src_start"] < s + n]
        if over:
            matched.add(over[0])
            status.append("getrimmt")
            trim_of[k] = over[0]
        else:
            status.append("neu")
    removed = [j for j in range(len(built_p)) if j not in matched]
    # moved = unchanged pieces outside the longest increasing run of their original order (removals shift positions,
    # that alone is no move)
    eq = sorted([(k, built_p.index((v1[k]["clip"], v1[k]["src_start"], v1[k]["frames"]))) for k, st in enumerate(status)
                 if st == "gleich"] + list(trim_of.items()))
    keep = set(_lis([j for _, j in eq]))
    for (k, j) in eq:
        if j not in keep:
            status[k] = "verschoben" if status[k] == "gleich" else "getrimmt + verschoben"
    cnt = {s: status.count(s) for s in ("gleich", "verschoben", "getrimmt", "getrimmt + verschoben", "neu", "unbekannt")}
    lines.append(f"Timeline „{timeline['name']}“ (V1: {len(v1)} Clips) gegen „{built.timeline_name}“ ({len(built_p)} Teilstücke): "
                 + ", ".join(f"{v} {k}" for k, v in cnt.items() if v) + (f", {len(removed)} entfernt" if removed else ""))
    for k, st in enumerate(status):
        if st in ("verschoben", "getrimmt", "getrimmt + verschoben", "neu"):
            it = v1[k]
            lines.append(f"  {'↕' if st == 'verschoben' else '+' if st == 'neu' else '✎'} {st}: V1 {k + 1} {it['clip']} "
                         f"f{it['src_start']}–f{it['src_start'] + it['frames'] - 1} an {it['rec']}")
    for j in removed:
        p = plan.pieces[j]
        lines.append(f"  − entfernt: Teilstück von #{p.item:02d} ({p.clip} f{p.start_frame}–f{p.end_frame - 1}): „{p.text[:70]}“")
    changed = any(s != "gleich" for s in status) or bool(removed) or len(v1) != len(built_p)
    # overlays / graphics on upper tracks: compared by count and position, not adopted automatically
    up_now = sum(len(v) for v in (timeline.get("upper") or {}).values())
    up_built = len(plan.overlays) + len(plan.graphics)
    if up_now != up_built:
        unclear.append(f"Obere Spuren: {up_now} Clips statt {up_built} gebauter Overlays/Grafiken – nicht automatisch "
                       f"übernommen (bitte sagen, welche bleiben sollen)")
    # cutlist that reproduces V1: one item per clip, explicit frames, no tightening, zoom as in Resolve
    items = []
    for k, (it, st) in enumerate(zip(v1, status)):
        if st == "unbekannt":
            continue
        at = analyzed[it["clip"]]
        fps = it["fps"]
        a, b = it["src_start"], it["src_start"] + it["frames"]
        full, partial = [], []
        for e in at.entries:
            if e.id[0] != "w" or e.kind not in ("word", "filler"):
                continue
            ws, we = e.start_s * fps, e.end_s * fps
            if ws >= a - 0.5 and we <= b + 0.5:
                full.append(e)
            elif min(we, b) > max(ws, a):
                partial.append(e)
        for e in (partial if st not in ("gleich", "verschoben") else []):  # only words cut by the manual edit
            unclear.append(f"V1 {k + 1}: Wort „{e.text}“ ({it['clip']}:{e.id}) angeschnitten – Schnitt bleibt framegenau "
                           f"wie in Resolve")
        if not full:
            unclear.append(f"V1 {k + 1}: {it['clip']} f{a}–f{b - 1} enthält kein vollständiges Wort – als Cutlist-Item nicht "
                           f"darstellbar, bleibt nur in Resolve")
            continue
        items.append(CutItem(clip=it["clip"], from_word=full[0].id, to_word=full[-1].id, start_frame=f"{it['clip']}:f{a:04d}",
                             end_frame=f"{it['clip']}:f{b - 1:04d}", zoom=round(it.get("zoom") or 1.0, 3),
                             note=f"aus Resolve übernommen ({st})"))
    cl = None
    if items:
        cl = built.model_copy(deep=True)
        cl.pass_ = None
        cl.base_cutlist = None
        cl.items = items
        cl.item_changes = []
        cl.punch_in = None
        cl.options = cl.options.model_copy(update={"tighten_gaps_over_ms": 10 ** 6, "cut_fillers": False,
                                                   "motion_aware_cuts": False, "keep_pause_ms": 10 ** 6})
    return {"lines": lines, "unclear": unclear, "cutlist": cl, "changed": changed, "status": status, "removed": removed}


def _lis(seq: list[int]) -> list[int]:
    """Longest strictly increasing subsequence (values)."""
    import bisect
    tails, idx, prev = [], [], [-1] * len(seq)
    for i, x in enumerate(seq):
        k = bisect.bisect_left(tails, x)
        if k == len(tails):
            tails.append(x)
            idx.append(i)
        else:
            tails[k] = x
            idx[k] = i
        prev[i] = idx[k - 1] if k else -1
    out, i = [], idx[-1] if idx else -1
    while i >= 0:
        out.append(seq[i])
        i = prev[i]
    return out[::-1]
