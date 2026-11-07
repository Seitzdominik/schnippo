"""Render a still image as a short ProRes clip in the timeline format (fill/crop by focus, optional Ken Burns move).

Only still images are ever rendered – never the original video. Used when Resolve's API cannot express the
requested framing/motion natively (measured in Phase 3: Dynamic Zoom only zooms *out* 1.24→1.0; Fusion keyframes set
via the API have no effect in the render; Pan units are not documented). Output is cached by content + parameters.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .media import _bin

ZOOM = 1.15  # end zoom for slow_zoom_in / start zoom for slow_zoom_out / constant zoom for pans
OVERSAMPLE = 2  # render the source at 2x before zoompan → smooth sub-pixel motion


def _crop_xy(focus: str) -> tuple[str, str]:
    x = {"left": "0", "right": "iw-ow"}.get(focus, "(iw-ow)/2")
    y = {"top": "0", "bottom": "ih-oh"}.get(focus, "(ih-oh)/2")
    return x, y


def render_still(src: Path, out_dir: Path, width: int, height: int, fps_num: int, fps_den: int, frames: int,
                 motion: str = "none", focus: str = "center", rotation: int = 0) -> Path:
    key = hashlib.sha1(f"{src.resolve()}|{src.stat().st_size}|{src.stat().st_mtime_ns}|{width}x{height}|{fps_num}/{fps_den}|"
                       f"{frames}|{motion}|{focus}|{rotation}".encode()).hexdigest()[:16]
    out = out_dir / f"still_{key}.mov"
    if out.exists():
        return out
    out_dir.mkdir(parents=True, exist_ok=True)
    W, H = width * OVERSAMPLE, height * OVERSAMPLE
    cx, cy = _crop_xy(focus)
    n = max(1, frames - 1)
    zoom, x, y = "1", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    if motion == "slow_zoom_in":
        zoom = f"1+{ZOOM - 1}*on/{n}"
    elif motion == "slow_zoom_out":
        zoom = f"{ZOOM}-{ZOOM - 1}*on/{n}"
    elif motion in ("pan_left", "pan_right"):
        zoom = f"{ZOOM}"
        frac = f"on/{n}" if motion == "pan_right" else f"(1-on/{n})"
        x = f"(iw-iw/zoom)*{frac}"
    rot = {90: "transpose=1,", -90: "transpose=2,", 270: "transpose=2,", 180: "transpose=1,transpose=1,"}.get(rotation, "")
    vf = (f"{rot}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}:{cx}:{cy},"
          f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps_num}/{fps_den},"
          f"format=yuv422p10le")
    tmp = out.with_suffix(".tmp.mov")
    subprocess.run([_bin("ffmpeg"), "-nostdin", "-v", "error", "-y", "-loop", "1", "-i", str(src), "-vf", vf,
                    "-frames:v", str(frames), "-c:v", "prores_ks", "-profile:v", "2", "-an", str(tmp)], check=True)
    tmp.replace(out)
    return out


def needs_render(motion: str, focus: str) -> bool:
    """Native Resolve handles: centered fill (Scaling=FILL) and the fixed Dynamic Zoom out."""
    return not (focus == "center" and motion in ("none", "slow_zoom_out"))
