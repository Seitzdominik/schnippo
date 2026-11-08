"""ffmpeg/ffprobe from the PyPI package portable-ffmpeg-full (FFmpeg 9.0.2, GPL-3.0-or-later build by Martin Riedl, native arm64/x86_64 wheels with both binaries). Only used when no system ffmpeg exists.
Fetched on first use (deps.py). License notice: see README (section ffmpeg). The binaries run as separate processes; nothing links against them."""

from __future__ import annotations

_found: tuple[str, str] | None = None


def _paths() -> tuple[str, str] | None:
    global _found
    if _found is not None:
        return _found
    try:
        from portable_ffmpeg import get_ffmpeg
    except ImportError:
        return None
    import contextlib
    import sys
    try:
        # first call unpacks the archive shipped inside the wheel and prints progress to stdout – stdout is the MCP
        # channel (stdio transport), so it goes to stderr
        with contextlib.redirect_stdout(sys.stderr):
            ffmpeg, ffprobe = get_ffmpeg()
    except Exception:
        return None
    _found = (str(ffmpeg), str(ffprobe))
    return _found


def path(name: str) -> str | None:
    p = _paths()
    if p is None:
        return None
    return {"ffmpeg": p[0], "ffprobe": p[1]}.get(name)
