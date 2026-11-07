"""Contact sheet of a graphic over the real video frame at its planned position (before rendering), plus the checks
of 05_motion_graphics: fits the safe zone, max lines, face free, contrast."""

from __future__ import annotations

import io
import subprocess

from PIL import Image, ImageDraw, ImageFont

from ..formatting import ts
from ..media import _bin
from .tokens import contrast

THUMB = (270, 480)


def video_frame(clip, idx: int, w: int, h: int) -> Image.Image:
    fps = clip.resolve_fps or clip.fps
    raw = subprocess.run([_bin("ffmpeg"), "-nostdin", "-v", "error", "-ss", f"{idx / fps:.6f}", "-i", clip.path, "-frames:v", "1",
                          "-vf", f"scale={w}:{h}", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    try:
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return Image.new("RGB", (w, h), (90, 90, 90))


def punched(img: Image.Image, zoom: float, pan: float, tilt: float, scale: float) -> Image.Image:
    """Approximation of the Resolve punch-in (zoom around the centre, Pan +x right, Tilt + up) at preview scale."""
    if zoom <= 1.0 and not pan and not tilt:
        return img
    w, h = img.size
    big = img.resize((round(w * zoom), round(h * zoom)), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h))
    canvas.paste(big, (round((w - big.width) / 2 + pan * scale), round((h - big.height) / 2 - tilt * scale)))
    return canvas


def checks(meta: dict, bbox, fit, face, tok: dict) -> list[str]:
    out = []
    if fit:
        out.append(("✓" if fit.get("ok") else "⚠") + f" passt in die sichere Zone (Schriftgröße × {fit.get('scale')}, "
                   f"{fit.get('lines')} Zeile(n))" + ("" if fit.get("scale", 1) >= 0.8 else " – deutlich verkleinert, Text kürzen?"))
    safe = meta.get("safe")
    if bbox and safe:
        x0, y0, x1, y1 = safe
        inside = bbox[0] >= x0 - 1 and bbox[1] >= y0 - 1 and bbox[2] <= x1 + 1 and bbox[3] <= y1 + 1
        out.append(("✓" if inside else "⚠") + f" Box {round(bbox[0])},{round(bbox[1])}–{round(bbox[2])},{round(bbox[3])} "
                   f"{'innerhalb' if inside else 'außerhalb'} der sicheren Zone {round(x0)},{round(y0)}–{round(x1)},{round(y1)}")
    if bbox and face:
        m = 20
        fx, fy, fw, fh = face
        hit = not (bbox[2] < fx - m or bbox[0] > fx + fw + m or bbox[3] < fy - m or bbox[1] > fy + fh + m)
        out.append(("⚠ überdeckt das Gesicht" if hit else "✓ Gesicht frei") + f" (Gesicht {round(fx)},{round(fy)} {round(fw)}×{round(fh)})")
    b = tok["brand"]
    mode = tok["style"]["surface_mode"]
    bg = {"light": b["surface_light"], "accent": b["accent"]}.get(mode, b["surface"])
    fg = b["text_dark"] if mode == "light" else b["text"]
    c = contrast(fg, bg if not bg.startswith("rgba") else "#" + "".join(f"{int(float(v)):02x}" for v in bg[5:-1].split(",")[:3]))
    out.append(("✓" if c >= tok["contrast"]["min_ratio"] else "⚠") + f" Kontrast Text/Box {c}:1 (Ziel ≥ {tok['contrast']['min_ratio']}:1; Box deckend gerechnet, Scrim {bg})")
    return out


def label(img: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
    except OSError:
        f = ImageFont.load_default()
    d.rectangle((0, img.height - 22, img.width, img.height), fill=(0, 0, 0))
    d.text((6, img.height - 19), text, fill=(255, 255, 0), font=f)
    return img


def sheet(rows: list[list[Image.Image]], title: str) -> bytes:
    cols = max(len(r) for r in rows)
    im = Image.new("RGB", (THUMB[0] * cols, THUMB[1] * len(rows) + 26), (24, 24, 24))
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
    except OSError:
        f = ImageFont.load_default()
    d.text((8, 5), title, fill=(230, 230, 230), font=f)
    for y, row in enumerate(rows):
        for x, t in enumerate(row):
            im.paste(t, (x * THUMB[0], 26 + y * THUMB[1]))
    if im.width > 1620:
        im.thumbnail((1620, 10000))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def stage_times(meta: dict) -> list[tuple[float, str]]:
    D, t_in, t_out, td = meta["duration_ms"], meta["in_ms"], meta["out_ms"], meta["text_delay_ms"]
    return [(t_in * 0.3, "Ein"), (td + t_in * 0.5, "Ein"), (td + t_in + 150, "steht"), (D * 0.55, "Mitte"),
            (D - t_out * 0.6, "Aus"), (D - t_out * 0.15, "Aus")]


def frame_at(plan, tl_frame: int):
    rec = 0
    for pc in plan.pieces:
        if rec <= tl_frame < rec + pc.frames:
            return pc, pc.start_frame + (tl_frame - rec)
        rec += pc.frames
    pc = plan.pieces[-1]
    return pc, pc.end_frame - 1


def fmt_time(frame: int, fps: float) -> str:
    return ts(frame / fps)


def debug_lines(img: Image.Image, sc: float, safe, head, bbox, min_gap, padding: dict | None = None) -> None:
    """Helper lines on the preview: safe zone (cyan), head box of this frame (yellow), visible graphic (magenta),
    clearance between them (with px label), inner padding (green: text box; dashed-free thin line: required minimum)."""
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", max(12, round(28 * sc)))
    except OSError:
        f = ImageFont.load_default()
    if safe:
        d.rectangle([v * sc for v in safe], outline=(0, 220, 255, 255), width=2)
    if padding:
        l, t, r, b = padding["box"]
        mx, my = padding["min_x"], padding["min_y"]
        d.rectangle([(l + mx) * sc, (t + my) * sc, (r - mx) * sc, (b - my) * sc], outline=(255, 255, 255, 255), width=1)
        d.rectangle([v * sc for v in padding["text"]], outline=(0, 255, 120, 255), width=2)
    if head:
        x, y, w, h = head[:4]
        d.rectangle([x * sc, y * sc, (x + w) * sc, (y + h) * sc], outline=(255, 220, 0, 255), width=3)
    if bbox:
        d.rectangle([v * sc for v in bbox], outline=(255, 0, 200, 255), width=3)
        if head:
            x, y, w, h = head[:4]
            cx = (max(bbox[0], x) + min(bbox[2], x + w)) / 2 * sc
            if bbox[3] <= y:  # graphic above the head
                d.line([cx, bbox[3] * sc, cx, y * sc], fill=(255, 0, 200, 255), width=3)
                d.text((cx + 6, (bbox[3] + y) / 2 * sc - 10), f"{min_gap:.0f} px" if min_gap is not None else "", fill=(255, 0, 200, 255), font=f)
            elif bbox[1] >= y + h:  # below the chin
                d.line([cx, (y + h) * sc, cx, bbox[1] * sc], fill=(255, 0, 200, 255), width=3)
                d.text((cx + 6, (y + h + bbox[1]) / 2 * sc - 10), f"{min_gap:.0f} px" if min_gap is not None else "", fill=(255, 0, 200, 255), font=f)
