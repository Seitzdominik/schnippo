"""Generates the shipped sound effects with numpy, fixed seeds, no recorded material of any kind: reproducible and entirely ours (MIT).

    uv run python sfx/generate.py        → sfx/wav/*.wav (48 kHz, 24 bit, stereo), sfx/library.json

The targets (durations, spectra, width, reverb) come from measured key figures (data/sfx/analysis/groups.json); every effect is built from scratch from layers."""

import json
import sys
import wave
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
ROOT = REPO / "src" / "schnippo" / "data" / "sfx"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(TOOLS))
from schnippo.sfx import measure  # noqa: E402
from synth import (SR, add, band, burst, colored, const, finish, flutter, glide, highpass, lowpass, modes, pair, place, reverb, rnd, saturate,  # noqa: E402
                   smooth, stereo, swell, varispeed)


# ---------------------------------------------------------------- air
def whoosh(dur, seed, lo=180, hi=900, back=260, peak=0.55, width=1.1, body=0.7, sub=0.3, air=0.08, pan=(-0.5, 0.5), corr=0.65, rt=0.5, wet=0.12, rise=2.2, fall=2.6):
    """Moving air: a broad band sweeping up and falling away (Doppler), a pressure layer below, a little hiss at the moment of passing."""
    rng = rnd(seed)
    n = int(dur * SR)
    e = swell(n, peak, rise, fall) * flutter(n, rng, 22, 0.16)
    c = glide((0, lo), (peak, hi), (1, back))
    a, b = pair(lambda r: band(dur, c, const(width), r, jitter=0.1), rng, corr)
    lows = glide((0, 90), (peak, 150), (1, 70))
    p, q = pair(lambda r: band(dur, lows, const(0.8), r, slope=-0.9, jitter=0.06), rng, corr + 0.15)
    ee = swell(n, peak, rise * 1.5, fall * 1.3)
    l, r = a * e + body * p * ee, b * e + body * q * ee
    if air:
        h, g = pair(lambda r_: band(dur, glide((0, 2200), (peak, 4800), (1, 1800)), const(0.9), r_), rng, 0.3)
        ea = swell(n, peak, 5, 6)
        l, r = l + air * h * ea, r + air * g * ea
    if sub:
        t = np.arange(n) / SR
        f = 58 + 62 * np.exp(-np.maximum(t - peak * dur, 0) / 0.12)
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * swell(n, peak, 4, 3)
        l, r = l + sub * 1.4 * s, r + sub * 1.4 * s
    x = place(stereo(l, r), np.interp(np.linspace(0, 1, n), [0, peak, 1], [pan[0], (pan[0] + pan[1]) / 2 + 0.1 * rng.standard_normal(), pan[1]]))
    return reverb(saturate(x / np.abs(x).max(), 1.2), rt, wet, damp=0.5)


# ---------------------------------------------------------------- strikes
def impact(dur, seed, f0=118, f1=46, tau=0.55, boom=0.85, crack=0.05, rt=2.4, wet=0.3, drive=1.7, wide=0.9):
    """Sub drop + rumble + contact + room. The rumble wanders between the channels, as measured."""
    rng = rnd(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.09)
    f = f * (1 + 0.012 * smooth(n, 7, rng))
    ph = 2 * np.pi * np.cumsum(f) / SR
    e = (1 - np.exp(-t / 0.012)) * np.exp(-t / tau)
    core = 0.8 * saturate((np.sin(ph) + 0.35 * np.sin(2 * ph) * np.exp(-t / 0.25)) * e, drive)
    a, b = pair(lambda r: band(dur, glide((0, 170), (0.25, 95), (1, 60)), const(0.9), r, slope=-1.0, jitter=0.12), rng, 1 - wide)
    er = (1 - np.exp(-t / 0.02)) * np.exp(-t / (tau * 1.25)) * flutter(n, rng, 9, 0.3)
    l, r = core + boom * a * er, core + boom * b * er
    x = stereo(l, r)
    if crack:
        c = burst(4, rng, 1400, 1.4)
        x = add(x, crack * stereo(c) * np.abs(x).max() * 6)
    x = x / np.abs(x).max()
    return reverb(lowpass(x, 1500), rt, wet, predelay=0.02, damp=0.72, size=1.3, width=1.4, tail=min(rt * 0.5, 1.2))


def pop(f0, f1, drop_ms, decay_ms, seed, rt=0.18, wet=0.1):
    rng = rnd(seed)
    n = int((decay_ms / 1000 * 7 + 0.02) * SR)
    t = np.arange(n) / SR
    f = (f1 + (f0 - f1) * np.exp(-t / (drop_ms / 1000))) * (1 + 0.004 * smooth(n, 40, rng))
    ph = 2 * np.pi * np.cumsum(f) / SR
    e = (1 - np.exp(-t / 0.0015)) * np.exp(-t / (decay_ms / 1000))
    y = saturate((np.sin(ph) + 0.18 * np.sin(2.02 * ph) * np.exp(-t / 0.012)) * e, 1.3)
    b = burst(1.2, rng, 900, 1.6)
    y[:len(b)] += 0.1 * b
    return reverb(stereo(y), rt, wet, predelay=0.004, damp=0.5, size=0.5)


def bell(table, dur, seed, attack_ms=2.0, detune=0.0012, rt=1.4, wet=0.22, width=1.0, drift=0.0, strike=0.03):
    """Inharmonic partials with their own decay, each a slightly beating pair; a soft strike; a room."""
    rng = rnd(seed)
    y = modes(table, dur, rng, attack_ms, detune)
    y = y / np.abs(y).max()
    b = burst(1.0, rng, table[0][0] * 2.2, 1.0)
    y[:len(b)] += strike * b
    n = len(y)
    l, r = y * (1 + 0.03 * smooth(n, 3, rng)), y * (1 + 0.03 * smooth(n, 3, rng))
    x = place(stereo(l, r), drift * np.linspace(-1, 1, n))
    return reverb(x, rt, wet, predelay=0.018, damp=0.3, width=width * 0.9, tail=rt)


def sequence(notes, seed, **kw):
    """Several struck notes, one after the other (table, offset s, level)."""
    return add(*[(lvl * bell(tb, 1.1, seed + k, rt=0.05, wet=0.001, **{a: b for a, b in kw.items() if a in ("attack_ms", "detune")}), off) for k, (tb, off, lvl) in enumerate(notes)])


# ---------------------------------------------------------------- rising
def riser(dur, seed, lo=240, hi=1700, tone=0.12, pulse=(5, 18), low=1.3, rt=1.2, wet=0.28):
    """Band noise opening upward, a rising drone, a tremolo that gets faster. Stops dead on the event: the tail belongs to what follows."""
    rng = rnd(seed)
    n = int(dur * SR)
    tt = np.linspace(0, 1, n)
    a, b = pair(lambda r: band(dur, glide((0, lo), (1, hi)), lambda t: 1.0 - 0.35 * t, r, jitter=0.05), rng, 0.45)
    e = tt ** (np.log(0.1) / np.log(1 - 0.7 / max(dur, 1.0))) + 0.05 * tt ** 1.2  # a quiet start, the last 0.7 s carry the rise
    rate = pulse[0] + (pulse[1] - pulse[0]) * tt ** 2
    trem = 0.72 + 0.28 * np.sin(2 * np.pi * np.cumsum(rate) / SR)
    l, r = a * e * trem, b * e * trem
    f = 52 * 2.2 ** tt * (1 + 0.004 * smooth(n, 5, rng))
    ph = 2 * np.pi * np.cumsum(f) / SR
    d = (np.sin(ph) + 0.5 * np.sin(2 * ph + 0.4) + 0.25 * np.sin(3 * ph + 1.0)) * e
    l, r = l + low * d, r + low * d
    if tone:
        ph2 = 2 * np.pi * np.cumsum(330 * 2.0 ** (1.4 * tt)) / SR
        s = (np.sin(ph2) + 0.4 * np.sin(1.5 * ph2 + 0.3)) * e
        l, r = l + tone * s, r + tone * np.sin(ph2 + 0.5) * e
    x = stereo(l, r) / max(np.abs(l).max(), np.abs(r).max())
    y = reverb(x, rt, wet, damp=0.45, tail=0.0001)
    y = y[:n]
    y[-int(0.012 * SR):] *= np.linspace(1, 0, int(0.012 * SR))[:, None]
    return y


def riser_impact(rise, seed, tail=1.9):
    r = riser(rise, seed, tone=0.1)
    i = impact(tail, seed + 3, f0=128, f1=46, tau=0.5, rt=2.3, wet=0.3)
    return add(0.8 * r, (1.0 * i, rise - 0.005))


def reverse_swell(dur, seed):
    """A strike's reverb played backwards: our own strike, our own reverb."""
    rng = rnd(seed)
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    y = band(0.12, const(170), const(1.5), rng, slope=-0.8) * np.exp(-t / 0.03)
    w = reverb(stereo(y), dur * 1.5, 0.95, predelay=0.0, damp=0.55, size=1.2, width=0.55, tail=dur)[:int(dur * SR)]
    return w[::-1]


# ---------------------------------------------------------------- stop
def tape_stop(dur, seed):
    """A short own music-like chord that slows to a stop: falling pitch, slowing, closing lowpass."""
    rng = rnd(seed)
    src_d = dur * 1.1
    n = int(src_d * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for f, a in ((82, 1.0), (165, 0.7), (660, 0.6), (831, 0.5), (1320, 0.6), (1980, 0.45)):
        ph = 2 * np.pi * f * t * (1 + 0.002 * rng.standard_normal())
        y += a * (np.sin(ph) + 0.33 * np.sin(3 * ph) + 0.15 * np.sin(5 * ph))
    y += 0.5 * band(src_d, const(1800), const(1.6), rng)
    x = stereo(saturate(y / np.abs(y).max(), 2.0), saturate(np.roll(y, 7) / np.abs(y).max(), 2.0))
    m = int(dur * SR)
    rate = (1 - np.linspace(0, 1, m)) ** 0.8
    z = varispeed(x, rate)
    fade = np.linspace(1, 0.02, len(z)) ** 9 * (1 - np.exp(-np.arange(len(z)) / SR / 0.03))
    return lowpass(z * fade[:, None], 7000)


# ---------------------------------------------------------------- contact
def press(rng, body, snap, level=1.0, body_level=0.35, snap_ms=(0.7, 1.4), width=1.9):
    """One contact: a broad noise snap and a small resonant body, slightly different each time."""
    k = rng.uniform(0.96, 1.04)
    table = [(f * k, a * rng.uniform(0.8, 1.2), t60 * rng.uniform(0.85, 1.15)) for f, a, t60 in body]
    y = modes(table, 0.05, rng, attack_ms=0.1)
    b = burst(rng.uniform(*snap_ms), rng, snap * k, width)
    y = y / (np.abs(y).max() + 1e-12) * body_level
    y[:len(b)] += b
    return y * level


MOUSE = [(700, 0.7, 0.05), (1900, 0.8, 0.036), (3400, 1.0, 0.028), (5600, 0.7, 0.018)]


def ui_tick(seed, scale, snap):
    """One contact of a small button: the first half of a click."""
    rng = rnd(seed)
    table = [(f * scale, a, t) for f, a, t in MOUSE]
    p, q = press(rng, table, snap, 1.0, body_level=0.28), press(rng, table, snap * 1.1, 1.0, body_level=0.28)
    n = min(len(p), len(q))
    return stereo(p[:n], 0.85 * p[:n] + 0.15 * q[:n])


def alarm(dur, seed, f=1004, ring=24, on=0.9, off=0.22):
    """Mechanical alarm: a clapper striking two gongs fast, the harmonics of the measured kind, in bursts."""
    rng = rnd(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for k, a in ((2, 1.0), (3, 0.6), (4, 0.9), (5, 0.5), (7, 0.33), (8, 0.42), (9, 0.28), (10, 0.5)):
        y += a * np.sin(2 * np.pi * f * k * (1 + 0.0015 * rng.standard_normal()) * t + rng.uniform(0, 6))
    c = (np.sin(2 * np.pi * ring * t) > 0).astype(float)
    c = np.convolve(c, np.ones(96) / 96, mode="same")
    gate = ((t % (on + off)) < on).astype(float)
    gate = np.convolve(gate, np.ones(480) / 480, mode="same")
    y = saturate(y / np.abs(y).max() * c * gate * (0.8 + 0.2 * smooth(n, 11, rng)), 1.5)
    return reverb(stereo(y, np.roll(y, 18)), 0.5, 0.12, predelay=0.006, damp=0.3, size=0.6)


BELL_RATIOS = ((1.0, 1.0, 2.0), (2.01, 0.09, 0.5), (2.61, 0.13, 0.42), (3.77, 0.05, 1.1), (4.92, 0.02, 0.7))


def tbl(f0, ratios=BELL_RATIOS, scale=1.0):
    return [(f0 * r, a, t * scale) for r, a, t in ratios]


# id: category, intensity, description, reference group (None = no reference), type, event_align, sound
EFFECTS = {
    "whoosh_soft": ("whoosh", 1, "weich, luftig", "whoosh", "oneshot", "transient", lambda: whoosh(0.75, 11, 170, 620, 230, 0.55, sub=0.15, air=0.05)),
    "whoosh_mid": ("whoosh", 2, "rund, von links nach rechts", "whoosh", "oneshot", "transient", lambda: whoosh(1.0, 21, 150, 760, 210, 0.5, pan=(-0.7, 0.7), rt=0.7, wet=0.16)),
    "whoosh_big": ("whoosh", 3, "cinematisch, mit Körper und Raum", "whoosh", "oneshot", "transient", lambda: whoosh(1.3, 31, 110, 860, 180, 0.42, body=0.95, sub=0.5, rt=1.3, wet=0.22, pan=(-0.35, 0.35), fall=2.9)),
    "whoosh_end": ("whoosh", 2, "kurz, tief, endet hart", "whoosh", "oneshot", "transient", lambda: whoosh(0.62, 41, 90, 330, 120, 0.72, width=1.0, body=1.1, sub=0.7, air=0.0, rt=0.4, wet=0.08, rise=1.6, fall=1.5)),
    "swish_soft": ("swish", 1, "luftig, schnell", "whoosh", "oneshot", "transient", lambda: whoosh(0.32, 51, 260, 780, 360, 0.5, width=1.2, body=0.4, sub=0.0, air=0.04, rt=0.3, wet=0.1, pan=(-0.25, 0.25))),
    "swish_mid": ("swish", 2, "knapp", "whoosh", "oneshot", "transient", lambda: whoosh(0.4, 61, 300, 880, 400, 0.55, width=1.1, body=0.4, sub=0.0, air=0.06, rt=0.35, wet=0.1, pan=(-0.5, 0.5))),
    "swish_bright": ("swish", 3, "hell", "whoosh", "oneshot", "transient", lambda: whoosh(0.5, 71, 340, 1050, 480, 0.5, width=1.0, body=0.35, sub=0.0, air=0.1, rt=0.4, wet=0.1, pan=(-0.6, 0.6))),
    "pop_soft": ("pop", 1, "weich, tief", None, "oneshot", "transient", lambda: pop(560, 200, 24, 30, 81)),
    "pop_mid": ("pop", 2, "rund", None, "oneshot", "transient", lambda: pop(820, 280, 22, 26, 82)),
    "pop_bright": ("pop", 3, "knackig", None, "oneshot", "transient", lambda: pop(1300, 480, 15, 18, 83)),
    "tick_soft": ("tick", 1, "Holz, leise", "click", "oneshot", "transient", lambda: ui_tick(91, 1.0, 4800)),
    "tick_mid": ("tick", 2, "Kunststoff", "click", "oneshot", "transient", lambda: ui_tick(92, 1.15, 5600)),
    "tick_bright": ("tick", 3, "hell, trocken", "click", "oneshot", "transient", lambda: ui_tick(93, 1.3, 6800)),
    "ding_glass": ("ding", 1, "Glas, ein Ton", "ding", "oneshot", "transient", lambda: bell([(2640, 1, 1.8), (5300, 0.12, 0.6), (6880, 0.2, 0.42), (9920, 0.08, 1.1)], 1.5, 111, attack_ms=4, rt=1.2, wet=0.16)),
    "ding_bell": ("ding", 2, "kleine Glocke", "ding", "oneshot", "transient", lambda: bell([(2980, 1, 2.2), (5960, 0.04, 0.9), (7470, 0.8, 0.6), (13300, 0.1, 0.32)], 1.8, 112, attack_ms=1.5, rt=1.3, wet=0.2)),
    "ding_notify": ("ding", 2, "Benachrichtigung, zwei Lagen", "ding", "oneshot", "transient", lambda: bell([(1340, 0.45, 2.4), (2680, 1, 1.7), (4050, 0.08, 0.7), (13900, 0.06, 0.38)], 1.6, 113, attack_ms=6, rt=1.6, wet=0.24, width=0.9)),
    "ding_chime": ("ding", 3, "Dreiklang, leicht versetzt", "ding", "oneshot", "transient", lambda: reverb(sequence([(tbl(1680, scale=0.9), 0.0, 0.8), (tbl(2110, scale=0.9), 0.04, 0.8), (tbl(2830, scale=0.9), 0.08, 1.0)], 114, attack_ms=2.5), 1.5, 0.28, predelay=0.02, damp=0.3, width=1.2)),
    "ding_bright": ("ding", 3, "hell, breit", "ding", "oneshot", "transient", lambda: bell([(2110, 1, 1.1), (4220, 0.3, 0.9), (5900, 0.55, 0.33), (9540, 0.7, 0.38)], 1.2, 115, attack_ms=2, rt=1.35, wet=0.3, drift=0.28)),
    "impact_soft_low": ("impact_soft", 1, "sehr weich", "impact", "oneshot", "transient", lambda: impact(1.4, 121, f0=92, f1=46, tau=0.42, boom=0.5, crack=0.0, rt=2.0, wet=0.24)),
    "impact_soft_mid": ("impact_soft", 2, "weich", "impact", "oneshot", "transient", lambda: impact(1.7, 122, f0=108, f1=48, tau=0.5, boom=0.55, crack=0.02, rt=2.3, wet=0.26)),
    "impact_boom": ("impact", 2, "Boom, tief und breit", "impact", "oneshot", "transient", lambda: impact(2.0, 131, f0=120, f1=44, tau=0.62, boom=0.65, crack=0.04, rt=2.6, wet=0.3)),
    "impact_hit": ("impact", 3, "Schlag mit Kontakt", "impact", "oneshot", "transient", lambda: impact(2.0, 132, f0=150, f1=46, tau=0.5, boom=0.35, crack=0.1, rt=2.6, wet=0.3, drive=2.2)),
    "riser_short": ("riser", 1, "1,5 s, endet auf dem Ereignis", "riser", "oneshot", "end", lambda: riser(1.5, 141, tone=0.08, pulse=(6, 20))),
    "riser_long": ("riser", 2, "2,4 s, mit Ton", "riser", "oneshot", "end", lambda: riser(2.4, 142, tone=0.14, pulse=(3, 16))),
    "riser_swell": ("riser", 1, "rückwärts laufender Hall, 2 s", "riser", "oneshot", "end", lambda: reverse_swell(2.0, 143)),
    "riser_impact": ("riser", 3, "Riser 2 s mit Impact auf dem Ereignis", "riser", "oneshot", "transient", lambda: riser_impact(2.0, 144)),
    "downer_tape": ("downer", 2, "Bandstopp", "downer", "oneshot", "transient", lambda: tape_stop(0.85, 151)),
    "alarm_bell": ("alarm", 2, "Wecker, nur als Pointe", "clock", "oneshot", "start", lambda: alarm(1.9, 181)),
}


def write24(path, x):
    rng = rnd(1)
    q = x * (2 ** 23 - 1) + (rng.random(x.shape) - rng.random(x.shape))  # TPDF dither
    v = np.clip(np.round(q), -2 ** 23, 2 ** 23 - 1).astype("<i4").reshape(-1)
    b = v.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(3)
        w.setframerate(SR)
        w.writeframes(b)


def true_peak_db(x):
    k = 4
    best = 0.0
    for c in range(x.shape[1]):
        s = np.fft.rfft(x[:, c])
        y = np.fft.irfft(np.concatenate([s, np.zeros(len(s) * (k - 1))]), len(x) * k) * k
        best = max(best, float(np.abs(y).max()))
    return round(20 * np.log10(best), 1)


STYLES = {"whoosh": ["bold", "soft", "minimal"], "swish": ["bold", "soft", "minimal"], "pop": ["bold"], "tick": ["tech", "minimal", "bold"], "click": ["tech", "minimal", "bold"],
          "ding": ["soft", "bold", "tech"], "impact_soft": ["bold", "minimal", "soft"], "impact": ["bold"], "riser": ["bold"], "downer": ["bold"], "typing": ["tech", "bold"],
          "clock": ["tech", "bold", "minimal"], "alarm": ["bold"]}


def build(only=None):
    """{id: samples} of all effects, or of those named."""
    floors = {"impact": -46.0, "impact_soft": -46.0, "ding": -50.0, "riser": -48.0}
    return {k: finish(v[6](), floor_db=floors.get(v[0], -58.0)) for k, v in EFFECTS.items() if only is None or k in only}


def main():
    out = ROOT / "wav"
    out.mkdir(exist_ok=True)
    rec_file = ROOT / "recorded.json"  # real CC0 recordings, cut by recorded.py
    recorded = json.loads(rec_file.read_text(encoding="utf-8")) if rec_file.exists() else []
    keep = {Path(e["file"]).name for e in recorded}
    for old in out.glob("*.wav"):
        if old.name not in keep:
            old.unlink()
    effects, total = [], sum((ROOT / e["file"]).stat().st_size for e in recorded)
    for name, x in build().items():
        cat, inten, desc, group, typ, align, _ = EFFECTS[name]
        f = out / f"{name}.wav"
        write24(f, x)
        total += f.stat().st_size
        m = measure(x)
        if name == "riser_impact":  # the riser hides the onset from the level: the gap before the impact marks it
            env = np.abs(x).max(axis=1)
            w = SR // 200
            lv = 20 * np.log10(np.array([env[i:i + w].max() for i in range(0, len(env) - w, w)]) + 1e-9)
            a, b = int(1.6 * 200), int(2.3 * 200)
            m["hit_offset_ms"] = (a + int(np.argmax(lv[a + 2:b] - lv[a:b - 2])) + 2) * 5
        if align == "end":
            m["hit_offset_ms"] = m["duration_ms"]
        elif align == "start":
            m["hit_offset_ms"] = 0
        effects.append({"id": name, "file": f"wav/{name}.wav", "category": cat, "intensity": inten, "description": desc, "type": typ, "event_align": align, "reference": group,
                        "styles": STYLES[cat], **m, "true_peak_db": true_peak_db(x), "license": "MIT (selbst erzeugt)"})
    effects = sorted(effects + recorded, key=lambda e: (list(STYLES).index(e["category"]), e["id"]))
    (ROOT / "library.json").write_text(json.dumps({"version": 2, "sample_rate": SR, "bit_depth": 24, "effects": effects}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_licenses(effects)
    print(f"{len(effects)} Effekte, davon {len(recorded)} Aufnahmen, {total / 1e6:.2f} MB")


def write_licenses(effects):
    rows = []
    for e in effects:
        if e["license"] == "CC0":
            rows.append(f"| `{e['file']}` | {e['category']} | {e['source']}, Ausschnitt {e['cut_s'][0]:g}–{e['cut_s'][1]:g} s ({e['changes']}) | {e['author']} | CC0 | [Freesound]({e['url']}) |")
        else:
            rows.append(f"| `{e['file']}` | {e['category']} | selbst erzeugt (`sfx/generate.py`) | Schnippo | MIT | [LICENSE](../LICENSE) |")
    text = (ROOT / "LICENSES.md").read_text(encoding="utf-8")
    head, _, rest = text.partition("|---|---|---|---|---|---|\n")
    tail = rest[rest.index("\n\n"):]
    (ROOT / "LICENSES.md").write_text(head + "|---|---|---|---|---|---|\n" + "\n".join(rows) + tail, encoding="utf-8")


if __name__ == "__main__":
    main()
