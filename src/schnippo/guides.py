"""Editing guides per pass (guides/01_rough_cut.md … 04_polish.md, research-based) + guides/technik.md (server usage)."""

from __future__ import annotations

import re
from pathlib import Path

PASSES = ("rough", "fine", "broll", "polish", "motion", "reel")
COMPLETE = "komplett"  # the complete cut: its own guide, then everything a pass would read
FILES = {"rough": "01_rough_cut.md", "fine": "02_fine_cut.md", "broll": "03_broll.md", "polish": "04_polish.md",
         "motion": "05_motion_graphics.md", "reel": "07_reels.md"}
COMPLETE_FILE = "00_komplett.md"
SOUND = "06_sound_design.md"  # read in the passes that place effects
TITLES = {"rough": "Durchgang 1: Rough Cut", "fine": "Durchgang 2: Fine Cut", "broll": "Durchgang 3: B-Roll",
          "polish": "Durchgang 4: Polish", "motion": "Durchgang 5: Motion Graphics", "reel": "Reels aus dem langen Video"}


def default_dir() -> Path:
    """Repo checkout: <repo>/guides; installed bundle: same layout (the bundle ships the whole project)."""
    return Path(__file__).resolve().parent / "data" / "guides"


def technik(folder: Path, pass_name: str | None) -> str:
    f = Path(folder) / "technik.md"
    if not f.exists():
        return ""
    text = f.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## ", text)
    secs = {p.split("\n", 1)[0].strip(): p.split("\n", 1)[1] if "\n" in p else "" for p in parts[1:]}
    out = ["## Technik (alle Durchgänge)\n" + secs.get("Alle Durchgänge", "").strip()]
    for ps in ([pass_name] if pass_name else PASSES):
        if ps in secs:
            out.append(f"## Technik ({ps})\n" + secs[ps].strip())
    return "\n\n".join(out)


def guide(folder: Path, pass_name: str | None) -> str:
    """Guide text for one pass (or all four when pass_name is None) incl. the matching technik sections."""
    if pass_name == COMPLETE:
        parts = [(Path(folder) / COMPLETE_FILE).read_text(encoding="utf-8").strip()]
        parts += [(Path(folder) / FILES[ps]).read_text(encoding="utf-8").strip() for ps in ("rough", "fine", "broll", "motion", "polish") if (Path(folder) / FILES[ps]).exists()]
        if (Path(folder) / SOUND).exists():
            parts.append((Path(folder) / SOUND).read_text(encoding="utf-8").strip())
        return "\n\n".join(parts + [technik(folder, None)])
    if pass_name is not None and pass_name not in PASSES:
        raise ValueError(f"pass muss eines von {', '.join(PASSES)} sein, nicht {pass_name!r}")
    folder = Path(folder)
    texts = []
    for ps in ([pass_name] if pass_name else PASSES[:4]):  # motion only on request (optional pass)
        f = folder / FILES[ps]
        if f.exists():
            texts.append(f.read_text(encoding="utf-8").strip())
    if pass_name in ("broll", "motion", "reel") and (folder / SOUND).exists():
        texts.append((folder / SOUND).read_text(encoding="utf-8").strip())
    tech = technik(folder, pass_name)
    return "\n\n".join(texts + ([tech] if tech else []))
