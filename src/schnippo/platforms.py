"""What differs between macOS and Windows, in one place."""

from __future__ import annotations

import subprocess
import sys


def is_windows() -> bool:
    return sys.platform == "win32"


def no_window() -> dict:
    """Without this every ffmpeg call opens a console window when the server was started without one (Claude Desktop on Windows)."""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if is_windows() else {}
