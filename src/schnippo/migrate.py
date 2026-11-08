"""One-time move from the working title: settings, brand profiles and the cache. Runs at start, never stops the server.

The config folder is copied. The cache is renamed and the old path stays as a link: rendered graphics and stills in it are referenced by finished Resolve timelines, which must not go offline."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from .branding import LEGACY_SLUG, SLUG
from . import platforms

_log = logging.getLogger("schnippo")


def run(home: Path | None = None) -> list[str]:
    if platforms.is_windows() or (home is None and os.environ.get("SCHNIPPO_NO_MIGRATE")):  # the old name never ran on Windows
        return []
    home = Path(home or Path.home())
    done = []
    old, new = home / ".config" / LEGACY_SLUG, home / ".config" / SLUG
    try:
        if old.is_dir() and not new.exists():
            shutil.copytree(old, new)
            done.append(f"Einstellungen übernommen: {old} → {new}")
    except OSError as e:
        _log.warning("Einstellungen nicht übernommen: %s", type(e).__name__)
    old, new = home / "Library" / "Caches" / LEGACY_SLUG, home / "Library" / "Caches" / SLUG
    try:
        if old.is_dir() and not old.is_symlink() and not new.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            os.rename(old, new)
            old.symlink_to(new, target_is_directory=True)
            done.append(f"Cache übernommen: {old} → {new}")
    except OSError as e:
        _log.warning("Cache nicht übernommen: %s", type(e).__name__)
    return done
