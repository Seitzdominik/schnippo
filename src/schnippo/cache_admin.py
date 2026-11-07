"""clear_cache: what the cache holds, by category, and removing old entries. Only the cache folder is touched, never
material or exports. Transcripts cost money and graphic/B-roll renders are used by timelines → only on request."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

CATEGORIES = {  # key: (label, regenerable, kept unless asked)
    "renders_check": ("Prüf-Renders (Ton-/QC-Messung)", True, False),
    "frames": ("Einzelbilder und Bewegungsanalyse", True, False),
    "audio": ("Ton-Auszüge (16 kHz) und Pegelanalyse", True, False),
    "transcripts": ("Transkripte (Gladia – erneut kostenpflichtig)", False, True),
    "renders_used": ("Grafik- und B-Roll-Renders (in Timelines verwendet – dort danach offline)", False, True),
}


def _entries(root: Path):
    """(category, path) for every deletable unit (file or directory)."""
    media = root / "media"
    for d in sorted(media.glob("*")) if media.exists() else []:
        for p in d.iterdir():
            n = p.name
            if n == "frames" or n.startswith("person") or n.startswith("motion") or n.startswith("scenes"):
                yield "frames", p
            elif n.startswith("audio16k") or n.startswith("acoustic") or n.startswith("audio_report") or n.startswith("speaker_channels"):
                yield "audio", p
            elif n.startswith("raw.") or n.startswith("tokens."):
                yield "transcripts", p
    for sub in ("fcpxml/audio", "qc"):
        for p in sorted((root / sub).glob("*.mov")) if (root / sub).exists() else []:
            yield "renders_check", p
    for sub in ("fcpxml/broll", "mg"):
        for p in sorted((root / sub).iterdir()) if (root / sub).exists() else []:
            yield "renders_used", p


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _mtime(p: Path) -> float:
    if p.is_file():
        return p.stat().st_mtime
    ts = [f.stat().st_mtime for f in p.rglob("*") if f.is_file()]
    return max(ts) if ts else p.stat().st_mtime


def scan(root: Path, older_than_days: float = 30.0, now: float | None = None) -> dict:
    now = now or time.time()
    limit = now - older_than_days * 86400
    out = {k: {"label": v[0], "all_bytes": 0, "old_bytes": 0, "old": []} for k, v in CATEGORIES.items()}
    for cat, p in _entries(Path(root)):
        sz = _size(p)
        out[cat]["all_bytes"] += sz
        if _mtime(p) < limit:
            out[cat]["old_bytes"] += sz
            out[cat]["old"].append(p)
    return out


def clear(root: Path, older_than_days: float = 30.0, include_transcripts: bool = False, include_renders: bool = False,
          confirm: bool = False, now: float | None = None) -> tuple[str, int]:
    root = Path(root).resolve()
    info = scan(root, older_than_days, now)
    chosen = [k for k, (_, regen, kept) in CATEGORIES.items()
              if not kept or (k == "transcripts" and include_transcripts) or (k == "renders_used" and include_renders)]
    gb = lambda b: f"{b / 1e9:.2f} GB" if b >= 1e8 else f"{b / 1e6:.0f} MB"
    lines = [f"Cache {root} – älter als {older_than_days:g} Tage:"]
    total = 0
    for k, v in info.items():
        mark = "→ wird gelöscht" if k in chosen and v["old"] else ("bleibt" if k not in chosen else "nichts Altes")
        lines.append(f"  {v['label']}: {gb(v['all_bytes'])} gesamt, {gb(v['old_bytes'])} alt ({len(v['old'])}) – {mark}")
        if k in chosen:
            total += v["old_bytes"]
    if not confirm:
        lines.append(f"Würde {gb(total)} freigeben. Noch nichts gelöscht – clear_cache(confirm=true) nach OK des Nutzers.")
        return "\n".join(lines), 0
    freed = 0
    for k in chosen:
        for p in info[k]["old"]:
            if root not in p.resolve().parents:  # never outside the cache
                continue
            sz = _size(p)
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            freed += sz
    lines.append(f"Gelöscht: {gb(freed)}. Material und Exporte unberührt.")
    return "\n".join(lines), freed
