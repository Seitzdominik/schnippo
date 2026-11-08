"""Heavy helpers are not part of the install: the server starts in seconds, and on first use Schnippo fetches them once, with a real progress report.

Measured on the Windows CI (Phase 13, docs/ENTWICKLUNG.md): of 147 MB download and 393 MB unpacked, ffmpeg is 62/153 MB and OpenCV 41/116 MB; Windows Defender scans every unpacked file on top. Both go through
`uv pip install` into the environment the server runs in, `uv run` leaves them alone at the next start. ffmpeg is not fetched when the system has its own.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import logging
import re
import sys
import tempfile
import time
from pathlib import Path

from . import platforms

log = logging.getLogger("schnippo")

HEAVY = {"ffmpeg": ("portable-ffmpeg-full", "portable_ffmpeg", "ffmpeg"), "opencv": ("opencv-python-headless", "cv2", "die Bildanalyse")}
FALLBACK = {"portable-ffmpeg-full": "==0.5.0", "opencv-python-headless": ">=4.10,<5"}


class SetupFailed(RuntimeError):
    """A helper could not be fetched: the message says what to do."""


def available(key: str) -> bool:
    return importlib.util.find_spec(HEAVY[key][1]) is not None


def wanted(key: str) -> str:
    """The version constraint this release was built with."""
    dist = HEAVY[key][0]
    try:
        for req in importlib.metadata.requires("schnippo") or []:
            m = re.match(rf"{re.escape(dist)}\s*([^;]*)", req)
            if m:
                return f"{dist}{m.group(1).strip()}"
    except importlib.metadata.PackageNotFoundError:
        pass
    return f"{dist}{FALLBACK[dist]}"


def _platform_tag() -> str:
    if sys.platform == "win32":
        return "win_amd64"
    return "arm64" if sys.platform == "darwin" else "x86_64"


def _pick_wheel(files: list[dict]) -> dict | None:
    """The wheel for this computer from a PyPI release listing."""
    tag = _platform_tag()
    py = f"cp{sys.version_info.major}{sys.version_info.minor}"
    wheels = [f for f in files if f["filename"].endswith(".whl") and tag in f["filename"] and not f.get("yanked")]
    return next((f for f in wheels if py in f["filename"]), None) or next((f for f in wheels if "abi3" in f["filename"] or "py3-none" in f["filename"]), None)


def _exact_version(req: str) -> str | None:
    m = re.search(r"==\s*([\w.]+)", req)
    return m.group(1) if m else None


def _download(dist: str, version: str | None, folder: Path, say, label: str) -> Path | None:
    """The wheel from PyPI with a real percentage, its hash checked. None if PyPI gives no fitting wheel: uv then does it alone."""
    import httpx
    url = f"https://pypi.org/pypi/{dist}/{version}/json" if version else f"https://pypi.org/pypi/{dist}/json"
    with httpx.Client(timeout=60.0, follow_redirects=True) as c:
        rel = c.get(url)
        rel.raise_for_status()
        pick = _pick_wheel(rel.json()["urls"])
        if pick is None:
            return None
        total, done, shown = pick["size"], 0, -1
        out = folder / pick["filename"]
        sha = hashlib.sha256()
        with c.stream("GET", pick["url"]) as resp, open(out, "wb") as f:
            resp.raise_for_status()
            for chunk in resp.iter_bytes(1 << 20):
                f.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                pct = int(done * 100 / total)
                if pct >= shown + 10:
                    shown = pct - pct % 10
                    say(f"{DISPLAY} lädt einmalig {label} ({total / 1e6:.0f} MB) … {pct} %")
    if sha.hexdigest() != pick["digests"]["sha256"]:
        out.unlink()
        raise SetupFailed(f"Der Download von {label} war beschädigt. Bitte noch einmal versuchen.")
    return out


DISPLAY = "Schnippo"


def ensure(key: str, say=None) -> bool:
    """Make sure a helper is there. True if it was fetched just now."""
    if available(key):
        return False
    say = say or (lambda msg: log.info("Einrichtung: %s", msg))
    dist, _, label = HEAVY[key]
    uv = platforms.find_uv()
    if uv is None:
        raise SetupFailed(f"Für {label} fehlt das Installationsprogramm uv. Installiere Schnippo als Erweiterung in Claude Desktop neu oder führe aus: pip install \"schnippo[media]\"")
    req = wanted(key)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="schnippo_setup_") as tmp:
        target = req
        try:
            wheel = _download(dist, _exact_version(req), Path(tmp), say, label)
            if wheel is not None:
                target = str(wheel)
        except SetupFailed:
            raise
        except Exception as e:  # uv has its own retries and mirrors: let it try
            log.info("Direkter Download von %s nicht möglich (%s), uv übernimmt", dist, type(e).__name__)
        say(f"{label[0].upper()}{label[1:]} wird eingerichtet …")
        res = platforms.run([uv, "pip", "install", "--python", sys.executable, target], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise SetupFailed(f"{label[0].upper()}{label[1:]} ließ sich nicht laden. Bitte Internetverbindung prüfen und noch einmal versuchen. ({res.stderr.strip()[-200:]})")
    importlib.invalidate_caches()
    from .media import find_tool
    find_tool.cache_clear()
    say(f"{label[0].upper()}{label[1:]} ist bereit ({time.monotonic() - started:.0f} s).")
    return True


def status() -> dict[str, bool]:
    return {k: available(k) for k in HEAVY}


def ensure_for_material(say=None) -> None:
    """Before the first ingest: everything at once, so there is one wait instead of two surprises. A system ffmpeg makes the download unnecessary."""
    from .media import system_tool
    if not (system_tool("ffmpeg") and system_tool("ffprobe")):
        ensure("ffmpeg", say)
    ensure("opencv", say)
