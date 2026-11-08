"""Project folders: the recommended structure, folder names as a signal, projects by name, the brief. Nothing here moves or renames a file of the user."""

from __future__ import annotations

import datetime
import re
from pathlib import Path

ROLES = {"aroll": {"aroll", "atake", "atakes", "interview", "interviews", "sprecher", "speaker", "talkinghead", "takes", "hauptkamera", "maincam"},
         "broll": {"broll", "footage", "schnittbilder", "cutaways", "cutaway", "stockfootage"},
         "images": {"bilder", "images", "fotos", "photos", "stills", "logos", "standbilder", "pictures"},
         "script": {"skript", "skripte", "script", "scripts", "drehbuch"}}
STRUCTURE = ("A-Roll", "B-Roll", "Bilder", "Skript")
SCRIPT_EXTS = {".docx", ".txt", ".md"}
BRIEF = """# Brief

Alles ist optional, Stichworte reichen.

Format (Reel, YouTube, Kurs, Interview, Werbung):
Art des Inhalts (Interview, Kurs, Werbung, Talking Head):
Ziel und Zielgruppe:
Gewünschte Länge:
Kernbotschaft:
Call-to-Action:
Muss rein:
Muss raus:
Tonalität:
Marke/Design-Profil:
"""
GLOSSARY = """# Namen, Firmen, Orte und Adressen in richtiger Schreibweise, eine Zeile je Begriff.
# Bekannte Verhörer nach einem Gleichheitszeichen, zum Beispiel: MOC AG = Moz AG
"""


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]", "", name.lower())


def role_of_folder(name: str) -> str | None:
    n = _norm(name)
    return next((r for r, names in ROLES.items() if n in names), None)


def role_of_file(path: str | Path, root: str | Path) -> str | None:
    """The role the folder gives a file below root: its first folder with a known name."""
    try:
        parts = Path(path).relative_to(root).parts[:-1]
    except ValueError:
        return None
    return next((r for r in map(role_of_folder, parts) if r), None)


def has_structure(root: Path) -> bool:
    return any(p.is_dir() and role_of_folder(p.name) for p in Path(root).iterdir())


def in_structure(path: Path, root: Path) -> bool:
    """Files directly in the project or below a folder with a known name count; other subfolders are left alone."""
    rel = path.relative_to(root).parts[:-1]
    return not rel or role_of_folder(rel[0]) is not None


def script_files(root: Path) -> list[Path]:
    out = []
    for d in Path(root).iterdir():
        if d.is_dir() and role_of_folder(d.name) == "script":
            out += [f for f in sorted(d.iterdir()) if f.suffix.lower() in SCRIPT_EXTS and not f.name.startswith((".", "~"))]
    return out


def brief_text(root: Path) -> str | None:
    """What the user filled in; an untouched template says nothing."""
    f = Path(root) / "brief.md"
    if not f.is_file():
        return None
    lines = []
    for ln in f.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("Alles ist optional"):
            continue
        if s.endswith(":") and s in BRIEF:
            continue
        lines.append(s)
    return "\n".join(lines) or None


def brief_format(root: Path) -> str | None:
    """The format named in the brief, in the words the template offers. A project's own brief beats the general preference."""
    from .prefs import FORMATS
    text = brief_text(root) or ""
    m = re.search(r"^Format[^:\n]*:\s*(.+)$", text, re.M | re.I)
    if not m:
        return None
    fmt = FORMATS.get(m.group(1).strip().rstrip(".").lower())
    return None if fmt in (None, "auto") else fmt


def brief_content_type(root: Path) -> str | None:
    """What the brief says the material is: the line for it, or "Interview" and the like in the format line."""
    from .formats import CONTENT_WORDS
    text = brief_text(root) or ""
    for rx in (r"^Art[^:\n]*:\s*(.+)$", r"^Format[^:\n]*:\s*(.+)$"):
        m = re.search(rx, text, re.M | re.I)
        if m and (ct := CONTENT_WORDS.get(m.group(1).strip().rstrip(".").lower())):
            return ct
    return None


def _stem(name: str) -> str:
    return re.sub(r"^\d{4}-\d{2}-\d{2}[_ -]*", "", name)


def find(query: str, root: Path) -> Path:
    """A project by name in the projects folder, tolerant of typos and dates. Several good matches: the user decides."""
    from rapidfuzz import fuzz
    dirs = [p for p in Path(root).iterdir() if p.is_dir() and not p.name.startswith(".")]
    q = _norm(query)
    scored = sorted(((max(fuzz.WRatio(q, _norm(_stem(d.name))), fuzz.partial_ratio(q, _norm(d.name))), d) for d in dirs), key=lambda x: -x[0])
    good = [(s, d) for s, d in scored if s >= 75]
    if not good:
        raise FileNotFoundError(f"Kein Projekt „{query}“ in {root}. Vorhanden: {', '.join(d.name for d in dirs[:8]) or 'noch keins'}")
    if len(good) > 1 and good[0][0] - good[1][0] < 8:
        raise LookupError(f"Mehrere Projekte passen zu „{query}“: {', '.join(d.name for _, d in good[:5])}. Welches meinst du?")
    return good[0][1]


def create(name: str, root: Path, today: datetime.date | None = None) -> tuple[Path, bool]:
    """Folder structure with empty glossary and brief template. Returns (path, already there). Existing files stay as they are."""
    clean = re.sub(r"[\\/:*?\"<>|]+", " ", name).strip().strip(".")
    clean = re.sub(r"\s+", "_", clean)
    if not clean:
        raise ValueError("Bitte einen Projektnamen angeben, zum Beispiel „Kunde Thema“")
    d = today or datetime.date.today()
    p = Path(root) / f"{d.isoformat()}_{clean}"
    existed = p.exists()
    for sub in STRUCTURE:
        (p / sub).mkdir(parents=True, exist_ok=True)
    for fname, text in (("glossar.txt", GLOSSARY), ("brief.md", BRIEF)):
        if not (p / fname).exists():
            (p / fname).write_text(text, encoding="utf-8")
    return p, existed
