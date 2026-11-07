"""Placement of a graphic with clearance to the head over its whole duration (05_motion_graphics, Phase 7).

Stages in order: above the head (scaled down to the minimum readable size) → beside the head → below the chin → not
placed ("kein sauberer Platz"). A stage is accepted only if the VISIBLE pixels (alpha of the rendered frame while the
graphic stands, underline included) lie completely in the safe box and keep ≥ head_clearance_px to the head box of every
sampled frame (punch-in applied).
"""

from __future__ import annotations

import io

from PIL import Image

from .templates import ATTEMPTS, CAP_RATIO, STAGE_LABEL, STAGES


def visible_bbox(png: bytes, threshold: int = 8) -> tuple[int, int, int, int] | None:
    a = Image.open(io.BytesIO(png)).getchannel("A").point(lambda v: 255 if v > threshold else 0)
    return a.getbbox()  # (l, t, r, b) or None


def inner_padding(png: bytes, inner: dict | None, min_x_cap: float, min_y_cap: float) -> dict | None:
    """Measure the inner padding in the rendered frame: background box (from the page, without the accent line) against the
    text inside it, found as the pixels that differ from the box colour. Returns distances per side in px, the minimum (from
    the cap height of the box's font) and ok. None for graphics without a box."""
    import numpy as np
    if not inner or not inner.get("rect"):
        return None
    im = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA")).astype(np.int16)
    l, t, r, b = (int(round(v)) for v in inner["rect"])
    crop = im[max(t, 0):b, max(l, 0):r]
    if crop.size == 0:
        return None
    alpha = crop[..., 3]
    solid = alpha > 8
    if not solid.any():
        return None
    bg = np.median(crop[solid], axis=0)
    if bg[3] < 16:  # no visible box
        return None
    corner = alpha < bg[3] - 12  # rounded corners
    diff = np.abs(crop - bg).max(axis=2)
    if inner.get("skip_left"):  # an accent line bends into the box along the rounded corners: not text
        diff[:, :int(inner["skip_left"])] = 0
    if inner.get("skip_right"):
        diff[:, -int(inner["skip_right"]):] = 0
    ys, xs = np.where((diff > 56) & ~corner)
    if len(xs) == 0:
        return None
    H, W = alpha.shape
    cap = float(inner["font"]) * CAP_RATIO
    res = {"left": int(xs.min()), "right": int(W - 1 - xs.max()), "top": int(ys.min()), "bottom": int(H - 1 - ys.max()),
           "min_x": round(min_x_cap * cap, 1), "min_y": round(min_y_cap * cap, 1), "cap": round(cap, 1),
           "box": [l, t, r, b], "text": [l + int(xs.min()), t + int(ys.min()), l + int(xs.max()) + 1, t + int(ys.max()) + 1]}
    res["ok"] = (min(res["left"], res["right"]) >= res["min_x"] - 1 and min(res["top"], res["bottom"]) >= res["min_y"] - 1)
    return res


def gap(box: tuple, head: list | tuple) -> float:
    """Distance between the graphic box (l, t, r, b) and a head box (x, y, w, h); negative = overlap depth."""
    l, t, r, b = box
    hx, hy, hw, hh = head[:4]
    dx = max(hx - r, l - (hx + hw))
    dy = max(hy - b, t - (hy + hh))
    return float(max(dx, dy))


def inside(box: tuple, safe: tuple) -> bool:
    return box[0] >= safe[0] - 0.5 and box[1] >= safe[1] - 0.5 and box[2] <= safe[2] + 0.5 and box[3] <= safe[3] + 0.5


def hold_time(meta: dict) -> float:
    """A moment where everything (incl. a late underline) stands: after the enter, before the exit."""
    return max(meta["text_delay_ms"] + meta["in_ms"] + 450, (meta["duration_ms"] - meta["out_ms"]) * 0.85)


def attempt_label(stage: str, drop: bool, scale: bool) -> str:
    return STAGE_LABEL.get(stage, stage) + (" ohne Zusatzzeile" if drop else "") + ("" if scale else " in voller Größe")


def place(renderer, build, heads: list, clearance: float, attempts=ATTEMPTS, has_label: bool = True,
          min_pad: tuple[float, float] = (0.9, 0.5)) -> dict:
    """build(stage, drop_label, allow_scale) → (html, meta) or raises LookupError. Tries the attempts in order (full size →
    without the extra line → scaled → beside → below); returns the first that fits, with measurements and all attempts."""
    tried = []
    for k, (stage, drop, scale) in enumerate(attempts):
        if drop and not has_label:
            continue  # nothing to drop: the attempt equals the previous one
        name = attempt_label(stage, drop, scale)
        try:
            html, meta = build(stage, drop, scale)
        except LookupError as e:
            tried.append((name, str(e)))
            continue
        (t, png, _), = renderer.stills(html, [hold_time(meta)])
        fit = getattr(renderer, "last_fit", None) or {}
        box = visible_bbox(png)
        if box is None:
            tried.append((name, "nichts sichtbar"))
            continue
        safe = meta.get("safe")
        gaps = [gap(box, hd) for hd in heads] if heads else []
        min_gap = min(gaps) if gaps else None
        reasons = []
        if not fit.get("ok", True):
            reasons.append("passt in voller Größe nicht" if not scale else f"passt selbst bei Mindestgröße (× {meta.get('min_scale')}) nicht")
        if safe and not inside(box, safe):
            reasons.append("ragt aus der sicheren Zone")
        if min_gap is not None and min_gap < clearance - 0.5:
            reasons.append(f"Abstand zum Kopf {min_gap:.0f} px < {clearance:.0f} px")
        pad = inner_padding(png, getattr(renderer, "last_inner", None), *min_pad)
        if pad is not None and not pad["ok"]:
            reasons.append(f"Innenabstand zu klein (links {pad['left']}, rechts {pad['right']}, oben {pad['top']}, unten {pad['bottom']} px; "
                           f"Minimum {pad['min_x']:.0f}/{pad['min_y']:.0f} px)")
        res = {"stage": stage, "label": name, "attempt": k + 1, "label_dropped": drop, "html": html, "meta": meta, "bbox": box, "padding": pad,
               "min_gap": None if min_gap is None else round(min_gap, 1), "safe_ok": bool(safe is None or inside(box, safe)),
               "fit": fit, "heads": len(heads), "png": png}
        if not reasons:
            res["ok"], res["tried"] = True, tried
            return res
        tried.append((name, "; ".join(reasons)))
    return {"ok": False, "stage": None, "label": "nicht gesetzt", "tried": tried, "heads": len(heads)}


def tried_text(tried: list) -> str:
    return " → ".join(f"{s}: {r}" for s, r in tried)
