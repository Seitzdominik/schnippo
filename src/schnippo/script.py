"""Optional script import (.docx/.txt/.md) and fuzzy segment→line candidates (hints only)."""

from __future__ import annotations

from .platforms import read_text
import re
from pathlib import Path

from pydantic import BaseModel
from rapidfuzz import fuzz

_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[\"„“'(]?[A-ZÄÖÜ0-9])")


class ScriptLine(BaseModel):
    id: str  # L01
    section: str
    text: str


def _paragraphs(path: Path) -> list[tuple[str, bool]]:
    """(text, is_heading) paragraphs."""
    ext = path.suffix.lower()
    out: list[tuple[str, bool]] = []
    if ext == ".docx":
        import docx  # python-docx

        for p in docx.Document(str(path)).paragraphs:
            t = p.text.strip()
            if t:
                style = (p.style.name or "").lower() if p.style is not None else ""
                out.append((t, style.startswith(("heading", "überschrift", "title", "titel"))))
        return out
    if ext not in (".txt", ".md", ".markdown"):
        raise ValueError(f"Skriptformat {ext} nicht unterstützt (.docx, .txt, .md)")
    for raw in read_text(path).splitlines():
        t = raw.strip()
        if not t:
            continue
        m = re.match(r"^#{1,6}\s+(.*)", t)
        if m:
            out.append((m.group(1).strip(), True))
        elif ext == ".txt" and (t.endswith(":") and len(t) < 60 or (t.isupper() and len(t) < 60)):
            out.append((t.rstrip(":"), True))
        else:
            out.append((re.sub(r"^[-*•]\s+|^\d+[.)]\s+", "", t), False))
    return out


def load_script(path: str | Path) -> list[ScriptLine]:
    path = Path(path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Skript nicht gefunden: {path}")
    section, lines = "", []
    for text, heading in _paragraphs(path):
        if heading:
            section = text
            continue
        for sent in _SENT_SPLIT.split(text):
            sent = sent.strip()
            if sent:
                lines.append(ScriptLine(id=f"L{len(lines) + 1:02d}", section=section, text=sent))
    return lines


def _norm(s: str) -> str:
    return re.sub(r"[^\wäöüß ]+", " ", s.lower()).strip()


def match(text: str, lines: list[ScriptLine], top: int = 3, min_score: float = 0.5) -> list[tuple[str, float]]:
    t = _norm(text)
    if not t:
        return []
    scored = []
    for ln in lines:
        lt = _norm(ln.text)
        s = 0.5 * fuzz.token_set_ratio(t, lt) + 0.5 * fuzz.partial_ratio(t, lt)
        scored.append((ln.id, round(s / 100, 2)))
    scored.sort(key=lambda x: -x[1])
    return [x for x in scored[:top] if x[1] >= min_score]
