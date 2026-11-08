"""Frames: cached thumbnails from the original files, contact sheets for Claude, per-frame motion energy.

Frame IDs work like word IDs: ``c01:f0123`` = source frame 123 of clip c01 on Resolve's frame grid (t = 123 / fps).
Extraction uses ffmpeg input seeking (``-ss t -i file``): verified frame-identical to ``select=eq(n,…)`` and to
Resolve (see NOTES), honours rotation (autorotate) and edit lists, ~0.1 s per frame.
"""

from __future__ import annotations

from . import platforms
import io
import math
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .formatting import ts
from .media import _bin
from .models import Clip, Still

THUMB_LONG = 480  # cached thumbnail long edge (px)
SHEET_MAX = 1024  # contact sheet long edge (px)
MOTION_W = 64  # motion analysis width (px)


def frame_id(cid: str, idx: int) -> str:
    return f"{cid}:f{idx:04d}"


def parse_frame_id(ref: str) -> tuple[str, int]:
    m = re.fullmatch(r"(c\d+):f0*(\d+)", ref.strip())
    if not m:
        raise ValueError(f"ungültige Frame-ID {ref!r} (z. B. c01:f0123)")
    return m.group(1), int(m.group(2))


def image_tokens(w: int, h: int) -> int:
    """Approximate vision tokens of an image as sent to Claude (≈ w·h / 750, after the 1568 px long-edge cap)."""
    s = min(1.0, 1568 / max(w, h))
    return math.ceil((w * s) * (h * s) / 750)


def display_size(c: Clip) -> tuple[int, int]:
    return (c.height, c.width) if abs(c.rotation) % 180 == 90 else (c.width, c.height)


class FrameCache:
    def __init__(self, cache_dir: Path, clip: Clip):
        self.clip = clip
        self.dir = cache_dir / "frames"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.fps = clip.resolve_fps or clip.fps
        w, h = display_size(clip)
        self.tw, self.th = (THUMB_LONG, round(THUMB_LONG * h / w)) if w >= h else (round(THUMB_LONG * w / h), THUMB_LONG)
        self.tw -= self.tw % 2
        self.th -= self.th % 2

    def path(self, idx: int) -> Path:
        return self.dir / f"f{idx:06d}.jpg"

    def _extract(self, idx: int) -> Path:
        out = self.path(idx)
        if not out.exists():
            tmp = out.with_suffix(".tmp.jpg")
            platforms.run([_bin("ffmpeg"), "-nostdin", "-v", "error", "-y", "-ss", f"{idx / self.fps:.6f}", "-i", self.clip.path,
                            "-frames:v", "1", "-vf", f"scale={self.tw}:{self.th}", "-q:v", "3", str(tmp)], check=True)
            tmp.replace(out)
        return out

    def get(self, idxs: list[int]) -> dict[int, Path]:
        last = (self.clip.resolve_frames or self.clip.nb_frames or 10**9) - 1
        idxs = sorted({max(0, min(last, i)) for i in idxs})
        with ThreadPoolExecutor(max_workers=4) as ex:
            return dict(zip(idxs, ex.map(self._extract, idxs)))


def motion_energy(cache_dir: Path, clip: Clip) -> np.ndarray:
    """Mean absolute luma difference to the previous frame (0..255), per source frame; cached."""
    f = cache_dir / "motion.npy"
    if f.exists():
        return np.load(f)
    w, h = display_size(clip)
    mh = round(MOTION_W * h / w)
    mh -= mh % 2
    proc = platforms.popen([_bin("ffmpeg"), "-nostdin", "-v", "error", "-i", clip.path, "-an",
                             "-vf", f"fps={clip.resolve_fps or clip.fps},scale={MOTION_W}:{mh},format=gray",
                             "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    size = MOTION_W * mh
    vals, prev = [0.0], None
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        cur = np.frombuffer(buf, np.uint8).astype(np.int16)
        if prev is not None:
            vals.append(float(np.mean(np.abs(cur - prev))))
        prev = cur
    proc.wait()
    arr = np.array(vals, dtype=np.float32)
    np.save(f, arr)
    return arr


# ---------------------------------------------------------------- contact sheets
def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _label(img: Image.Image, text: str, sub: str = "") -> None:
    d = ImageDraw.Draw(img)
    fs = max(11, img.width // 11)
    font = _font(fs)
    lines = [text] + ([sub] if sub else [])
    bh = (fs + 4) * len(lines) + 4
    d.rectangle([0, img.height - bh, img.width, img.height], fill=(0, 0, 0))
    for k, ln in enumerate(lines):
        d.text((4, img.height - bh + 2 + k * (fs + 4)), ln, fill=(255, 255, 0) if k == 0 else (255, 255, 255), font=font)


def sheet(tiles: list[tuple[Path | Image.Image | None, str, str]], cols: int, tile_aspect: float,
          max_edge: int = SHEET_MAX, header: str = "") -> Image.Image:
    """tiles: (image or path or None for an empty slot, label, sublabel). tile_aspect = w/h of a tile."""
    rows = max(1, math.ceil(len(tiles) / cols))
    hh = 22 if header else 0
    # fit cols x rows tiles of aspect tile_aspect into max_edge
    tw = max_edge / cols
    th = tw / tile_aspect
    if th * rows + hh > max_edge:
        th = (max_edge - hh) / rows
        tw = th * tile_aspect
    tw, th = int(tw), int(th)
    out = Image.new("RGB", (tw * cols, th * rows + hh), (40, 40, 40))
    if header:
        ImageDraw.Draw(out).text((6, 3), header, fill=(255, 255, 255), font=_font(15))
    for k, (src, lab, sub) in enumerate(tiles):
        x, y = (k % cols) * tw, hh + (k // cols) * th
        if src is None:
            continue
        im = src if isinstance(src, Image.Image) else Image.open(src)
        im = im.convert("RGB")
        im.thumbnail((tw - 2, th - 2))
        tile = Image.new("RGB", (tw - 2, th - 2), (0, 0, 0))
        tile.paste(im, ((tile.width - im.width) // 2, (tile.height - im.height) // 2))
        _label(tile, lab, sub)
        out.paste(tile, (x + 1, y + 1))
    return out


def to_jpeg(img: Image.Image, quality: int = 80) -> bytes:
    b = io.BytesIO()
    img.save(b, format="JPEG", quality=quality, optimize=True)
    return b.getvalue()


def still_tile(st: Still, long_edge: int = THUMB_LONG) -> Image.Image:
    im = Image.open(st.path)
    im = im.convert("RGB")
    if st.rotation:
        im = im.rotate(-st.rotation, expand=True)
    im.thumbnail((long_edge, long_edge))
    return im


def scene_frames(clip: Clip, threshold: float = 0.3, max_frames: int = 64) -> list[int]:
    """Frame indices of scene changes (ffmpeg scene score), always including frame 0."""
    fps = clip.resolve_fps or clip.fps
    err = platforms.run([_bin("ffmpeg"), "-nostdin", "-v", "info", "-i", clip.path, "-an", "-vf",
                          f"scale=160:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    pts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", err)]
    return sorted({0} | {round(t * fps) for t in pts})[:max_frames]


def label_time(idx: int, fps: float) -> str:
    return ts(idx / fps)


# ---------------------------------------------------------------- person-aware motion (Phase 4)
PERSON_W = 270  # analysis width (px)
MOTION_VERSION = 2


def _face_detector():
    import cv2

    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def person_analysis(cache_dir: Path, clip: Clip, detect_every: int = 2) -> dict:
    """One decode pass: per frame face box (x, y, w, h in analysis px, -1 = none), motion inside the person region
    (face + upper body/hands; centre region without a face) and global motion. Cached (person.npz)."""
    f = cache_dir / "person.npz"
    if f.exists():
        d = np.load(f)
        if int(d["version"]) == MOTION_VERSION:
            return {k: d[k] for k in d.files}
    w, h = display_size(clip)
    H = round(PERSON_W * h / w)
    H -= H % 2
    det = _face_detector()
    proc = platforms.popen([_bin("ffmpeg"), "-nostdin", "-v", "error", "-i", clip.path, "-an",
                             "-vf", f"fps={clip.resolve_fps or clip.fps},scale={PERSON_W}:{H},format=gray", "-f", "rawvideo", "-"],
                            stdout=subprocess.PIPE)
    size = PERSON_W * H
    boxes, m_person, m_global = [], [0.0], [0.0]
    prev = None
    last_box = None
    k = 0
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        g = np.frombuffer(buf, np.uint8).reshape(H, PERSON_W)
        if k % detect_every == 0:
            faces = det.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=(max(24, PERSON_W // 12),) * 2)
            last_box = tuple(int(v) for v in max(faces, key=lambda b: b[2] * b[3])) if len(faces) else None
        box = last_box
        boxes.append(box or (-1, -1, -1, -1))
        cur = g.astype(np.int16)
        if prev is not None:
            if box:
                x, y, bw, bh = box
                x0, x1 = max(0, int(x - 1.2 * bw)), min(PERSON_W, int(x + 2.2 * bw))
                y0, y1 = max(0, int(y - 0.5 * bh)), min(H, int(y + 4.0 * bh))
            else:
                x0, x1, y0, y1 = int(PERSON_W * 0.1), int(PERSON_W * 0.9), int(H * 0.15), int(H * 0.95)
            m_person.append(float(np.mean(np.abs(cur[y0:y1, x0:x1] - prev[y0:y1, x0:x1]))))
            m_global.append(float(np.mean(np.abs(cur - prev))))
        prev = cur
        k += 1
    proc.wait()
    out = {"boxes": np.array(boxes, dtype=np.int32), "person": np.array(m_person, dtype=np.float32),
           "global": np.array(m_global, dtype=np.float32), "size": np.array([PERSON_W, H]), "version": np.array(MOTION_VERSION)}
    np.savez_compressed(f, **out)
    return out


def bridge_face_gaps(face: np.ndarray, max_gap: int = 12) -> np.ndarray:
    """Short detector dropouts (≤ max_gap frames, face on both sides) count as face present. Measured on the Phase-8
    interview (3/4 profile): 733 dropouts, median 2 frames, p90 10 – without bridging they flagged 16 cuts as restless."""
    out = face.copy()
    n, k = len(face), 0
    while k < n:
        if not face[k]:
            j = k
            while j < n and not face[j]:
                j += 1
            if 0 < k and j < n and j - k <= max_gap:
                out[k:j] = True
            k = j
        else:
            k += 1
    return out


def cut_motion(pa: dict, no_face_factor: float = 50.0, min_face_share: float = 0.2, max_gap: int = 12) -> np.ndarray:
    """Motion used for cut decisions: person-region motion; frames without a detected face for longer than max_gap
    frames count as very restless (entering the frame, turned away). Clips with hardly any faces (B-roll) fall back to
    global motion."""
    face = bridge_face_gaps(pa["boxes"][:, 0] >= 0, max_gap)
    if face.mean() < min_face_share:
        return pa["global"].copy()
    m = pa["person"].copy()
    med = max(float(np.median(m[1:][face[1:]])) if face[1:].any() else 0.5, 0.05)
    m[~face] = np.maximum(m[~face], no_face_factor * med)
    return m
