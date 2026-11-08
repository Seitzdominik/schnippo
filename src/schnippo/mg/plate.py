"""The calm surface of a framed reel: one rendered picture in the design colour with a transparent window, so the video stays the untouched main item on V1 and nothing has to move
to another track. It lies above the B-roll, which therefore also shows inside the window, and below the graphics."""

from __future__ import annotations

import hashlib
import subprocess
from fractions import Fraction
from pathlib import Path

from PIL import Image

from ..media import _bin
from ..platforms import no_window

TRACK = 3


def picture(path: Path, W: int, H: int, win: tuple[int, int, int, int], colour: str) -> Path:
    img = Image.new("RGBA", (W, H), colour)
    x, y, w, h = win
    img.paste((0, 0, 0, 0), (x, y, x + w, y + h))
    img.save(path)
    return path


def render(cache_root: Path, W: int, H: int, win: tuple[int, int, int, int], colour: str, fps: float, frames: int) -> str:
    """ProRes 4444 from the one picture; the same path the other graphics take into Resolve (alpha straight). Cached by content."""
    key = hashlib.sha1(f"{W}x{H}|{win}|{colour}|{fps}|{frames}".encode()).hexdigest()[:16]
    base = Path(cache_root) / "mg" / f"plate_{key}"
    mov = base.with_suffix(".mov")
    if mov.exists():
        return str(mov)
    base.parent.mkdir(parents=True, exist_ok=True)
    png = picture(base.with_suffix(".png"), W, H, win, colour)
    rate = Fraction(fps).limit_denominator(1001)
    cmd = [_bin("ffmpeg"), "-y", "-nostdin", "-v", "error", "-loop", "1", "-framerate", f"{rate.numerator}/{rate.denominator}", "-i", str(png), "-frames:v", str(frames),
           "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16", "-vendor", "apl0", "-colorspace", "bt709", "-color_primaries", "bt709",
           "-color_trc", "bt709", str(mov)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **no_window())
    if r.returncode != 0:
        raise RuntimeError(f"Hintergrundfläche: Encoding fehlgeschlagen: {r.stderr.strip()[-300:]}")
    return str(mov)
