"""Building blocks of the generator: shaped noise, modal resonators, a Freeverb-style reverb, stereo tools. numpy only."""

import numpy as np

SR = 48000
N, HOP = 2048, 256


def rnd(seed):
    return np.random.default_rng(seed)


def smooth(n, hz, rng):
    """Random curve around 0 (sd ≈ 1) that moves at about hz: nothing in nature is a clean line."""
    k = max(2, int(n / SR * hz * 2) + 2)
    p = rng.standard_normal(k)
    return np.interp(np.linspace(0, k - 1, n), np.arange(k), p)


def colored(n, rng, slope=-0.5):
    """Noise with amplitude ∝ f^slope (−0.5 pink, −1 brown)."""
    s = np.fft.rfft(rng.standard_normal(n + 1024))
    f = np.maximum(np.fft.rfftfreq(n + 1024, 1 / SR), 20.0)
    y = np.fft.irfft(s * f ** slope, n + 1024)[:n]
    return y / (y.std() + 1e-12)


def band(dur, center, width, rng, slope=-0.5, jitter=0.0):
    """Noise through a Gaussian band (in octaves) that follows center(t), width(t), t in 0..1. Shaped in the frequency domain,
    so there is no filter ringing. jitter: random wobble of the centre in octaves (turbulence)."""
    n = int(dur * SR)
    x = colored(n + 2 * N, rng, slope)
    wob = smooth(len(x), 14, rng) * jitter
    win = np.hanning(N)
    out, norm = np.zeros(len(x)), np.zeros(len(x))
    f = np.maximum(np.fft.rfftfreq(N, 1 / SR), 1.0)
    lf = np.log2(f)
    for i in range(0, len(x) - N, HOP):
        t = min(max((i - N / 2) / SR, 0.0), dur) / dur
        c = np.log2(center(t)) + wob[i]
        g = np.exp(-0.5 * ((lf - c) / width(t)) ** 2)
        out[i:i + N] += np.fft.irfft(np.fft.rfft(x[i:i + N] * win) * g) * win
        norm[i:i + N] += win ** 2
    y = (out / np.maximum(norm, 1e-6))[N // 2:N // 2 + n]
    return y / (y.std() + 1e-12)


def const(v):
    return lambda t: v


def glide(*points):
    """Curve through (t, value) points, geometric between them."""
    ts = [p[0] for p in points]
    vs = np.log([p[1] for p in points])
    return lambda t: float(np.exp(np.interp(t, ts, vs)))


def swell(n, peak, rise=2.0, fall=2.6):
    t = np.linspace(0, 1, n)
    up = np.sin(np.clip(t / peak, 0, 1) * np.pi / 2) ** rise
    down = np.cos(np.clip((t - peak) / (1 - peak), 0, 1) * np.pi / 2) ** fall
    return np.where(t < peak, up, down)


def flutter(n, rng, hz=18, depth=0.25):
    """Amplitude turbulence: rough at the hz given, never periodic."""
    return np.clip(1 + depth * smooth(n, hz, rng), 0.05, None)


def saturate(x, drive=1.5):
    return np.tanh(x * drive) / np.tanh(drive)


def lowpass(x, hz):
    """Gentle lowpass by frequency-domain roll-off (x: 1-D or (n, 2))."""
    s = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = 1 / np.sqrt(1 + (f / hz) ** 4)
    return np.fft.irfft(s * (g if x.ndim == 1 else g[:, None]), len(x), axis=0)


def highpass(x, hz):
    s = np.fft.rfft(x, axis=0)
    f = np.maximum(np.fft.rfftfreq(len(x), 1 / SR), 0.1)
    g = 1 / np.sqrt(1 + (hz / f) ** 4)
    return np.fft.irfft(s * (g if x.ndim == 1 else g[:, None]), len(x), axis=0)


def stereo(l, r=None):
    return np.stack([l, l if r is None else r], axis=1)


def place(x, pan):
    """Equal-power panning of a mono signal or a stereo pair; pan −1..1, scalar or per sample."""
    th = (np.clip(pan, -1, 1) + 1) * np.pi / 4
    if x.ndim == 1:
        return np.stack([x * np.cos(th), x * np.sin(th)], axis=1) * np.sqrt(2)
    return np.stack([x[:, 0] * np.cos(th), x[:, 1] * np.sin(th)], axis=1) * np.sqrt(2)


def pair(make, rng, corr):
    """Two signals with correlation corr: width without a hole in the middle (mono-safe)."""
    a, b = make(rng), make(rng)
    return a, corr * a + np.sqrt(1 - corr ** 2) * b


def add(*parts):
    """Sum of (signal, offset in s) of different lengths; plain arrays start at 0."""
    items = [(p, 0.0) if not isinstance(p, tuple) else p for p in parts]
    n = max(int(o * SR) + len(p) for p, o in items)
    out = np.zeros((n, 2))
    for p, o in items:
        s = int(o * SR)
        out[s:s + len(p)] += p if p.ndim == 2 else p[:, None]
    return out


def _comb(x, d, g, damp):
    y = np.zeros(len(x) + d + 1)
    for s in range(0, len(x), d):
        e = min(s + d, len(x))
        k = e - s
        fb = (1 - damp) * y[s + 1:s + 1 + k] + damp * y[s:s + k]
        y[s + d + 1:s + d + 1 + k] = x[s:e] + g * fb
    return y[d + 1:]


def _allpass(x, d, g=0.5):
    b = np.zeros(len(x) + d)
    y = np.zeros(len(x))
    for s in range(0, len(x), d):
        e = min(s + d, len(x))
        k = e - s
        fb = b[s:s + k]
        b[s + d:s + d + k] = x[s:e] + g * fb
        y[s:e] = fb - x[s:e]
    return y


COMBS = (1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617)  # Freeverb tunings at 44.1 kHz
ALLPASS = (556, 441, 341, 225)


def reverb(x, rt60, wet=0.25, predelay=0.012, damp=0.35, size=1.0, spread=23, width=1.0, tail=None):
    """Freeverb principle: parallel damped combs into serial allpasses, one bank per channel, feedback set from rt60."""
    if x.ndim == 1:
        x = stereo(x)
    tail = rt60 * 1.15 if tail is None else tail
    pad = int((tail + predelay) * SR)
    mono = np.concatenate([x.mean(axis=1), np.zeros(pad)])
    outs = []
    for ch in (0, 1):
        acc = np.zeros(len(mono))
        for d0 in COMBS:
            d = int((d0 + spread * ch) * SR / 44100 * size)
            acc += _comb(mono, d, 10 ** (-3 * d / (rt60 * SR)), damp)
        for d0 in ALLPASS:
            acc = _allpass(acc, int((d0 + spread * ch) * SR / 44100))
        outs.append(acc)
    l, r = outs
    m, s = (l + r) / 2, (l - r) / 2 * width
    w = np.stack([m + s, m - s], axis=1)
    w = w / (np.sqrt(np.mean(w ** 2)) + 1e-12) * (np.sqrt(np.mean(x ** 2)) + 1e-12)
    pre = int(predelay * SR)
    w = np.concatenate([np.zeros((pre, 2)), w])[:len(mono)]
    dry = np.concatenate([x, np.zeros((pad, 2))])
    return dry * (1 - wet) ** 0.5 + w * wet ** 0.5


def modes(table, dur, rng, attack_ms=0.2, detune=0.0):
    """Modal synthesis: table of (Hz, level, decay in s to −60 dB). detune: each mode as a slightly beating pair, like a real bell."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for f, a, t60 in table:
        f = f * (1 + rng.normal(0, 0.002))
        e = 10 ** (-3 * t / max(t60, 1e-3))
        ph = rng.uniform(0, 2 * np.pi)
        if detune:
            d = f * detune * rng.uniform(0.5, 1.5)
            y += a * e * (np.sin(2 * np.pi * (f - d) * t + ph) + 0.8 * np.sin(2 * np.pi * (f + d) * t + ph * 1.7)) / 1.8
        else:
            y += a * e * np.sin(2 * np.pi * f * t + ph)
    return y * (1 - np.exp(-t / (attack_ms / 1000)))


def burst(ms, rng, center, width=1.2):
    """Short noise excitation, shaped: the contact of a click or a strike."""
    n = max(32, int(ms * 6 / 1000 * SR))
    t = np.arange(n) / SR
    s = np.fft.rfft(rng.standard_normal(n))
    f = np.maximum(np.fft.rfftfreq(n, 1 / SR), 1.0)
    y = np.fft.irfft(s * np.exp(-0.5 * (np.log2(f / center) / width) ** 2), n)
    y = y / (np.abs(y).max() + 1e-12)
    return y * np.exp(-t / (ms / 1000)) * (1 - np.exp(-t / 0.0001))


def varispeed(x, rate):
    """Plays x at a changing rate (1 = normal, 0 = stopped), like a slowing tape; x: (n, 2)."""
    pos = np.cumsum(rate)
    pos = pos[pos < len(x) - 1]
    i = np.arange(len(x))
    return np.stack([np.interp(pos, i, x[:, c]) for c in (0, 1)], axis=1)


def finish(x, peak_db=-3.0, floor_db=-58.0, fade_ms=8.0):
    """No DC, tail cut where it is inaudible, zero at both ends, peak −3 dBFS."""
    x = x - x.mean(axis=0)
    env = np.abs(x).max(axis=1)
    top = env.max()
    last = np.nonzero(env > top * 10 ** (floor_db / 20))[0][-1] + 1
    first = np.nonzero(env > top * 10 ** (-80 / 20))[0][0]
    x = x[max(0, first - 8):last].copy()
    n = len(x)
    f = int(min(fade_ms / 1000 * SR, n * 0.1))
    r = np.linspace(0, 1, f)[:, None] ** 2
    x[-f:] *= r[::-1]
    h = min(48, n // 8)
    x[:h] *= np.linspace(0, 1, h)[:, None]
    return x / np.abs(x).max() * 10 ** (peak_db / 20)
