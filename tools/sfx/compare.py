"""Distance of our effects to their reference group (key figures only).   uv run python sfx/compare.py [ids…]"""
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
ROOT = REPO / "src" / "schnippo" / "data" / "sfx"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(TOOLS))
import generate  # noqa: E402
from schnippo.sfx import decode  # noqa: E402
from schnippo.sfx_profile import distance, profile  # noqa: E402

META = {e["id"]: e for e in json.loads((ROOT / "library.json").read_text(encoding="utf-8"))["effects"]}


def skip_for(name):
    """Values that do not apply: a sequence has no single tail, a riser that stops on the event has none at all."""
    e = META[name]
    if e["type"] in ("sequence", "bed") or e["category"] == "alarm":
        return ("rt60_ms", "tail_share", "attack_ms")
    if e["event_align"] == "end":
        return ("rt60_ms", "tail_share", "fall20_ms")
    return ()


def table(only=None):
    groups = json.loads((ROOT / "analysis" / "groups.json").read_text())
    rows = []
    sounds = generate.build(only)
    for e in META.values():
        if e["license"] == "CC0" and (only is None or e["id"] in only):
            sounds[e["id"]] = decode(ROOT / e["file"])
    for name, x in sounds.items():
        g = META[name]["reference"]
        p = profile(x, name=name)
        rows.append({"id": name, "group": g, "profile": p, "distance": distance(p, groups[g], skip_for(name)) if g else None})
    return rows


if __name__ == "__main__":
    rows = table(set(sys.argv[1:]) or None)
    for r in rows:
        p, d = r["profile"], r["distance"]
        print(f"{r['id']:18} {str(r['group']):7} D={d['total'] if d else '–':<5} {p['duration_ms']:>5} ms at={p['attack_ms']:<6} f20={p['fall20_ms']} A={p['centroid_a_hz']:<5} bw={p['bandwidth_oct']} fl={p['flatness']} S/M={p['side_mid_db']} rt={p['rt60_ms']} tail={p['tail_share']} {list(p['bands_pct'].values())} {d['outside'] if d else ''}")
