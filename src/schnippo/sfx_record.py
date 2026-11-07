"""Own recordings → library: light noise reduction, split into single hits, level, then the normal scan measures transient and category.
Only for the user's own recordings; the originals stay untouched, the results go to <sfx_folder>/Aufnahmen/<category>/."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .sfx import AUDIO_EXTS, SR, decode, guess_category, write_wav

WHOLE = {"typing": 30.0, "clock": 30.0, "atmo": 60.0, "applause": 20.0}  # these stay one piece, at most so many seconds
GROUP_MS = {"click": 200, "tick": 80}  # press and release are one click
PEAK_DB = -3.0


def denoise(x: np.ndarray, max_cut_db: float = 9.0) -> np.ndarray:
    """Spectral gate against the quietest tenth of the recording; at most 9 dB, so nothing starts to gurgle."""
    size, hop = 1024, 256
    win = np.hanning(size)
    out = np.zeros_like(x)
    floor = 10 ** (-max_cut_db / 20)
    for c in range(x.shape[1]):
        s = np.pad(x[:, c], (size, size))
        idx = np.arange(0, len(s) - size, hop)[:, None] + np.arange(size)
        X = np.fft.rfft(s[idx] * win, axis=1)
        mag = np.abs(X)
        e = mag.sum(axis=1)
        noise = np.median(mag[e <= np.percentile(e[e > 0], 10)], axis=0) if (e > 0).any() else np.zeros(mag.shape[1])
        gain = np.clip(1 - 1.5 * noise[None, :] / np.maximum(mag, 1e-12), floor, 1.0)
        gain = (gain + np.roll(gain, 1, axis=0) + np.roll(gain, -1, axis=0)) / 3
        y = np.fft.irfft(X * gain, size, axis=1) * win
        acc, norm = np.zeros(len(s)), np.zeros(len(s))
        np.add.at(acc, idx, y)
        np.add.at(norm, idx, np.broadcast_to(win ** 2, y.shape))
        out[:, c] = (acc / np.maximum(norm, 1e-6))[size:size + len(x)]
    return out


def split_hits(x: np.ndarray, group_ms: int = 150, min_ms: int = 12, max_hits: int = 12) -> list[np.ndarray]:
    """Single sounds, with a little air before and the decay after. Sounds closer than group_ms stay together."""
    hop = SR // 200
    n = len(x) // hop
    if n == 0:
        return []
    env = 20 * np.log10(np.sqrt(np.mean(np.mean(x[:n * hop] ** 2, axis=1).reshape(n, hop), axis=1)) + 1e-9)
    floor = np.percentile(env, 20)
    gate = max(floor + 12, env.max() - 40)
    on = np.nonzero(env > gate)[0]
    if len(on) == 0:
        return []
    groups, a, b = [], on[0], on[0]
    for i in on[1:]:
        if (i - b) * 5 > group_ms:
            groups.append((a, b))
            a = i
        b = i
    groups.append((a, b))
    out = []
    for a, b in groups:
        if (b - a + 1) * 5 < min_ms:
            continue
        s, e = max(0, a * hop - SR // 200), min(len(x), (b + 1) * hop + SR // 12)
        y = x[s:e].copy()
        f = min(len(y) // 4, SR // 100)
        y[-f:] *= np.linspace(1, 0, f)[:, None]
        y[:SR // 1000] *= np.linspace(0, 1, min(SR // 1000, len(y)))[:, None]
        out.append(y)
    out.sort(key=lambda y: -np.abs(y).max())
    return out[:max_hits]


def peak(x: np.ndarray) -> np.ndarray:
    return x / max(np.abs(x).max(), 1e-9) * 10 ** (PEAK_DB / 20)


def prepare(files: list[Path], target: Path, category: str | None = None) -> list[str]:
    """Writes prepared copies below target; returns one line per recording."""
    lines = []
    for f in files:
        cat = category or guess_category(Path(f.name)) or guess_category(f) or "ohne_kategorie"
        x = denoise(decode(f))
        folder = target / cat
        folder.mkdir(parents=True, exist_ok=True)
        if cat in WHOLE:
            y = x[:int(WHOLE[cat] * SR)]
            act = np.nonzero(np.abs(y).max(axis=1) > np.abs(y).max() * 0.02)[0]
            y = y[max(0, act[0] - SR // 50):act[-1] + SR // 10] if len(act) else y
            n = min(len(y) // 4, SR // 50)
            y[:n] *= np.linspace(0, 1, n)[:, None]
            y[-n:] *= np.linspace(1, 0, n)[:, None]
            write_wav(folder / f"{f.stem}.wav", peak(y))
            lines.append(f"{f.name} → {cat}: ein Stück, {len(y) / SR:.1f} s")
            continue
        hits = split_hits(x, GROUP_MS.get(cat, 150))
        for k, y in enumerate(hits, 1):
            write_wav(folder / f"{f.stem}_{k:02d}.wav", peak(y))
        lines.append(f"{f.name} → {cat}: {len(hits)} Einzelanschläge" if hits else f"{f.name}: nichts Verwertbares gefunden")
    return lines


def recordings(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS and not p.name.startswith("."))
