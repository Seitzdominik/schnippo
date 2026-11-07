"""Transform maths for Resolve timeline items (measured on 21.1.2).

* Zoom is relative to the item's fitted size; ZoomX = 1.12 → 1.12× (measured 1.12–1.13).
* Pan/Tilt move the image in units of (displayed item width / timeline width) output pixels: a video item at timeline
  resolution moves exactly 1 px per unit (Pan +x → right, Tilt +y → UP), independent of zoom; a 4000×6000 still filled
  into 1080×1920 (displayed 1280 px wide) moved 1.2 px per unit (1280/1080 = 1.19).
"""

from __future__ import annotations


def px_per_unit(displayed_w: float, timeline_w: float) -> float:
    return displayed_w / timeline_w


def punch_in(face_x: float, face_y: float, zoom: float, width: int, height: int, unit: float = 1.0) -> tuple[float, float]:
    """Pan/Tilt that keep the face (normalised centre, y downwards) where it was while zooming about the frame centre,
    clamped so that no image border becomes visible."""
    if zoom <= 1.0:
        return 0.0, 0.0
    dx = -(face_x - 0.5) * (zoom - 1) * width  # image shift in px (right +)
    dy = -(face_y - 0.5) * (zoom - 1) * height  # image shift in px (down +)
    mx, my = (zoom - 1) / 2 * width, (zoom - 1) / 2 * height
    dx, dy = max(-mx, min(mx, dx)), max(-my, min(my, dy))
    return round(dx / unit, 2), round(-dy / unit, 2)  # Tilt + moves the image up
