"""Quality control (guides/04_polish.md) – on the plan (validate_cutlist hints) and on a timeline read back from Resolve
(run_qc). Automatable checks only; every result says what was checked and what was not.
"""

from __future__ import annotations

import re

from .formatting import ts

APP_MARKS = re.compile(r"capcut|tiktok|inshot|instagram|snapchat|kinemaster|videoleap|splice|vn video|vllo|picsart|canva",
                       re.I)
SENTENCE_END = re.compile(r"[.!?…]$")


def _recs(pieces) -> list[int]:
    out, rec = [], 0
    for pc in pieces:
        out.append(rec)
        rec += pc.frames
    return out


def max_zoom(clip, prof) -> float:
    from .profiles import max_zoom_for
    return max_zoom_for(prof, clip.width, clip.height)


def beat_lines(plan, total_s: float, prof, cl) -> list[str]:
    """FC3: long formats need breathing room after key statements; short formats at most 1–2."""
    n = len(plan.beats)
    long_form = prof.format in ("youtube", "course")
    if not n:
        if long_form and cl.pass_ == "fine":
            return ["  ⚠ Keine Kernaussagen markiert (FC3, Pflicht in langen Formaten): beats setzen, etwa eine je 30–60 s"]
        return []
    keys = sum(1 for b in plan.beats if b["kind"] == "key")
    short = [b for b in plan.beats if b["orig_s"] is not None and b["actual_s"] < 0.75 * b["target_s"]
             and b["orig_s"] >= b["target_s"]]
    line = f"  Beats: {n} ({keys} key, {n - keys} section), im Mittel alle {total_s / n:.0f} s"
    if long_form:
        line += " (Richtwert 30–60 s)" + (" – ⚠ zu wenige" if total_s / n > 90 else "")
    elif n > 2:
        line += " – ⚠ für kurze Formate höchstens 1–2"
    return [line] + [f"  ⚠ Beat nach {b['word']}: Pause nur {b['actual_s']:.2f} s, Original hätte {b['orig_s']:.2f} s" for b in short]


def change_points(frames_list: list[tuple[int, int]], zoom_changes: list[int], overlays: list[tuple[int, int]],
                  total: int) -> list[int]:
    """Visual changes = every cut (also jump cuts), zoom changes, overlay in/out."""
    pts = {r for r, _ in frames_list[1:]} | set(zoom_changes)
    for a, b in overlays:
        pts |= {a, b}
    return sorted(p for p in pts if 0 < p < total)


def tempo_lines(points: list[int], total: int, fps: float, prof) -> list[str]:
    edges = [0] + points + [total]
    gaps = [(b - a, a) for a, b in zip(edges, edges[1:])]
    mean = total / fps / max(1, len(gaps))
    lo, hi = prof.change_every_s
    long = [(g, a) for g, a in gaps if g / fps > prof.max_unchanged_s]
    out = [f"Tempo: {len(points)} visuelle Wechsel, im Mittel alle {mean:.1f} s (Richtwert {lo:g}–{hi:g} s)"
           + ("" if lo <= mean <= hi else " – außerhalb, Richtwert, kein Zwang")]
    for g, a in long[:6]:
        out.append(f"  ⚠ {g / fps:.1f} s ohne Wechsel ab {ts(a / fps)} (Richtwert max. {prof.max_unchanged_s:g} s)")
    return out


def plan_checks(cl, plan, clips: dict, prof, analyzed: dict | None = None) -> list[str]:
    """Hints for validate_cutlist, by pass (rough: hook/runtime; fine: tempo/zoom; broll: overlay rules)."""
    if not plan.pieces:
        return []
    out = ["Prüfungen (Leitfaden):"]
    fps = clips[plan.pieces[0].clip].resolve_fps or clips[plan.pieces[0].clip].fps
    total = sum(p.frames for p in plan.pieces)
    total_s = total / fps
    lo, hi = (cl.reframe.min_s, cl.reframe.max_s) if cl.reframe else prof.runtime_s
    out.append(f"  Laufzeit {ts(total_s)} " + ("✓" if lo <= total_s <= hi else f"⚠ außerhalb {ts(lo)}–{ts(hi)} ({prof.format})"))
    first = plan.pieces[0]
    at = (analyzed or {}).get(first.clip)
    w0 = next((e for e in at.entries if e.id == first.word_ids[0]), None) if at is not None and first.word_ids else None
    if w0 is not None:
        lead = max(0, round(w0.start_s * fps) - first.start_frame)
        out.append(f"  Hook: erstes Wort ab Frame {lead} ({lead / fps * 1000:.0f} ms) "
                   + ("✓" if lead <= 4 else "⚠ Vorlauf > 4 Frames – start_frame näher ans erste Wort (Sprache ab dem ersten Frame)"))
    flash = [k + 1 for k, p in enumerate(plan.pieces) if p.frames < prof.flash_frames]
    if flash:
        out.append(f"  ⚠ Flash-Frames: Teilstück(e) {flash} kürzer als {prof.flash_frames} Frames")
    if cl.pass_ in (None, "fine", "broll", "polish"):
        recs = _recs(plan.pieces)
        zc = [recs[k] for k in range(1, len(plan.pieces)) if plan.pieces[k].zoom != plan.pieces[k - 1].zoom]
        jumps = [k for k in range(1, len(plan.pieces)) if plan.pieces[k].clip == plan.pieces[k - 1].clip]
        zj = [k for k in jumps if plan.pieces[k].zoom != plan.pieces[k - 1].zoom]
        if any(p.zoom != 1.0 for p in plan.pieces):
            out.append(f"  Punch-ins: {len(zj)} von {len(jumps)} Jump-Cuts mit Zoomwechsel"
                       + (" – ⚠ Zoom auf jedem Schnitt" if jumps and len(zj) == len(jumps) and len(jumps) >= 4 else ""))
            seen = set()
            for p in plan.pieces:
                mz = max_zoom(clips[p.clip], prof)
                if p.zoom > mz + 1e-6 and p.item not in seen and not p.fill:
                    seen.add(p.item)
                    out.append(f"  ⚠ Zoom {p.zoom * 100:.0f} % auf #{p.item:02d} über {mz * 100:.0f} % für diese Quellauflösung – "
                               f"das Bild wird weich")
        ov = [(o.tl_start, o.tl_end) for o in plan.overlays]
        out += ["  " + x for x in tempo_lines(change_points([(r, 0) for r in recs], zc, ov, total), total, fps, prof)]
    if cl.pass_ in (None, "fine", "broll", "polish", "motion") and plan.pieces:
        out += beat_lines(plan, total / fps, prof, cl)
    if plan.overlays:
        last_item = max(p.item for p in plan.pieces)
        recs = _recs(plan.pieces)
        from .cutlist import cta_start as _cta
        cta_start = _cta(plan.pieces, recs, last_item)
        for o in plan.overlays:
            d = o.frames / fps
            tag = f"O{o.index} {o.media}"
            if o.tl_start < prof.hook_s * fps and prof.format != "commercial":  # commercial: a picture may be the hook
                out.append(f"  ⚠ {tag} beginnt im Hook (erste {prof.hook_s:g} s) – Gesicht wirkt dort")
            if o.tl_end > cta_start and not getattr(o, "tail", False):
                out.append(f"  ⚠ {tag} liegt über dem letzten Satz (CTA) – dort Gesicht")
            if d < prof.broll_min_s - 1e-6 or d > prof.broll_max_s + 1e-6:
                out.append(f"  Hinweis {tag}: {d:.1f} s (Richtwert {prof.broll_min_s:g}–{prof.broll_max_s:g} s; Detailbilder ≥ 3 s)")
        cover = sum(o.frames for o in plan.overlays) / total
        if prof.broll_coverage[1]:
            c0, c1 = prof.broll_coverage
            out.append(f"  B-Roll-Abdeckung {cover * 100:.0f} % (Richtwert {c0 * 100:.0f}–{c1 * 100:.0f} %, schwach belegt)")
        elif prof.broll_every_s[1]:
            every = total_s / len(plan.overlays)
            out.append(f"  B-Roll: {len(plan.overlays)} Einblendung(en), etwa alle {every:.0f} s (Richtwert "
                       f"{prof.broll_every_s[0]:g}–{prof.broll_every_s[1]:g} s; ohne passendes Material lieber keine)")
    return out


def watermark_hints(paths: list[str]) -> list[str]:
    """Metadata only (encoder/handler/comment/title tags); the picture itself is not checked."""
    from .media import probe
    out = []
    for path in paths:
        try:
            meta = probe(path)
        except Exception:
            continue
        tags = dict(meta.get("format", {}).get("tags", {}))
        for st in meta.get("streams", []):
            tags.update({f"{st.get('codec_type')}:{k}": v for k, v in (st.get("tags") or {}).items()})
        hits = sorted({f"{k}={v}" for k, v in tags.items() if isinstance(v, str) and APP_MARKS.search(v)})
        if hits:
            out.append(f"{path.rsplit('/', 1)[-1]}: {', '.join(hits)[:200]}")
    return out


def run(tl: dict, clips: dict, analyzed: dict, prof, master: str | None, built_plan=None, audio: dict | None = None,
        graphics: list | None = None, acoustics: dict | None = None, reframe_cfg=None, face_first: bool | None = None) -> dict:
    """Checks on a timeline read back with resolve_bridge.read_timeline. Returns {"ok", "lines", "counts"}."""
    lines, bad, warn = [], 0, 0

    def res(ok: bool | None, text: str):
        nonlocal bad, warn
        mark = "✅" if ok else ("⚠️" if ok is None else "❌")
        if ok is False:
            bad += 1
        elif ok is None:
            warn += 1
        lines.append(f"{mark} {text}")

    v1 = tl["v1"]
    fps = tl.get("fps") or 30.0
    total = tl["frames"]
    # 1 flash frames
    flash = [k + 1 for k, it in enumerate(v1) if it["frames"] < prof.flash_frames]
    upper_flash = [f"V{t} {n}" for t, items in tl["upper"].items() for n, _, d in items if d < prof.flash_frames]
    res(not flash and not upper_flash, "Keine Flash-Frames (Stücke < %d Frames)" % prof.flash_frames
        + (f": V1-Stück {flash}" if flash else "") + (f"; {', '.join(upper_flash)}" if upper_flash else ""))
    # 2 gaps: picture and sound
    holes, pos = [], 0
    for it in v1:
        if it["rec"] > pos:
            holes.append((pos, it["rec"]))
        pos = max(pos, it["rec"] + it["frames"])
    if pos < total:
        holes.append((pos, total))
    res(not holes, "Keine Lücken im Bild (V1)" + (": " + ", ".join(f"{ts(a / fps)}–{ts(b / fps)}" for a, b in holes) if holes else ""))
    cover = sorted((a, a + d) for t in tl["audio"].values() if t["enabled"] for a, d in t["items"])
    silent, pos = [], 0
    for a, b in cover:
        if a > pos + 1:
            silent.append((pos, a))
        pos = max(pos, b)
    if pos < total - 1:
        silent.append((pos, total))
    res(not silent, "Keine Lücken ohne Ton (aktive Audiospuren)"
        + (": " + ", ".join(f"{ts(a / fps)}–{ts(b / fps)}" for a, b in silent[:5]) if silent else ""))
    # 3 cut words
    cut_words = []
    for k, it in enumerate(v1):
        at = analyzed.get(it["clip"]) if it["clip"] else None
        if at is None:
            continue
        cf = it["fps"] or fps
        for edge, side in ((it["src_start"], "Anfang"), (it["src_start"] + it["frames"], "Ende")):
            t = edge / cf
            for w in at.entries:
                if w.id[0] == "w" and w.kind == "word" and w.start_s + 1 / cf < t < w.end_s - 1 / cf:
                    cut_words.append(f"Stück {k + 1} {side} in {it['clip']}:{w.id} „{w.text}“")
    res(not cut_words, "Keine angeschnittenen Wörter" + (": " + "; ".join(cut_words[:5]) if cut_words else ""))
    # 3b hard edges: the last/first 10 ms of every piece should be close to the noise floor (a hint: connected speech
    # sometimes leaves no quiet point; the 2-frame crossfade softens what remains)
    if acoustics:
        from . import edges as ed
        hard = []
        for it in v1:
            ac = acoustics.get(it["clip"]) if it["clip"] else None
            if ac is None:
                continue
            cf = it["fps"] or fps
            for frame, side, at_tl in ((it["src_start"], "start", it["rec"]), (it["src_start"] + it["frames"], "end", it["rec"] + it["frames"])):
                if not ed.is_quiet(ac, frame, cf, side, prof.edge_db):
                    hard.append(f"{ts(at_tl / fps)} ({'Anfang' if side == 'start' else 'Ende'}, "
                                f"{ed.edge_level(ac, frame, cf, side) - ac.floor_db:+.0f} dB)")
        res(None if hard else True, f"Keine harten Kanten im Ton (Schwelle Rauschboden + {prof.edge_db:g} dB)"
            + (f": {len(hard)} Stelle(n): " + ", ".join(hard[:10]) + (" …" if len(hard) > 10 else "") if hard else ""))
    # 4 zoom on every cut
    jumps = [k for k in range(1, len(v1)) if v1[k]["clip"] and v1[k]["clip"] == v1[k - 1]["clip"]]
    zj = [k for k in jumps if abs(v1[k]["zoom"] - v1[k - 1]["zoom"]) > 1e-3]
    if any(abs(it["zoom"] - 1.0) > 1e-3 for it in v1):
        every = bool(jumps) and len(zj) == len(jumps) and len(jumps) >= 4
        res(not every, f"Nicht auf jedem Schnitt ein Zoom ({len(zj)} von {len(jumps)} Jump-Cuts mit Zoomwechsel)")
    else:
        res(True, "Nicht auf jedem Schnitt ein Zoom (keine Punch-ins)")
    # 5 frame rate
    rb = tl["readback"]
    want = (clips[master].resolve_fps or clips[master].fps) if master else fps
    rates = {k: rb.get(k) for k in ("timeline_fps", "timeline_playback_fps")}
    rate_ok = all(v is None or abs(v - want) < 0.005 for v in rates.values()) and rates["timeline_fps"] is not None
    res(rate_ok, f"Framerate: Timeline {rates['timeline_fps']} / Wiedergabe "
        f"{rates['timeline_playback_fps'] if rates['timeline_playback_fps'] is not None else 'nicht gemeldet (eigene Einstellungen)'}"
        f" = Material {want:g}")
    # 6 duration
    if built_plan is not None:
        exp = sum(p.frames for p in built_plan.pieces)
        res(exp == total, f"Dauer {ts(total / fps)} ({total} Frames) = Cutlist {ts(exp / fps)} ({exp} Frames)")
    else:
        res(None, f"Dauer {ts(total / fps)} ({total} Frames) – keine gespeicherte Cutlist zum Vergleich")
    # 7 a/v sync (linked audio has the video item's position and length)
    off = []
    for k, it in enumerate(v1):
        la = it["linked_audio"]
        a1 = [x for x in tl["audio"].get(1, {}).get("items", []) if x[0] == it["rec"]]
        cand = la or a1
        if not cand or (cand[0][0], cand[0][1]) != (it["rec"], it["frames"]):
            off.append(k + 1)
    res(not off, "A/V-Sync: Ton jedes Stücks an Position und Länge des Bildes" + (f" – abweichend: Stück {off[:8]}" if off else ""))
    # 8 audio loudness (optional render measurement)
    if audio is not None:
        lufs, tp = audio.get("lufs"), audio.get("true_peak")
        lo, hi = prof.lufs_range
        res(lufs is not None and lo <= lufs <= hi and tp is not None and tp <= prof.true_peak_max,
            f"Lautheit {lufs} LUFS (Ziel {prof.target_lufs:g}, {lo:g} bis {hi:g}) / True Peak {tp} dBTP (≤ {prof.true_peak_max:g})")
    # 9 overlay/graphic edges vs. cuts (read back from the timeline): no slivers, not 1–margin frames next to a cut
    cuts = sorted({0, total} | {it["rec"] for it in v1} | {it["rec"] + it["frames"] for it in v1})
    sliver = round(getattr(prof, "sliver_s", 0.5) * fps)
    margin = getattr(prof, "cover_margin_frames", 4)
    near = []
    for t, items in tl["upper"].items():
        for name, a, d in items:
            for edge, side in ((a, "Anfang"), (a + d, "Ende")):
                dist = min(abs(edge - c) for c in cuts)
                if 0 < dist < max(sliver, margin + 1):
                    near.append(f"V{t} {name[:24]} {side} {dist} F neben einem Schnitt")
    if tl["upper"]:
        res(not near, "Overlay-/Grafik-Kanten sauber an Schnitten (keine Splitter < "
            f"{sliver} F)" + (": " + "; ".join(near[:5]) if near else ""))
    # 10 graphics: clearance to the head, safe zone, no two graphics overlapping (from the build's placement report)
    if graphics:
        bad_gap = [f"G{g['index']} {g['min_gap']} px" for g in graphics if g.get("min_gap") is not None
                   and g["min_gap"] < (g.get("clearance") or 48) - 0.5]
        res(not bad_gap, "Grafiken: Abstand zum Kopf ≥ Minimum ("
            + ", ".join(f"G{g['index']} {g.get('min_gap')} px" for g in graphics) + f"; Minimum {graphics[0].get('clearance')} px)"
            + (" – zu knapp: " + ", ".join(bad_gap) if bad_gap else ""))
        res(all(g.get("safe_ok") for g in graphics), "Grafiken: sichtbare Pixel in der sicheren Zone"
            + ("" if all(g.get("safe_ok") for g in graphics) else ": " + ", ".join(f"G{g['index']}" for g in graphics if not g.get("safe_ok"))))
        pads = [g for g in graphics if g.get("padding")]
        if pads:
            thin = [f"G{g['index']}" for g in pads if not g["padding"]["ok"]]
            res(not thin, "Grafiken: Innenabstand ≥ Minimum (" + ", ".join(
                f"G{g['index']} {g['padding']['left']}/{g['padding']['right']}/{g['padding']['top']}/{g['padding']['bottom']} px"
                for g in pads) + f"; Minimum {pads[0]['padding']['min_x']:.0f} seitlich, {pads[0]['padding']['min_y']:.0f} oben/unten)"
                + (" – zu knapp: " + ", ".join(thin) if thin else ""))
        clash = []
        for i, g in enumerate(graphics):
            for o in graphics[i + 1:]:
                t_over = g["tl_start"] < o["tl_start"] + o["frames"] and o["tl_start"] < g["tl_start"] + g["frames"]
                b1, b2 = g.get("bbox"), o.get("bbox")
                if t_over and b1 and b2 and b1[0] < b2[2] and b2[0] < b1[2] and b1[1] < b2[3] and b2[1] < b1[3]:
                    clash.append(f"G{g['index']}/G{o['index']}")
        res(not clash, "Grafiken überlappen sich nicht" + (": " + ", ".join(clash) if clash else ""))
    # 10a reel from a long version: crop, edges, face, resolution, hook
    if built_plan is not None and built_plan.reframe and reframe_cfg is not None:
        from . import reframe as _rf
        for ok, text in _rf.qc_lines(tl, built_plan, clips, analyzed, reframe_cfg, face_first):
            res(ok, text)
    # 10b sound effects: read back from the SFX track, positions and levels against the build, rules of guides/06
    sfx_items = tl.get("sfx") or []
    placed = sorted(built_plan.sfx, key=lambda s: s.tl_start) if built_plan is not None else []
    if sfx_items or placed:
        from . import sfx as _sfx
        off = [f"S{s.index}" for s, it in zip(placed, sfx_items) if s.tl_start != it["rec"] or abs(s.volume_db - it["volume"]) > 0.05]
        same = len(sfx_items) == len(placed) and not off
        res(same, f"SFX-Spur: {len(sfx_items)} Effekt(e) an Position und Pegel des Plans"
            + ("" if same else f" – Plan {len(placed)}, abweichend: {', '.join(off) or 'Anzahl'}"))
        if placed and len(sfx_items) == len(placed):
            ctx = _sfx.context(built_plan, analyzed, fps, prof)
            found = _sfx.rules(_sfx.cues_of(placed, fps, [it["rec"] for it in sfx_items]), ctx, fps,
                               built_plan.sfx_info.get("limit", 5), prof.format in ("reel", "commercial"))
            hard = [t for h, t in found if h]
            res(not hard, f"SFX-Regeln: Anzahl ≤ {built_plan.sfx_info.get('limit', 5)}, Abstand ≥ {_sfx.MIN_GAP_S:g} s, nicht im Hook-Satz/CTA, "
                "nicht auf jedem Schnitt" + (": " + "; ".join(hard[:5]) if hard else ""))
            for _, text in [f for f in found if not f[0]][:5]:
                res(None, f"SFX: {text}")
            lines.append("ℹ️ SFX: Ernste oder emotionale Momente prüft nur das Ohr")
    # 11 watermarks (metadata only)
    paths = sorted({clips[it["clip"]].path for it in v1 if it["clip"]})
    marks = watermark_hints(paths)
    res(None if marks else True, "Keine Wasserzeichen-Hinweise in den Metadaten" + (": " + "; ".join(marks) if marks else "")
        + " (Bildinhalt nicht automatisch geprüft)")
    foreign = [it["name"] for it in v1 if not it["clip"]]
    if foreign:
        res(None, f"{len(foreign)} V1-Clip(s) nicht aus dem eingelesenen Ordner (nicht geprüft): {', '.join(foreign[:4])}")
    return {"ok": bad == 0, "lines": lines, "counts": {"fehler": bad, "hinweise": warn}}
