"""Path rules (Phase 8, security): tools read only inside the material folder the user named (plus the export folder),
write only into the export folder and the cache, never modify or delete material. Paths are resolved first (".." and
symlinks), so a link inside the material folder cannot lead elsewhere."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

EXPORT_DIRNAME = "schnippo-export"
LEGACY_EXPORT_DIRNAME = "resolve-cut-export"  # projects from before the rename keep theirs
FONT_EXTS = {".woff2", ".woff", ".otf", ".ttf"}


class PathNotAllowed(ValueError):
    pass


def _too_broad() -> set[Path]:
    home = Path.home()
    return {Path(p).resolve() for p in ("/", "/Users", "/Volumes", "/System", "/Library", "/Applications", "/private",
                                        "/usr", "/bin", "/etc", str(home), str(home / "Desktop"), str(home / "Documents"),
                                        str(home / "Downloads"), str(home / "Movies"), str(home / "Library"))}


def real(p: str | Path) -> Path:
    return Path(os.path.realpath(Path(p).expanduser()))


def _by_unicode(p: Path) -> Path:
    """macOS keeps umlauts decomposed in some places, a pasted path may carry the other form: walk down and compare names in one normal form."""
    if p.exists() or not p.is_absolute():
        return p
    cur = Path(p.anchor)
    for part in p.parts[1:]:
        nxt = cur / part
        if not nxt.exists():
            want = unicodedata.normalize("NFC", part)
            try:
                nxt = next((c for c in cur.iterdir() if unicodedata.normalize("NFC", c.name) == want), nxt)
            except OSError:
                pass
        cur = nxt
    return cur


def clean_path(text: str | Path) -> Path:
    """A path as people paste it: quotes, spaces around it, ~, file:// URLs, a slash at the end, shell escapes, either Unicode form."""
    t = str(text).strip()
    while len(t) >= 2 and t[0] in "\"'“”„‘’«»" and t[-1] in "\"'“”„‘’«»":
        t = t[1:-1].strip()
    if t.lower().startswith("file:"):
        u = urlparse(t)
        t = unquote(u.path)
    t = re.sub(r"\\(.)", r"\1", t)
    if len(t) > 1:
        t = t.rstrip("/")
    return _by_unicode(Path(t).expanduser())


def inside(p: str | Path, root: str | Path) -> bool:
    rp, rr = real(p), real(root)
    return rp == rr or rr in rp.parents


def material_root(path: str | Path) -> Path:
    """The folder the user names as material. Must exist and be a concrete project folder (not /, the home folder,
    Desktop, Documents, … – scanning those would read far more than intended)."""
    p = real(clean_path(path))
    if not p.is_dir():
        raise FileNotFoundError(f"Ordner nicht gefunden: {p}. Bitte den Ordner mit dem Material angeben (Rechtsklick im "
                                f"Finder → „Kopieren als Pfadname“).")
    if p in _too_broad():
        raise PathNotAllowed(f"„{p}“ ist zu allgemein. Bitte den Projektordner mit den Aufnahmen angeben, z. B. "
                             f"„{p / 'Mein Projekt'}“.")
    return p


def media_files(folder: Path, recursive: bool, exts: set[str]) -> tuple[list[Path], list[str]]:
    """Files with these extensions in the folder. Skipped (and reported): links that lead outside the folder, our own
    export folder, hidden folders, macOS resource forks."""
    folder = real(folder)
    notes, out = [], []
    it = folder.rglob("*") if recursive else folder.iterdir()
    for p in it:
        rel = p.relative_to(folder)
        if any(part.startswith(".") or part in (EXPORT_DIRNAME, LEGACY_EXPORT_DIRNAME) for part in rel.parts[:-1]) or p.name.startswith("._"):
            continue
        if p.suffix.lower() not in exts or not p.is_file():
            continue
        if not inside(p, folder):
            notes.append(f"{rel}: Verknüpfung nach außerhalb des Material-Ordners – übersprungen")
            continue
        out.append(p)
    return sorted(out), notes


def check_read(path: str | Path, roots: list[Path | None], what: str) -> Path:
    p = real(clean_path(path))
    allowed = [r for r in roots if r is not None]
    if not any(inside(p, r) for r in allowed):
        names = " oder ".join(f"„{real(r)}“" for r in allowed) or "den Material-Ordner (zuerst ingest_folder)"
        raise PathNotAllowed(f"{what} liegt außerhalb der freigegebenen Ordner. Bitte in {names} legen und erneut versuchen.")
    if not p.is_file():
        raise FileNotFoundError(f"{what} nicht gefunden: {p}")
    return p


def check_write_dir(path: str | Path) -> Path:
    p = real(clean_path(path))
    if p in _too_broad():
        raise PathNotAllowed(f"Export-Ordner „{p}“ ist zu allgemein – bitte einen eigenen Ordner angeben.")
    return p


def check_font(path: str | Path, material: Path | None) -> Path:
    p = real(path)
    if p.suffix.lower() not in FONT_EXTS:
        raise PathNotAllowed(f"„{p.name}“ ist keine Schriftdatei ({', '.join(sorted(FONT_EXTS))}).")
    roots = [Path.home() / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts"),
             Path.home() / ".config/schnippo", material]
    return check_read(p, roots, f"Schriftdatei „{p.name}“")
