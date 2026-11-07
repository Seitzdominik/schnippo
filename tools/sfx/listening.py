"""Listening sheets: one file per group with our own effects one after the other (no references), a table with time marks and the distance to the group.

    uv run python sfx/listening.py        → docs/hoerbeispiele/"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
ROOT = REPO / "src" / "schnippo" / "data" / "sfx"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(TOOLS))
import compare  # noqa: E402
from schnippo.media import _bin  # noqa: E402
from schnippo.sfx import decode  # noqa: E402

OUT = REPO / "docs" / "hoerbeispiele"
SHEETS = {"Whoosh und Swish": ("whoosh", "swish"), "Riser": ("riser",), "Impact": ("impact", "impact_soft"), "Downer": ("downer",), "Ding": ("ding",),
          "Klick und Tick": ("click", "tick"), "Tippen": ("typing",), "Uhr und Wecker": ("clock", "alarm"), "Pop": ("pop",)}
FILE = {"Whoosh und Swish": "whoosh", "Riser": "riser", "Impact": "impact", "Downer": "downer", "Ding": "ding", "Klick und Tick": "klick", "Tippen": "tippen", "Uhr und Wecker": "uhr", "Pop": "pop"}


def main():
    lib = json.loads((ROOT / "library.json").read_text(encoding="utf-8"))["effects"]
    dist = {r["id"]: r for r in compare.table()}
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.m4a"):
        old.unlink()
    lines = ["# Hörbögen", "", "Je Gruppe eine Datei mit den Effekten der Bibliothek nacheinander, 1 s Pause dazwischen: eigene Synthese und echte CC0-Aufnahmen, keine Pixabay-Referenzen.",
             "", "Distanz: 0 heißt, alle Kennwerte liegen im Wertebereich der Referenzgruppe. Größere Werte: wie weit sie außerhalb liegen, die Spalte nennt die Kennwerte. Das misst Hüllkurve, Spektrum, Breite und Hall, nicht den Klangeindruck.", ""]
    for title, cats in SHEETS.items():
        rows = [e for e in lib if e["category"] in cats]
        parts, t, table = [], 0.0, []
        for e in rows:
            x = decode(ROOT / e["file"])
            table.append((t, e))
            parts += [x, np.zeros((48000, 2))]
            t += len(x) / 48000 + 1.0
        y = np.concatenate(parts)
        name = f"{FILE[title]}.m4a"
        raw = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
        subprocess.run([_bin("ffmpeg"), "-y", "-v", "error", "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", "-", "-c:a", "aac", "-b:a", "192k", str(OUT / name)], input=raw, check=True)
        lines += [f"## {title}: `{name}`", "", "| Zeit | Effekt | Stufe | Charakter | Distanz | außerhalb |", "|---|---|---|---|---|---|"]
        for a, e in table:
            d = dist[e["id"]]["distance"]
            if e["license"] == "CC0":
                lines.append(f"| {int(a // 60)}:{a % 60:05.2f} | `{e['id']}` | {e['intensity']} | {e['description']} | – (echte Aufnahme) | |")
                continue
            lines.append(f"| {int(a // 60)}:{a % 60:05.2f} | `{e['id']}` | {e['intensity']} | {e['description']} | {d['total'] if d else '– (keine Referenz)'} | {', '.join(d['outside']) if d else ''} |")
        lines.append("")
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    cc0 = {e["id"] for e in lib if e["license"] == "CC0"}
    vals = [r["distance"]["total"] for r in dist.values() if r["distance"] and r["id"] not in cc0]
    print(f"{len(SHEETS)} Hörbögen, mittlere Distanz {sum(vals) / len(vals):.2f}, im Bereich (< 0,5): {sum(v < 0.5 for v in vals)} von {len(vals)}")


if __name__ == "__main__":
    main()
