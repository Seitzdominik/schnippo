"""`get_edit_context`: everything Claude needs for the editorial decision, segment-wise and compact."""

from __future__ import annotations

from .formatting import ts
from .models import Clip
from .retakes import Edge, Group
from .script import ScriptLine
from .segments import Segment

LEGEND = ("Legende: c01:s003 Segment · w0018–w0027 Wortbereich · @Start · Dauer · ⏸3.1 Pause davor (s) · {?} stimmhafte "
          "Lücke (äh/hm?) · ⚠abgebr. endet ohne Satzzeichen vor langer Pause · ⚠gemurmelt? Wörter mit Konfidenz 0 · "
          "↺s002 0.78 ähnlich zu früherem Segment · ⚠vor Retake-Marker: danach „nochmal“/Klatscher · [L07? 0.82] Skript-Kandidat. Wortgenau: get_transcript(clip_id, from_word, to_word).")
FLAG = {"aborted": "⚠abgebr.", "mumbled?": "⚠gemurmelt?"}


def _flag(f: str) -> str | None:
    if f in FLAG:
        return FLAG[f]
    if f.startswith("marker:"):
        return f"⛔Retake-Marker „{f.split(':', 1)[1]}“ (raus)"
    if f.startswith("retake_before:"):
        return f"⚠vor Retake-Marker {f.split(':', 1)[1]} – vermutlich verworfen"
    return None


def display_res(c: Clip) -> str:
    w, h = (c.height, c.width) if abs(c.rotation) % 180 == 90 else (c.width, c.height)
    return f"{w}x{h} ({'Hochformat' if h > w else 'Querformat'})"


def segment_line(s: Segment, back: list[Edge]) -> str:
    parts = [f"{s.ref}{' ' + s.speaker if s.speaker else ''} {s.from_word}–{s.to_word} @{ts(s.start_s)} {s.duration_s:.1f}s"]
    if s.pause_before_s >= 0.7:
        parts.append(f"⏸{s.pause_before_s:.1f}")
    if s.script:
        parts.append("[" + " ".join(f"{lid}? {sc:.2f}" for lid, sc in s.script[:2]) + "]")
    parts.append(f'"{s.text}"')
    parts += [x for x in (_flag(f) for f in s.flags) if x]
    parts += [f"↺{e.a if e.b == s.id else e.b} {e.score:.2f}" for e in back]
    return " ".join(parts)


def render(clips: list[tuple[Clip, list[Segment], list[Edge], list[Group]]], script: list[ScriptLine] | None,
           stills_lines: list[str], folder: str, guide: str | None) -> str:
    n_seg = sum(len(s) for _, s, _, _ in clips)
    out = [f"EDIT-KONTEXT | {folder} | {len(clips)} Clip(s), {n_seg} Segmente | "
           + (f"Skript: {len(script)} Zeilen" if script else "ohne Skript → Reihenfolge der Aufnahme ist maßgeblich"),
           LEGEND]
    for clip, segs, edges, groups in clips:
        out.append(f"\n{clip.id} {clip.name} | {ts(clip.duration_s)} | {clip.fps:g}fps | {display_res(clip)} | {len(segs)} Segmente")
        for s in segs:
            back = [e for e in edges if e.b == s.id]  # links to earlier segments only
            out.append(segment_line(s, back))
        if groups:
            out.append("Retake-Kandidaten (Hinweise, können unvollständig/falsch sein):")
            out += [f"{clip.id}:{g.id} = {', '.join(g.members)} (Ø {g.score:.2f})" for g in groups]
            out.append("Bei knapper Entscheidung: get_take_frames(\"<Gruppe>\") zeigt die Versuche nebeneinander.")
    if script:
        out.append("\nSkript:")
        covered = {lid for _, segs, _, _ in clips for s in segs for lid, sc in s.script[:1] if sc >= 0.7}
        sec = None
        for ln in script:
            if ln.section != sec:
                sec = ln.section
                out.append(f"## {sec}" if sec else "## (ohne Abschnitt)")
            out.append(f"{ln.id} \"{ln.text}\"" + ("" if ln.id in covered else "  ⚠ kein sicherer Treffer"))
    if stills_lines:
        out.append("\n" + "\n".join(stills_lines))
    if guide:
        out.append("\n--- Schnitt-Leitfaden ---\n" + guide.strip())
    return "\n".join(out)


def paginate(clips: list[tuple], page_size: int) -> list[list[tuple[str, int]]]:
    """Pages over all segments of all clips in recording order: list of [(clip_id, segment index), ...]."""
    flat = [(clip.id, k) for clip, segs, _, _ in clips for k in range(len(segs))]
    return [flat[i:i + page_size] for i in range(0, len(flat), page_size)] or [[]]


def render_overview(clips: list[tuple], script, stills_lines: list[str], folder: str, guide: str | None,
                    pages: list[list[tuple[str, int]]]) -> str:
    seg_by = {clip.id: segs for clip, segs, _, _ in clips}
    total_raw = sum(c.duration_s for c, *_ in clips)
    n_seg = sum(len(s) for _, s, _, _ in clips)
    out = [f"ÜBERSICHT | {folder} | {len(clips)} Clip(s), {ts(total_raw)} Rohmaterial, {n_seg} Segmente, {len(pages)} Seite(n) | "
           + (f"Skript: {len(script)} Zeilen" if script else "ohne Skript → Reihenfolge der Aufnahme ist maßgeblich"),
           "Ablauf: erst diese Übersicht, dann get_edit_context(page=N) Seite für Seite; pro Seite Items/Rejected festlegen, "
           "am Ende merge_cutlists → validate_cutlist → complete_cut."]
    out.append("Clips:")
    for clip, segs, edges, groups in clips:
        out.append(f"  {clip.id} {clip.name} | {ts(clip.duration_s)} | {clip.fps:g}fps | {display_res(clip)} | {len(segs)} Segmente, "
                   f"{len(groups)} Retake-Gruppen")
    out.append("Seiten:")
    for k, pg in enumerate(pages, 1):
        if not pg:
            continue
        (c0, i0), (c1, i1) = pg[0], pg[-1]
        a, b = seg_by[c0][i0], seg_by[c1][i1]
        out.append(f"  Seite {k}: {a.ref}–{b.ref} ({len(pg)} Segmente) @{ts(a.start_s)}–{ts(b.end_s)}"
                   + (f" | {c0}→{c1}" if c0 != c1 else ""))
    page_of = {key: k for k, pg in enumerate(pages, 1) for key in pg}
    groups_lines = []
    for clip, segs, edges, groups in clips:
        idx = {s.id: n for n, s in enumerate(segs)}
        for g in groups:
            pgs = sorted({page_of[(clip.id, idx[m])] for m in g.members})
            groups_lines.append(f"  {clip.id}:{g.id} = {', '.join(g.members)} (Ø {g.score:.2f})"
                                + (f" · Seiten {', '.join(map(str, pgs))}" if len(pages) > 1 else ""))
    if groups_lines:
        out.append("Retake-Kandidaten (Hinweise):")
        out += groups_lines
    if script:
        covered = {lid for _, segs, _, _ in clips for s in segs for lid, sc in s.script[:1] if sc >= 0.7}
        miss = [ln.id for ln in script if ln.id not in covered]
        out.append(f"Skriptabdeckung: {len(script) - len(miss)}/{len(script)} Zeilen mit sicherem Treffer"
                   + (f"; ohne: {', '.join(miss)}" if miss else ""))
    if stills_lines:
        out.append("\n".join(stills_lines))
    if guide:
        out.append("\n--- Schnitt-Leitfaden ---\n" + guide.strip())
    return "\n".join(out)


def render_page(clips: list[tuple], pages: list, page: int, script) -> str:
    if not 1 <= page <= len(pages):
        raise ValueError(f"Seite {page} gibt es nicht (1–{len(pages)})")
    pg = pages[page - 1]
    want = set(pg)
    page_of = {key: k for k, p in enumerate(pages, 1) for key in p}
    out = [f"EDIT-KONTEXT Seite {page}/{len(pages)} ({len(pg)} Segmente)", LEGEND]
    for clip, segs, edges, groups in clips:
        sel = [(n, s) for n, s in enumerate(segs) if (clip.id, n) in want]
        if not sel:
            continue
        out.append(f"\n{clip.id} {clip.name} | {ts(clip.duration_s)} | {clip.fps:g}fps")
        for n, s in sel:
            out.append(segment_line(s, [e for e in edges if e.b == s.id]))
        idx = {s.id: n for n, s in enumerate(segs)}
        here = [g for g in groups if any((clip.id, idx[m]) in want for m in g.members)]
        if here:
            out.append("Retake-Kandidaten mit Versuchen auf dieser Seite:")
            for g in here:
                other = sorted({page_of[(clip.id, idx[m])] for m in g.members} - {page})
                out.append(f"{clip.id}:{g.id} = {', '.join(g.members)} (Ø {g.score:.2f})"
                           + (f" · weitere Versuche auf Seite {', '.join(map(str, other))}" if other else ""))
    if script and page == len(pages):
        out.append("(Skriptzeilen: siehe Übersicht)")
    return "\n".join(out)
