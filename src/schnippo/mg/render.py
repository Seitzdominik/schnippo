"""Deterministic rendering of HTML graphics: headless Chromium (Playwright), per frame t = n·1000/fps via
window.__seek (never a clock override – it does not drive CSS/WAAPI), screenshots with transparent background at the
timeline resolution, then ProRes 4444 with alpha (PNG sequence kept as fallback). The network is blocked while
rendering (fonts are embedded as data URIs).

Playwright and chromium-headless-shell are installed on first use (motion_setup), not with the extension:
  * Python package → <cache>/motion-lib (uv pip install --target …; a uv sync of the extension leaves it alone),
  * browser → <cache>/playwright (PLAYWRIGHT_BROWSERS_PATH).
"""

from __future__ import annotations

from .. import platforms
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..media import _bin

log = logging.getLogger("schnippo")
PLAYWRIGHT_VERSION = "1.64.1"


class MotionUnavailable(RuntimeError):
    pass


def _dirs(cache_root: Path) -> tuple[Path, Path]:
    return Path(cache_root) / "motion-lib", Path(cache_root) / "playwright"


def _activate(cache_root: Path) -> None:
    lib, browsers = _dirs(cache_root)
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):  # also when set but empty
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    if lib.exists() and str(lib) not in sys.path:
        sys.path.insert(0, str(lib))


def status(cache_root: Path) -> dict:
    _activate(cache_root)
    try:
        import playwright  # noqa: F401
        have_pkg = True
    except ImportError:
        have_pkg = False
    _, browsers = _dirs(cache_root)
    shells = sorted(Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]).glob("chromium_headless_shell-*")) if have_pkg else []
    return {"package": have_pkg, "browser": bool(shells), "browser_dir": str(shells[-1]) if shells else None}


def _du(p: Path) -> float:
    return sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file()) / 1e6 if Path(p).exists() else 0.0


def ensure(cache_root: Path, progress=None) -> dict:
    """Install what is missing; returns timings and sizes. progress(msg) gets status lines."""
    say = progress or (lambda msg: log.info(msg))
    st = status(cache_root)
    info = {"installed": [], "seconds": 0.0}
    t0 = time.time()
    lib, browsers = _dirs(cache_root)
    if not st["package"]:
        uv = platforms.find_uv()
        say(f"Motion Graphics: lade Playwright {PLAYWRIGHT_VERSION} (einmalig) …")
        cmd = ([uv, "pip", "install", "--quiet", "--target", str(lib), "--python", sys.executable, f"playwright=={PLAYWRIGHT_VERSION}"]
               if uv else [sys.executable, "-m", "pip", "install", "--quiet", "--target", str(lib), f"playwright=={PLAYWRIGHT_VERSION}"])
        r = platforms.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise MotionUnavailable(f"Playwright-Installation fehlgeschlagen: {r.stderr.strip()[-400:]}")
        info["installed"].append(f"Playwright {PLAYWRIGHT_VERSION} ({_du(lib):.0f} MB)")
        _activate(cache_root)
        st = status(cache_root)
    if not st["browser"]:
        say("Motion Graphics: lade Chromium (Headless Shell, einmalig, ~90 MB) …")
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(lib)] + sys.path)}
        r = platforms.run([sys.executable, "-m", "playwright", "install", "chromium-headless-shell"], capture_output=True,
                           text=True, env=env)
        if r.returncode != 0:
            raise MotionUnavailable(f"Chromium-Download fehlgeschlagen: {(r.stderr or r.stdout).strip()[-400:]}")
        info["installed"].append(f"Chromium Headless Shell ({_du(browsers):.0f} MB entpackt)")
    info["seconds"] = round(time.time() - t0, 1)
    return info


class Renderer:
    """One browser for many graphics (context manager)."""

    def __init__(self, cache_root: Path, w: int, h: int):
        self.cache_root, self.w, self.h = Path(cache_root), w, h

    def __enter__(self):
        _activate(self.cache_root)
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(args=["--disable-gpu", "--font-render-hinting=none"])
        self._ctx = self._browser.new_context(viewport={"width": self.w, "height": self.h}, device_scale_factor=1)
        self._ctx.route("**/*", lambda route: route.abort() if route.request.url.startswith(("http:", "https:", "ws:", "wss:"))
                        else route.continue_())
        return self

    def __exit__(self, *exc):
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    def page(self, html: str):
        pg = self._ctx.new_page()
        pg.set_content(html, wait_until="load")
        pg.evaluate("window.__ready")
        missing = pg.evaluate("[typeof window.__seek, typeof window.__duration_ms, typeof window.__ready]")
        if missing != ["function", "number", "object"]:
            pg.close()
            raise ValueError(f"Seek-Vertrag nicht erfüllt (__seek/__duration_ms/__ready): {missing}")
        return pg

    def stills(self, html: str, times_ms: list[float]) -> list[tuple[float, bytes, list]]:
        pg = self.page(html)
        self.last_fit = pg.evaluate("window.__fit || null")
        out = []
        try:
            for t in times_ms:
                pg.evaluate(f"window.__seek({t})")
                bbox = pg.evaluate("window.__bbox ? window.__bbox() : null")
                self.last_inner = pg.evaluate("window.__inner ? window.__inner() : null")
                out.append((t, pg.screenshot(omit_background=True, type="png"), bbox))
        finally:
            pg.close()
        return out

    def frames(self, html: str, fps: float, out_dir: Path) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        pg = self.page(html)
        t0 = time.time()
        try:
            dur = pg.evaluate("window.__duration_ms")
            n = max(1, round(dur / 1000 * fps))
            boxes = []
            fit = pg.evaluate("window.__fit || null")
            for k in range(n):
                pg.evaluate(f"window.__seek({k * 1000 / fps})")
                if k in (n // 2,):
                    boxes.append(pg.evaluate("window.__bbox ? window.__bbox() : null"))
                pg.screenshot(path=str(out_dir / f"f_{k:05d}.png"), omit_background=True, type="png")
        finally:
            pg.close()
        return {"frames": n, "seconds": round(time.time() - t0, 2), "bbox_mid": boxes[0] if boxes else None, "duration_ms": dur,
                "fit": fit}


def encode_prores4444(frames_dir: Path, fps: float, out: Path) -> Path:
    """ProRes 4444 with 16-bit alpha, BT.709 tags (design_tokens.render)."""
    from fractions import Fraction
    rate = Fraction(fps).limit_denominator(1001)
    cmd = [_bin("ffmpeg"), "-y", "-v", "error", "-framerate", f"{rate.numerator}/{rate.denominator}", "-i",
           str(frames_dir / "f_%05d.png"), "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le",
           "-alpha_bits", "16", "-vendor", "apl0", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           str(out)]
    r = platforms.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ProRes-4444-Encoding fehlgeschlagen: {r.stderr.strip()[-300:]}")
    return out


def render_graphic(cache_root: Path, html: str, w: int, h: int, fps: float, renderer: Renderer | None = None) -> dict:
    """→ {mov, frames_dir, frames, seconds (render), encode_s, cached}. Cached by content."""
    key = hashlib.sha1(f"{html}|{w}x{h}|{fps}".encode()).hexdigest()[:16]
    base = Path(cache_root) / "mg" / key
    mov = base.with_suffix(".mov")
    if mov.exists():
        return {"mov": str(mov), "frames_dir": str(base), "cached": True, "key": key}
    own = renderer is None
    r = renderer or Renderer(cache_root, w, h).__enter__()
    try:
        res = r.frames(html, fps, base)
    finally:
        if own:
            r.__exit__(None, None, None)
    t1 = time.time()
    encode_prores4444(base, fps, mov)
    res.update({"mov": str(mov), "frames_dir": str(base), "cached": False, "encode_s": round(time.time() - t1, 2), "key": key})
    return res


SANDBOX_CHECK_JS = """(() => {
  const els = [...document.querySelectorAll('body *')].filter(e => {
    const s = getComputedStyle(e), r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && parseFloat(s.opacity) > 0.01 && s.display !== 'none';
  });
  const fonts = new Set(), colors = new Set();
  let box = null;
  for (const e of els) {
    const s = getComputedStyle(e);
    if ([...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) { fonts.add(s.fontFamily); colors.add(s.color); }
    if (s.backgroundColor && s.backgroundColor !== 'rgba(0, 0, 0, 0)') colors.add(s.backgroundColor);
    const r = e.getBoundingClientRect();
    box = box ? [Math.min(box[0], r.left), Math.min(box[1], r.top), Math.max(box[2], r.right), Math.max(box[3], r.bottom)]
              : [r.left, r.top, r.right, r.bottom];
  }
  return {fonts: [...fonts], colors: [...colors], box};
})()"""


def _rgb(c: str) -> tuple[int, int, int] | None:
    c = c.strip()
    if c.startswith("rgb"):
        v = [float(x) for x in c[c.index("(") + 1:c.index(")")].replace("/", ",").split(",")[:3]]
        return tuple(round(x) for x in v)
    if c.startswith("#"):
        c = c.lstrip("#")
        c = "".join(ch * 2 for ch in c) if len(c) == 3 else c
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return None


def sandbox_wrap(html: str, tok: dict) -> str:
    """Inject the brand font (@font-face "Brand") and token CSS variables into free HTML."""
    from .tokens import font_faces
    b = tok["brand"]
    css = (f"<style>{font_faces(tok)}:root{{--accent:{b['accent']};--text:{b['text']};--text-dark:{b['text_dark']};"
           f"--surface:{b['surface']};--surface-light:{b['surface_light']};--radius:{b['radius_px']}px;--font:'Brand'}}</style>")
    return html.replace("<head>", "<head>" + css, 1) if "<head>" in html else css + html


def sandbox_check(renderer: "Renderer", html: str, tok: dict, safe: tuple | None) -> list[str]:
    """Seek contract, only token fonts/colours, everything inside the safe zone (at mid-duration)."""
    pg = renderer.page(html)  # raises if the contract is missing
    try:
        d = pg.evaluate("window.__duration_ms")
        pg.evaluate(f"window.__seek({d / 2})")
        info = pg.evaluate(SANDBOX_CHECK_JS)
    finally:
        pg.close()
    issues = []
    bad_fonts = [f for f in info["fonts"] if not f.strip().strip('"').startswith("Brand")]
    if bad_fonts:
        issues.append(f"⚠ Schrift außerhalb der Marke: {bad_fonts} (nur font-family: var(--font))")
    allowed = {_rgb(v if not v.startswith("rgba") else "rgb" + v[4:]) for k, v in tok["brand"].items()
               if isinstance(v, str) and (v.startswith("#") or v.startswith("rgb"))}
    bad_cols = [c for c in info["colors"] if _rgb(c) not in allowed]
    if bad_cols:
        issues.append(f"⚠ Farben außerhalb der Tokens: {bad_cols[:4]}")
    if safe and info["box"]:
        x0, y0, x1, y1 = safe
        b = info["box"]
        if b[0] < x0 - 1 or b[1] < y0 - 1 or b[2] > x1 + 1 or b[3] > y1 + 1:
            issues.append(f"⚠ ragt aus der sicheren Zone: {[round(v) for v in b]}")
    return issues or ["✓ Sandbox: Seek-Vertrag, Schrift, Farben und sichere Zone eingehalten (Netzwerk beim Rendern gesperrt)"]
