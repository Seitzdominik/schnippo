"""Real recordings under CC0 in the library: cut from the source files, nothing else unless noted.

    uv run python sfx/recorded.py ../CC0-SFX      → sfx/wav/<id>.wav, sfx/recorded.json

Only CC0 sounds whose licence was checked on their Freesound page belong here (see sfx/LICENSES.md). Pixabay files never."""

import json
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
ROOT = REPO / "src" / "schnippo" / "data" / "sfx"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(TOOLS))
from schnippo.sfx import SR, decode, measure  # noqa: E402
from synth import highpass  # noqa: E402

MOUSE = ("192068", "deleted_user_2902138", "mouseclicks", "https://freesound.org/s/192068/")
KEYS = ("866643", "7empest", "Keyboard typing", "https://freesound.org/s/866643/")
TIMER = ("869203", "initbruv216", "Steba oven clock - mechanical timer", "https://freesound.org/s/869203/")
VINYL = ("668909", "ChuckChuckGoof", "Vinyl Scratch", "https://freesound.org/s/668909/")

# id: source, start s, end s, category, intensity, description, type, align, what is done besides cutting
CUTS = {
    "click_mouse": (MOUSE, 2.590, 2.900, "click", 2, "echte Maus: Drücken und Loslassen", "oneshot", "transient", {"one_channel": 1}),
    "click_mouse_soft": (MOUSE, 0.340, 0.630, "click", 1, "echte Maus, leiser Anschlag", "oneshot", "transient", {"one_channel": 1}),
    "click_mouse_sharp": (MOUSE, 6.935, 7.220, "click", 3, "echte Maus, kräftig", "oneshot", "transient", {"one_channel": 1}),
    "typing_mech": (KEYS, 33.40, 36.90, "typing", 2, "echte Tastatur, rote Schalter, flüssig", "sequence", "start", {"highpass": 50}),
    "typing_mech_b": (KEYS, 0.0, 0.0, "typing", 1, "echte Tastatur, zweite Passage", "sequence", "start", {"highpass": 50}),
    "clock_timer": (TIMER, 88.0, 91.0, "clock", 2, "echtes Uhrwerk, 4 Ticks je Sekunde, loopt nahtlos", "bed", "start", {"exact": True}),
    "clock_timer_b": (TIMER, 16.0, 19.0, "clock", 1, "echtes Uhrwerk, zweite Passage", "bed", "start", {"exact": True}),
    "downer_vinyl": (VINYL, 0.0, 0.705, "downer", 2, "Vinyl-Scratch, nur auf Wunsch oder bei Bold Creator", "oneshot", "transient", {"auto_styles": ["bold"]}),
    "ding_real": (TIMER, 180.46, 182.0, "ding", 2, "echte Klingel der Küchenuhr, kurz", "oneshot", "transient", {}),
    "alarm_real": (TIMER, 180.46, 184.2, "alarm", 2, "echte Klingel der Küchenuhr, ganz, nur als Pointe", "oneshot", "start", {}),
}


def level(x, hop=240):
    m = np.mean(x ** 2, axis=1)
    k = len(m) // hop
    return 10 * np.log10(np.mean(m[:k * hop].reshape(k, hop), axis=1) + 1e-12)


def quiet_point(x, t, reach=0.15):
    """Nearest moment between two strokes: cuts in the gap, never into a stroke."""
    e = level(x)
    i = int(t * 200)
    a, b = max(0, i - int(reach * 200)), min(len(e), i + int(reach * 200))
    return (a + int(np.argmin(e[a:b]))) / 200


def calm_passage(x, seconds, avoid):
    """The passage with the most even strokes outside a given range."""
    from schnippo.sfx_profile import onsets
    e = level(x)
    w = int(seconds * 200)
    best = None
    for s in range(0, len(e) - w, 40):
        t = s / 200
        if avoid[0] - seconds < t < avoid[1]:
            continue
        on = onsets(e[s:s + w], 5.0, rise_db=8)
        if len(on) >= 20:
            v = float(e[s:s + w][on].std())
            best = (v, t) if best is None or v < best[0] else best
    return best[1]


def cut(src, a, b, opts):
    if opts.get("exact"):
        a, b = a - 0.06, b - 0.06  # just before a tick; the length stays a whole number of seconds, so it loops in step
    elif opts.get("highpass"):
        a, b = quiet_point(src, a), quiet_point(src, b)
    y = src[int(a * SR):int(b * SR)].copy()
    if "one_channel" in opts:  # the two channels of this recording cancel each other in a mono sum
        y = np.stack([y[:, opts["one_channel"]]] * 2, axis=1)
    if "highpass" in opts:
        y = highpass(y, opts["highpass"])
    return y, a, b


def main(folder):
    import generate
    folder = Path(folder)
    out, cache = [], {}
    for name, (who, a, b, cat, inten, desc, typ, align, opts) in CUTS.items():
        f = next(folder.glob(f"{who[0]}__*"))
        x = cache.setdefault(who[0], decode(f))
        if name == "typing_mech_b":
            a = calm_passage(x, 3.5, (30.0, 40.0))
            b = a + 3.5
        y, a, b = cut(x, a, b, opts)
        n = len(y)
        fi, fo = min(int(0.002 * SR), n // 8), min(int(0.012 * SR), n // 8)
        y[:fi] *= np.linspace(0, 1, fi)[:, None]
        y[-fo:] *= np.linspace(1, 0, fo)[:, None]
        y = y - y.mean(axis=0)
        y = y / np.abs(y).max() * 10 ** (-3 / 20)
        generate.write24(ROOT / "wav" / f"{name}.wav", y)
        m = measure(y)
        m["hit_offset_ms"] = 0 if align == "start" else m["hit_offset_ms"]
        extra = {"auto_styles": opts["auto_styles"]} if "auto_styles" in opts else {}
        changes = {"one_channel": "geschnitten, ein Kanal auf beide Seiten", "highpass": "geschnitten, Hochpass 50 Hz"}.get(next((k for k in opts if k not in ("exact", "auto_styles")), ""), "nur geschnitten")
        out.append({"id": name, "file": f"wav/{name}.wav", "category": cat, "intensity": inten, "description": desc, "type": typ, "event_align": align,
                    "reference": {"click": "click", "typing": "typing", "clock": "clock", "downer": "downer", "ding": "ding", "alarm": "clock"}[cat], "styles": generate.STYLES[cat], **m, **extra,
                    "true_peak_db": generate.true_peak_db(y), "license": "CC0", "source": f"Freesound {who[0]}: {who[2]}", "author": who[1], "url": who[3],
                    "cut_s": [round(a, 3), round(b, 3)], "changes": changes})
    (ROOT / "recorded.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(out)} Aufnahmen geschnitten")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(REPO.parent / "CC0-SFX"))
