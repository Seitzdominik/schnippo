"""Measured profile of a sound: only numbers and coarse curves. Used to derive target ranges from reference sounds, to compare
our own effects with them, and to rank candidates from external sources. Nothing here keeps, cuts or processes audio."""

from __future__ import annotations

import numpy as np

SR = 48000
BANDS = (("sub", 20, 60), ("low", 60, 250), ("mid", 250, 2000), ("high", 2000, 8000), ("air", 8000, 20000))
CURVE = 32  # points per curve: enough to compare shapes, far too coarse to hold any audio


def a_weight(f: np.ndarray) -> np.ndarray:
    """Power weighting of the ear: power spectra say a whoosh is all sub bass, the ear hears its air."""
    f2 = np.maximum(f, 1.0) ** 2
    ra = (12194 ** 2 * f2 ** 2) / ((f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * (f2 + 12194 ** 2))
    return (ra / ra[np.argmin(np.abs(f - 1000))]) ** 2


def _env(m2: np.ndarray, hop: int) -> np.ndarray:
    n = max(1, len(m2) // hop)
    return np.sqrt(np.mean(m2[:n * hop].reshape(n, hop), axis=1) + 1e-16)


def _db(v):
    return 20 * np.log10(np.maximum(v, 1e-8))


def _curve(v: np.ndarray, n: int = CURVE) -> list[float]:
    if len(v) == 0:
        return [0.0] * n
    pos = np.linspace(0, len(v) - 1, n)
    return [round(float(x), 2) for x in np.interp(pos, np.arange(len(v)), v)]


def _stft(m: np.ndarray, size: int, hop: int) -> np.ndarray:
    if len(m) < size:
        m = np.pad(m, (0, size - len(m)))
    idx = np.arange(0, len(m) - size + 1, hop)[:, None] + np.arange(size)
    return np.abs(np.fft.rfft(m[idx] * np.hanning(size), axis=1)) ** 2


def _t_fall(env_db: np.ndarray, start: int, drop: float, hop_ms: float) -> float | None:
    after = np.nonzero(env_db[start:] < env_db[start] - drop)[0]
    return round(float(after[0] * hop_ms), 1) if len(after) else None


def rt60(env_db: np.ndarray, peak: int, hop_ms: float) -> float | None:
    """Schroeder integration of the energy after the peak, slope between −5 and −25 dB."""
    e = 10 ** (env_db[peak:] / 10)
    if len(e) < 8:
        return None
    sch = 10 * np.log10(np.maximum(np.cumsum(e[::-1])[::-1], 1e-16) / max(e.sum(), 1e-16))
    i5, i25 = np.argmax(sch < -5), np.argmax(sch < -25)
    if i5 == 0 or i25 <= i5:
        return None
    return round(float(60 / (sch[i5] - sch[i25]) * (i25 - i5) * hop_ms), 0)


def partials(m: np.ndarray, sr: int, n_max: int = 8) -> list[dict]:
    """Strongest stable tones after the peak with their own decay time."""
    size, hop = 4096, 1024
    if len(m) < size:
        return []
    S = _stft(m, size, hop)
    f = np.fft.rfftfreq(size, 1 / sr)
    k0 = int(np.argmax(S.sum(axis=1)))
    spec = S[k0:k0 + max(2, min(12, len(S) - k0))].mean(axis=0)
    spec_db = 10 * np.log10(spec + 1e-16)
    top = spec_db[(f > 80) & (f < 16000)].max()
    cand = [i for i in range(2, len(spec) - 2) if 80 < f[i] < 16000 and spec_db[i] > top - 45 and spec[i] == spec[i - 2:i + 3].max()]
    # a peak must rise above its neighbourhood, or it is just noise
    cand = [i for i in cand if spec_db[i] - np.median(spec_db[max(0, i - 40):i + 40]) > 15]
    cand = sorted(cand, key=lambda i: -spec[i])[:n_max]
    out = []
    for i in sorted(cand):
        track = 10 * np.log10(S[k0:, i - 1:i + 2].sum(axis=1) + 1e-16)
        fall = np.nonzero(track < track[0] - 20)[0]
        t20 = float(fall[0] * hop / sr) if len(fall) else None
        out.append({"hz": round(float(f[i]), 1), "db": round(float(spec_db[i] - top), 1), "t60_s": round(3 * t20, 2) if t20 else None})
    return out


def onsets(env_db: np.ndarray, hop_ms: float, min_gap_ms: float = 25, rise_db: float = 6) -> list[int]:
    """Frames where the level jumps; rises from a slow average, so a loud tail hides nothing."""
    w = max(1, int(20 / hop_ms))
    base = np.convolve(env_db, np.ones(w) / w, mode="full")[:len(env_db)]
    base = np.concatenate([[env_db[0]], base[:-1]])
    top = env_db.max()
    out, last = [], -10 ** 6
    for i in range(1, len(env_db)):
        if env_db[i] - base[i] >= rise_db and env_db[i] > top - 40 and (i - last) * hop_ms >= min_gap_ms:
            j = i
            while j + 1 < len(env_db) and env_db[j + 1] > env_db[j]:
                j += 1
            out.append(j)
            last = j
    return out


def rhythm(env_db: np.ndarray, hop_ms: float, S: np.ndarray, f: np.ndarray, s_hop_ms: float) -> dict | None:
    on = onsets(env_db, hop_ms)
    if len(on) < 4:
        return None
    t = np.array(on) * hop_ms
    d = np.diff(t)
    lv = env_db[on]
    cents = []
    for o in on:
        fr = min(len(S) - 1, int(o * hop_ms / s_hop_ms))
        cents.append(float((S[fr] * f).sum() / max(S[fr].sum(), 1e-16)))
    c = np.array(cents)
    return {"hits": len(on), "interval_ms": round(float(np.median(d)), 1), "interval_sd_ms": round(float(d.std()), 1),
            "interval_p10_p90_ms": [round(float(np.percentile(d, 10)), 1), round(float(np.percentile(d, 90)), 1)],
            "level_sd_db": round(float(lv.std()), 1), "centroid_sd_hz": round(float(c.std()), 0),
            "even_odd_level_db": round(float(lv[::2].mean() - lv[1::2].mean()), 1),
            "even_odd_centroid_hz": round(float(c[::2].mean() - c[1::2].mean()), 0),
            "per_second": round(float(len(on) / max((t[-1] - t[0]) / 1000, 1e-3)), 2)}


def profile(x: np.ndarray, sr: int = SR, name: str = "") -> dict:
    """x: (n, 2) samples. Silence before and after is ignored."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    m2 = np.mean(x ** 2, axis=1)
    hop = sr // 200
    hop_ms = hop / sr * 1000
    env = _env(m2, hop)
    env_db = _db(env)
    top = env_db.max()
    act = np.nonzero(env_db > top - 50)[0]
    a, b = int(act[0]), int(act[-1]) + 1
    x, env_db = x[a * hop:b * hop], env_db[a:b]
    mono = x.mean(axis=1)
    side = (x[:, 0] - x[:, 1]) / 2
    sm = np.convolve(env_db, np.ones(3) / 3, mode="same")
    peak = int(np.argmax(sm))
    pre = np.nonzero(env_db[:peak + 1] < env_db[peak] - 20)[0]
    attack = (peak - pre[-1]) * hop_ms if len(pre) else peak * hop_ms
    S = _stft(np.pad(mono, 512), 1024, 256)  # padded: a click at the very start must not vanish under the window
    f = np.fft.rfftfreq(1024, 1 / sr)
    s_hop_ms = 256 / sr * 1000
    e = S.sum(axis=1)
    ok = e > e.max() * 10 ** (-40 / 10)
    lf = np.log2(np.maximum(f, 20))
    cen = (S * lf).sum(axis=1) / np.maximum(e, 1e-16)
    spread = np.sqrt(np.maximum((S * (lf[None, :] - cen[:, None]) ** 2).sum(axis=1) / np.maximum(e, 1e-16), 0))
    Sa = S * a_weight(f)[None, :]
    ea = Sa.sum(axis=1)
    cen_a = (Sa * lf).sum(axis=1) / np.maximum(ea, 1e-16)
    pk_s = min(len(cen) - 1, int(peak * hop_ms / s_hop_ms))
    idx = np.arange(len(cen))
    before = cen_a[ok & (idx < pk_s)]
    after = cen_a[ok & (idx > pk_s)]
    sweep_up = float(cen_a[pk_s] - np.median(before[:max(1, len(before) // 4)])) if len(before) >= 2 else 0.0
    sweep_down = float(np.median(after[-max(1, len(after) // 4):]) - cen_a[pk_s]) if len(after) >= 2 else 0.0
    band_e = S.sum(axis=0)
    total = band_e[(f >= 20)].sum() + 1e-16
    bands = {n: round(float(band_e[(f >= lo) & (f < hi)].sum() / total * 100), 1) for n, lo, hi in BANDS}
    # tonal vs noise: flatness per frame, loud frames count
    rng = (f > 100) & (f < min(16000, sr / 2 - 500))
    fl = np.exp(np.mean(np.log(S[:, rng] + 1e-16), axis=1)) / np.maximum(S[:, rng].mean(axis=1), 1e-16)
    flat = float((fl * e).sum() / max(e.sum(), 1e-16))
    # layers: where each band peaks relative to the hit and how fast it falls
    layers = {}
    for n, lo, hi in BANDS:
        be = S[:, (f >= lo) & (f < hi)].sum(axis=1)
        if be.sum() / (e.sum() + 1e-16) < 0.01:
            continue
        bd = 10 * np.log10(be + 1e-16)
        k = int(np.argmax(bd))
        layers[n] = {"peak_ms": round((k - pk_s) * s_hop_ms), "fall20_ms": _t_fall(bd, k, 20, s_hop_ms)}
    # stereo
    me, se = float((mono ** 2).sum()), float((side ** 2).sum())
    l, r = x[:, 0], x[:, 1]
    corr = float((l * r).sum() / max(np.sqrt((l ** 2).sum() * (r ** 2).sum()), 1e-12))
    el, er = _env(l ** 2, hop), _env(r ** 2, hop)
    loud = env_db[:len(el)] > env_db.max() - 25
    pan = (er ** 2 - el ** 2) / np.maximum(er ** 2 + el ** 2, 1e-16)
    pan_l = pan[loud[:len(pan)]] if loud.any() else pan
    tail = int(peak + 80 / hop_ms)
    energy = 10 ** (env_db / 10)
    out = {"name": name, "duration_ms": round(len(x) / sr * 1000), "attack_ms": round(float(attack), 1), "hit_ms": round(peak * hop_ms),
           "hit_pos": round(peak / max(1, len(env_db) - 1), 3), "rise_db_per_ms": round(float(np.max(np.diff(env_db)) / hop_ms), 2) if len(env_db) > 1 else 0.0,
           "fall20_ms": _t_fall(sm, peak, 20, hop_ms), "fall40_ms": _t_fall(sm, peak, 40, hop_ms),
           "crest_db": round(float(_db(np.abs(x).max()) - 10 * np.log10(np.mean(x ** 2) + 1e-16)), 1),
           "centroid_hz": round(float(2 ** ((cen * e).sum() / max(e.sum(), 1e-16)))),
           "centroid_a_hz": round(float(2 ** ((cen_a * ea).sum() / max(ea.sum(), 1e-16)))), "bandwidth_oct": round(float((spread * e).sum() / max(e.sum(), 1e-16)), 2),
           "sweep_up_oct": round(sweep_up, 2), "sweep_down_oct": round(sweep_down, 2), "bands_pct": bands, "flatness": round(flat, 3),
           "side_mid_db": round(10 * np.log10(max(se, 1e-16) / max(me, 1e-16)), 1), "correlation": round(corr, 3),
           "pan_range": round(float(np.percentile(pan_l, 95) - np.percentile(pan_l, 5)), 2) if len(pan_l) else 0.0,
           "pan_move": round(float(np.mean(pan_l[-max(1, len(pan_l) // 4):]) - np.mean(pan_l[:max(1, len(pan_l) // 4)])), 2) if len(pan_l) else 0.0,
           "mono_loss_db": round(10 * np.log10(max(2 * me, 1e-16) / max(float((l ** 2).sum() + (r ** 2).sum()), 1e-16)), 1),
           "rt60_ms": rt60(env_db, peak, hop_ms), "tail_share": round(float(energy[tail:].sum() / max(energy.sum(), 1e-16)), 3) if tail < len(energy) else 0.0,
           "layers": layers, "partials": partials(mono, sr),
           "rhythm": rhythm(env_db, hop_ms, S, f, s_hop_ms),
           "curves": {"envelope_db": _curve(env_db - env_db.max()), "centroid_hz": _curve(2 ** cen_a), "bandwidth_oct": _curve(spread), "pan": _curve(pan)}}
    return out


SCALARS = ("duration_ms", "attack_ms", "hit_pos", "fall20_ms", "centroid_hz", "centroid_a_hz", "bandwidth_oct", "sweep_up_oct", "sweep_down_oct", "flatness",
           "side_mid_db", "correlation", "pan_range", "rt60_ms", "tail_share", "crest_db")


def group_ranges(profiles: list[dict]) -> dict:
    """min / median / max of the scalars and band shares; the target ranges for synthesis."""
    out: dict = {"n": len(profiles)}
    for k in SCALARS:
        v = [p[k] for p in profiles if p.get(k) is not None]
        if v:
            out[k] = [round(float(np.min(v)), 3), round(float(np.median(v)), 3), round(float(np.max(v)), 3)]
    for b, *_ in BANDS:
        v = [p["bands_pct"][b] for p in profiles]
        out[f"band_{b}"] = [round(float(np.min(v)), 1), round(float(np.median(v)), 1), round(float(np.max(v)), 1)]
    return out


# distance: how many "widths" a value lies outside the group range; 0 = inside
WEIGHTS = {"attack_ms": 1, "fall20_ms": 1, "centroid_a_hz": 1.5, "bandwidth_oct": 1, "flatness": 1, "side_mid_db": 1, "rt60_ms": 1, "tail_share": 1,
           "band_sub": 0.5, "band_low": 0.75, "band_mid": 0.75, "band_high": 0.75, "band_air": 0.5}
LOG_SCALE = {"attack_ms", "fall20_ms", "centroid_a_hz", "rt60_ms"}


def distance(p: dict, ranges: dict, skip: tuple = ()) -> dict:
    """Per value and in total: 0 inside the range; outside, the gap relative to the range's size (log scale for times and Hz).
    skip: values that say nothing here, e.g. reverb of a sequence of hits, where the next hit looks like a tail."""
    parts: dict[str, float] = {}
    for k, w in WEIGHTS.items():
        if k in skip:
            continue
        r = ranges.get(k)
        v = p["bands_pct"][k[5:]] if k.startswith("band_") else p.get(k)
        if r is None or v is None:
            continue
        lo, hi = r[0], r[2]
        if k in LOG_SCALE:
            floor = 10.0 if k == "attack_ms" else 0.5  # the envelope has 5-ms steps: below 10 ms means "at once"
            v, lo, hi = np.log2(max(v, floor)), np.log2(max(lo, floor)), np.log2(max(hi, floor))
            pad = max(hi - lo, 1.0)
        elif k.startswith("band_"):
            pad = max(hi - lo, 15.0)
        elif k == "side_mid_db":
            pad = max(hi - lo, 6.0)
        else:
            pad = max(hi - lo, 0.1)
        gap = max(lo - v, v - hi, 0.0) / pad
        if gap > 0:
            parts[k] = round(float(gap * w), 2)
    return {"total": round(sum(parts.values()), 2), "outside": parts}
