"""16:9 material in a 9:16 timeline (Phase 10). Everything stays a property of the timeline items, nothing is rendered.

Measured on 21.1.2 (white cross in a UHD and an HD clip, 1080×1920 timeline):
  * without further ado a clip is fitted with black bars; timelineInputResMismatchBehavior = scaleToCrop is accepted and ignored;
  * item property Scaling = SCALE_FILL fills the frame, ZoomX/Y stay relative to that (zoom about the centre);
  * Pan moves displayed width / timeline width px per unit (UHD and HD: 3.16 px), Tilt 1 px per unit (Tilt + = image up);
  * there is no keyframe access to Pan/Zoom in the scripting API, Fusion keyframes on clips have no effect in the render (Phase 6):
    a moving head is followed by splitting the item at a word gap.
"""

from __future__ import annotations

from .cutlist import first_piece

import numpy as np

MARGIN = 0.06  # head stays this far from the left and right edge (share of the width)
EYES_Y = 1 / 3  # eyes in the upper third
MIN_PIECE_S = 1.0
HEAD = {"up": 0.35, "side": 0.08, "down": 0.05}  # the crop must hold the face with a little room; the box around hair and ears (graphics) is wider and may touch the edge
SOFT_LIMIT = 1.25  # above this many output px per source px a picture looks soft
FRAMED_RATIO = {"1:1": 1.0, "4:5": 1.25}  # height / width of the window of the framed layout


def display(clip) -> tuple[int, int]:
    return (clip.height, clip.width) if abs(clip.rotation) % 180 == 90 else (clip.width, clip.height)


def scale(clip, W: int, H: int) -> float:
    """Output px per source px at Scaling = Fill, zoom 1."""
    sw, sh = display(clip)
    return max(W / sw, H / sh)


def upscales(clip, W: int, H: int) -> bool:
    """Would the full 9:16 picture need more pixels than the source has? Then the framed layout is the better offer."""
    return scale(clip, W, H) > 1.0


def framed_height(clips: list, W: int, ratio: float) -> int:
    """Height of the window: the ratio asks for it, no source may be enlarged to reach it."""
    return min([round(W * ratio)] + [display(c)[1] for c in clips])


def window(height: int, W: int, H: int) -> tuple[int, int, int, int]:
    """x, y, width, height of the video in the frame."""
    return 0, (H - height) // 2, W, height


def pan_unit(clip, W: int, H: int) -> float:
    return display(clip)[0] * scale(clip, W, H) / W


def to_out(x: float, y: float, clip, pc, W: int, H: int) -> tuple[float, float]:
    """Source px → timeline px for a filled item."""
    sw, sh = display(clip)
    s = scale(clip, W, H) * (pc.zoom or 1.0)
    return W / 2 + (x - sw / 2) * s + pc.pan * pan_unit(clip, W, H), H / 2 + (y - sh / 2) * s - pc.tilt


def head_box(box, size, clip, hf: dict | None = None) -> tuple[float, float, float, float]:
    """Face box in analysis px → box in source px (x, y, w, h)."""
    hf = hf or HEAD
    sw, sh = display(clip)
    aw, ah = size
    x, y, w, h = box[0] / aw * sw, box[1] / ah * sh, box[2] / aw * sw, box[3] / ah * sh
    return x - hf["side"] * w, y - hf["up"] * h, w * (1 + 2 * hf["side"]), h * (1 + hf["up"] + hf.get("down", 0))


def punch_limit(clip, W: int, H: int) -> float:
    return max(1.12, SOFT_LIMIT / scale(clip, W, H))


def _heads(pc, faces: dict, clip, step: int = 3) -> list[tuple[int, tuple]]:
    """(source frame, head box) every few frames of a piece."""
    if pc.clip not in faces:
        return []
    boxes, size = faces[pc.clip]
    out = []
    for f in range(pc.start_frame, pc.end_frame, step):
        if f < len(boxes) and boxes[f][0] >= 0:
            out.append((f, head_box(boxes[f], size, clip)))
    return out


def _gaps(pc, by_id: dict, fps: float) -> list[tuple[int, int, bool]]:
    """Word gaps of a piece as (frame, gap length, after a sentence end): where a split is invisible to the ear."""
    out = []
    ws = [by_id[w] for w in pc.word_ids if w in by_id]
    for a, b in zip(ws, ws[1:]):
        f = round((a.end_s + b.start_s) / 2 * fps)
        if pc.start_frame < f < pc.end_frame:
            out.append((f, round((b.start_s - a.end_s) * fps), a.text.rstrip()[-1:] in ".!?…"))
    return out


def split_points(pc, heads: list, clip, fps: float, gaps: list, W: int, H: int) -> tuple[list[int], list[str]]:
    """Frames where the piece must be split, because the head moves further than the crop can hold."""
    s = scale(clip, W, H) * (pc.zoom or 1.0)
    room = W * (1 - 2 * MARGIN)
    lo, hi, start = None, None, pc.start_frame
    cuts, notes = [], []
    hold = round(MIN_PIECE_S * fps)
    for f, (x, _, w, _) in heads:
        a, b = x * s, (x + w) * s
        lo, hi = (a, b) if lo is None else (min(lo, a), max(hi, b))
        if hi - lo <= room:
            continue
        cand = [g for g in gaps if start + hold <= g[0] <= f]
        if not cand or pc.end_frame - max(g[0] for g in cand) < hold:
            notes.append(f"Gesicht wandert in {pc.clip}:f{f:04d} weiter, als der Ausschnitt reicht, und es gibt keine Wortlücke zum Teilen")
            lo, hi = a, b
            continue
        g = max(cand, key=lambda c: (c[2], c[0]))  # a sentence end, as late as possible
        cuts.append(g[0])
        start, lo, hi = g[0], a, b
    return cuts, notes


def split_piece(pc, frames: list[int], by_id: dict, fps: float) -> list:
    """Copies of a piece, cut at source frames; words go to the part they start in."""
    if not frames:
        return [pc]
    edges = [pc.start_frame] + sorted(frames) + [pc.end_frame]
    parts = []
    for a, b in zip(edges, edges[1:]):
        ids = [w for w in pc.word_ids if w in by_id and a <= round(by_id[w].start_s * fps) < b]
        parts.append(pc.model_copy(update={"start_frame": a, "end_frame": b, "start_s": a / fps, "end_s": b / fps, "word_ids": ids,
                                           "text": " ".join(by_id[w].text for w in ids), "start_shift": 0, "end_shift": 0}))
    return parts


def aim(pc, heads: list, clip, W: int, H: int, target_x: float | None, keep: float | None) -> tuple[float, float, float]:
    """Pan, Tilt and the source x the crop is centred on. keep: centre of the piece before; kept while the head fits, so that plain cuts do not jump."""
    sw, sh = display(clip)
    z = pc.zoom or 1.0
    s = scale(clip, W, H) * z
    if target_x is not None:
        c = target_x * sw
    elif heads:
        c = float(np.median([x + w / 2 for _, (x, _, w, _) in heads]))
    else:
        c = keep if keep is not None else sw / 2
    if keep is not None and heads and target_x is None:
        inside = all((x - keep) * s >= -W / 2 * (1 - 2 * MARGIN) and (x + w - keep) * s <= W / 2 * (1 - 2 * MARGIN) for _, (x, _, w, _) in heads)
        if inside and abs(c - keep) * s < 0.08 * W:
            c = keep
    room = max(0.0, (sw * s - W) / 2)
    shift = max(-room, min(room, (sw / 2 - c) * s))
    tilt = 0.0
    if z > 1 and heads:  # a punch-in has vertical room: eyes back to the upper third, head never cut
        top = float(np.median([y for _, (_, y, _, _) in heads]))
        hh = float(np.median([h for _, (_, _, _, h) in heads]))
        eyes = top + 0.45 * hh
        y_eyes = H / 2 + (eyes - sh / 2) * s
        want = H * EYES_Y - y_eyes
        want = max(want, 0.04 * H - (H / 2 + (top - sh / 2) * s))  # hair inside the frame
        lim = (z - 1) * H / 2
        tilt = -max(-lim, min(lim, want))
    return round(shift / pan_unit(clip, W, H), 2), round(tilt, 1), c


def apply(cl, plan, clips: dict, analyzed: dict, faces: dict, opts: dict | None = None) -> None:
    """Sets every piece of the plan to the crop of the reel; splits where the head leaves the crop."""
    rf = cl.reframe
    if rf is None or not plan.pieces:
        return
    opts = opts or {}
    W, H = rf.width, rf.height
    if rf.two_speaker_layout == "stacked":
        plan.warnings.append("two_speaker_layout „stacked“ ist nicht umgesetzt (siehe NOTES), es gilt „follow“")
    speakers = (opts.get("speakers") or (lambda p: [None] * len(p)))(plan.pieces)
    new, notes, splits, seen, no_face = [], [], 0, {}, 0
    last_speaker = {}
    framed = rf.layout == "framed"
    box_h = framed_height([clips[p.clip] for p in plan.pieces if not p.manual], W, FRAMED_RATIO[rf.aspect]) if framed else H
    for pc, spk in zip(plan.pieces, speakers):
        if pc.manual:
            new.append(pc)
            continue
        clip = clips[pc.clip]
        fps = clip.resolve_fps or clip.fps
        by_id = {e.id: e for e in analyzed[pc.clip].entries} if pc.clip in analyzed else {}
        if framed:  # output px per source px: never above 1.0, a punch-in only uses what the source has to spare
            s = box_h / display(clip)[1]
            pc.zoom = round(s / scale(clip, W, H) * min(pc.zoom or 1.0, 1.0 / s), 4)
        else:
            lim = punch_limit(clip, W, H)
            over = bool(0 < pc.item <= len(cl.items) and cl.items[pc.item - 1].zoom)
            if pc.zoom > lim and not over:
                pc.zoom = round(lim, 3)
        heads = _heads(pc, faces, clip)
        target = None
        if rf.speaker_x and spk is not None:
            # follow the speaker: the crop moves only at the start of a sentence, a piece inside a sentence stays with the one before
            prev = new[-1] if new else None
            sentence_start = prev is None or (prev.text.rstrip()[-1:] in ".!?…")
            if sentence_start:
                last_speaker[pc.clip] = spk
            target = rf.speaker_x.get(str(last_speaker.get(pc.clip, spk)))
        cuts, more = ([], []) if target is not None else split_points(pc, heads, clip, fps, _gaps(pc, by_id, fps), W, H)
        notes += more
        splits += len(cuts)
        for part in split_piece(pc, cuts, by_id, fps):
            hs = [h for h in heads if part.start_frame <= h[0] < part.end_frame]
            if not hs and target is None:
                no_face += 1
            part.pan, part.tilt, c = aim(part, hs, clip, W, H, target, seen.get(pc.clip))
            seen[pc.clip] = c
            part.fill = True
            new.append(part)
    plan.pieces = new
    worst = max(scale(clips[p.clip], W, H) * (p.zoom or 1) for p in new)
    base = min(scale(clips[p.clip], W, H) for p in new)
    c0 = clips[new[0].clip]
    vis = (round(W / base), round(H / base))
    plan.reframe = {"size": (W, H), "splits": splits, "pieces": len(new), "no_face": no_face, "base_scale": round(base, 2), "worst_scale": round(worst, 2),
                    "visible_source_px": vis, "source": display(c0), "report": report(plan, clips, faces, W, H), "layout": rf.layout}
    if framed:
        s0 = box_h / display(c0)[1]
        plan.reframe.update({"window": window(box_h, W, H), "scale": round(s0, 3), "visible_source_px": (round(W / s0), display(c0)[1]), "base_scale": round(s0, 2)})
        if round(W * FRAMED_RATIO[rf.aspect]) > box_h:
            plan.warnings.append(f"{rf.aspect} würde die Quelle hochskalieren: Das Bild ist {W}×{box_h} groß und bleibt bei höchstens 1,0.")
        if any(display(clips[p.clip])[0] * box_h / display(clips[p.clip])[1] < W for p in new):
            plan.warnings.append("Eine Quelle ist schmaler als das Fenster: An den Seiten bleibt die Hintergrundfläche sichtbar.")
    r = plan.reframe["report"]
    if worst > SOFT_LIMIT and not framed:
        plan.warnings.append(f"Bildschärfe: Quelle {display(c0)[0]}×{display(c0)[1]}, im Reel sichtbar {vis[0]}×{vis[1]} Quellpixel, hochskaliert bis {worst:.2f}×: wird weich")
    if r["out"]:
        plan.warnings.append(f"Gesicht in {r['out']} von {r['checked']} geprüften Frames nicht ganz im Ausschnitt")
    if no_face:
        plan.warnings.append(f"{no_face} Teilstück(e) ohne erkanntes Gesicht: Ausschnitt vom Teilstück davor übernommen")
    plan.warnings += notes[:4]


def report(plan, clips: dict, faces: dict, W: int, H: int) -> dict:
    """Head position in the finished crop, every third frame: how many frames were checked, how many leave the crop, the smallest gap to an edge."""
    checked, out, gap, top = 0, 0, float("inf"), float("inf")
    for pc in plan.pieces:
        clip = clips[pc.clip]
        for _, (x, y, w, h) in _heads(pc, faces, clip):
            ax, ay = to_out(x, y, clip, pc, W, H)
            bx, _ = to_out(x + w, y + h, clip, pc, W, H)
            checked += 1
            m = min(ax, W - bx)
            out += m < 0
            gap, top = min(gap, m), min(top, ay)
    return {"checked": checked, "out": int(out), "min_side_px": None if not checked else round(gap), "min_top_px": None if not checked else round(top)}


def place_overlays(cl, plan, clips: dict, focus=None) -> None:
    """Video B-roll fills the frame; the crop sits on focus_x, on the named side, or where the picture has the most going on."""
    rf = cl.reframe
    if rf is None:
        return
    W, H = rf.width, rf.height
    named = {"left": 0.25, "right": 0.75}
    for o in plan.overlays:
        if o.kind != "video" or o.media not in clips:
            continue
        src = cl.overlays[o.index - 1] if 0 < o.index <= len(cl.overlays) else None
        clip = clips[o.media]
        x = getattr(src, "focus_x", None)
        if x is None:
            x = named.get(o.focus) or (focus(o.media, o.src_start or 0, o.src_frames or 1) if focus else 0.5)
        s = scale(clip, W, H)
        sw = display(clip)[0]
        room = max(0.0, (sw * s - W) / 2)
        o.pan = round(max(-room, min(room, (0.5 - x) * sw * s)) / pan_unit(clip, W, H), 2)
        o.focus_x = round(float(x), 3)
        o.fill_video = True


def busiest_x(frames: list[np.ndarray]) -> float:
    """Horizontal centre of what happens in a clip: differences between frames, or fine detail if nothing moves. frames: gray arrays."""
    fr = [f.astype(np.float32) for f in frames]
    move = sum(np.abs(a - b) for a, b in zip(fr, fr[1:])) if len(fr) > 1 else None
    detail = np.abs(np.diff(fr[len(fr) // 2], axis=1))
    col = (move.mean(axis=0) if move is not None and move.mean() > 2 else detail.mean(axis=0))
    col = col - np.percentile(col, 20)
    col = np.clip(col, 0, None)
    n = len(col)
    win = max(3, int(n * 0.32))
    sums = np.convolve(col, np.ones(win), mode="valid")
    return (int(np.argmax(sums)) + win / 2) / n if sums.max() > 0 else 0.5


def qc_lines(tl: dict, plan, clips: dict, analyzed: dict, rf, faces_first=None) -> list[tuple]:
    """(ok | None for a hint, text) for run_qc, from the timeline read back."""
    W, H = rf.width, rf.height
    out = []
    size = (tl.get("readback") or {}).get("size") or tl.get("size")
    if size:
        out.append((tuple(size) == (W, H), f"Timeline {size[0]}×{size[1]} (Soll {W}×{H})"))
    bad, edges = [], []
    for k, (it, pc) in enumerate(zip(tl["v1"], plan.pieces)):
        if abs(it.get("pan", 0) - pc.pan) > 0.05 or abs(it.get("tilt", 0) - pc.tilt) > 0.05 or abs(it["zoom"] - pc.zoom) > 0.005:
            bad.append(k + 1)
        clip = clips.get(pc.clip)
        if clip is None:
            continue
        sw = display(clip)[0]
        s = scale(clip, W, H) * it["zoom"]
        room = (sw * s - W) / 2
        tilt_room = max(0.0, (it["zoom"] - 1) * H / 2)
        if it.get("scaling") != tl.get("scale_fill") or abs(it.get("pan", 0)) * pan_unit(clip, W, H) > room + 1 or abs(it.get("tilt", 0)) > tilt_room + 1:
            edges.append(k + 1)
    out.append((not bad and len(tl["v1"]) == len(plan.pieces), f"Ausschnitt jedes Stücks wie geplant ({len(tl['v1'])} Stücke)" + (f" – abweichend: {bad[:8]}" if bad else "")))
    ov_bad = [u["rec"] for u in tl.get("upper_props", []) if u.get("overlay") and u.get("scaling") != tl.get("scale_fill")]
    out.append((not edges and not ov_bad, "Keine leeren Ränder: V1 und B-Roll füllen das Bild, Pan und Tilt innerhalb des Bildes"
                + (f" – Stücke {edges[:8]}" if edges else "") + (f" – Overlays bei Frame {ov_bad[:4]}" if ov_bad else "")))
    r = plan.reframe.get("report", {})
    out.append((r.get("out", 0) == 0, f"Gesicht im Ausschnitt: {r.get('checked', 0)} Frames geprüft, {r.get('out', 0)} außerhalb, kleinster Seitenabstand {r.get('min_side_px')} px"))
    if r.get("min_top_px") is not None:
        out.append((r["min_top_px"] >= 0 or None, f"Kopf oben: geschätzte Oberkante {r['min_top_px']} px vom Bildrand" + ("" if r["min_top_px"] >= 0 else ", im Kontaktblatt ansehen")))
    w = plan.reframe
    soft = w["worst_scale"] > SOFT_LIMIT
    out.append((None if soft else True, f"Auflösung: Quelle {w['source'][0]}×{w['source'][1]}, sichtbar {w['visible_source_px'][0]}×{w['visible_source_px'][1]} Quellpixel, Skalierung {w['base_scale']:g}× bis {w['worst_scale']:g}×"
                + (" – hochskaliert, wird weich" if soft else "")))
    total_s = tl["frames"] / (tl.get("fps") or 25.0)
    out.append((rf.min_s <= total_s <= rf.max_s, f"Dauer {total_s:.1f} s (Rahmen {rf.min_s:g}–{rf.max_s:g} s)"))
    first = first_piece(plan)
    at = analyzed.get(first.clip)
    fps = (clips[first.clip].resolve_fps or clips[first.clip].fps)
    w0 = next((e for e in at.entries if e.id in first.word_ids), None) if at else None
    if w0 is not None:
        lead = max(0.0, w0.start_s - first.start_frame / fps)
        out.append((lead <= 0.5, f"Hook: Sprache nach {lead:.2f} s (höchstens 0,5 s)"))
    if faces_first is not None:
        out.append((bool(faces_first) or None, "Hook: Gesicht am Anfang erkannt" if faces_first else "Hook: im ersten halben Sekunde kein Gesicht erkannt, im Kontaktblatt ansehen"))
    return out
