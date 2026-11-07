"""Acoustic analysis of the 16 kHz mono WAV (numpy, no Torch).

* RMS envelope (25 ms window, 10 ms hop) in dBFS.
* Noise floor = low percentile of the envelope; activity threshold = floor + delta.
  This replaces the Phase-1 rule max(-35 dB, mean-18 dB), which on a quiet recording with a very low
  room noise put the threshold *above* half of the speech frames.
* Voicing per frame = peak of the normalised autocorrelation in the 75–400 Hz lag range (40 ms window).
  Voiced sounds ("äh", "hm", vowels) have a clear periodicity, breaths/clicks do not.

Regions of activity are classified as ``voiced`` (filler candidate), ``breath`` (unvoiced, breath-like
duration) or ``click`` (very short transient).
"""

from __future__ import annotations

import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SR = 16000
HOP = 160  # 10 ms
WIN = 400  # 25 ms
VWIN = 640  # 40 ms voicing window
LAG_MIN, LAG_MAX = SR // 400, SR // 75  # 40 .. 213 samples


@dataclass
class AcousticParams:
    floor_percentile: float = 10.0
    delta_db: float = 25.0  # activity threshold above the noise floor
    min_threshold_db: float = -60.0  # never below this (digital silence / heavy denoise)
    max_threshold_db: float = -30.0
    min_region_s: float = 0.06
    merge_gap_s: float = 0.08
    voiced_corr: float = 0.6  # frame is voiced if autocorrelation peak >= this
    voiced_min_s: float = 0.15  # region needs at least this much voiced material (calibrated on real take)
    voiced_ratio: float = 0.6  # ... and this share of its active frames voiced
    click_max_s: float = 0.08

    def key(self) -> list:
        return [self.floor_percentile, self.delta_db, self.min_threshold_db, self.max_threshold_db, self.min_region_s,
                self.merge_gap_s, self.voiced_corr, self.voiced_min_s, self.voiced_ratio, self.click_max_s, 2]


@dataclass
class Acoustic:
    env_db: np.ndarray  # per 10 ms frame
    voicing: np.ndarray  # per 10 ms frame, 0..1
    floor_db: float
    threshold_db: float
    duration_s: float
    params: AcousticParams = field(default_factory=AcousticParams)

    # ---- frame helpers ----
    def _sl(self, t0: float, t1: float) -> slice:
        return slice(max(0, int(round(t0 * 100))), max(0, int(round(t1 * 100))))

    def active(self, t0: float, t1: float) -> np.ndarray:
        return self.env_db[self._sl(t0, t1)] > self.threshold_db

    def regions(self, t0: float, t1: float) -> list[tuple[float, float]]:
        """Active (non-silent) sub-intervals of [t0, t1]."""
        act = self.active(t0, t1)
        base = int(round(t0 * 100))
        out: list[list[float]] = []
        i = 0
        while i < len(act):
            if act[i]:
                j = i
                while j < len(act) and act[j]:
                    j += 1
                a, b = (base + i) / 100, (base + j) / 100
                if out and a - out[-1][1] <= self.params.merge_gap_s:
                    out[-1][1] = b
                else:
                    out.append([a, b])
                i = j
            else:
                i += 1
        return [(max(a, t0), min(b, t1)) for a, b in out if b - a >= self.params.min_region_s]

    def classify(self, t0: float, t1: float) -> dict:
        sl = self._sl(t0, t1)
        env, voi = self.env_db[sl], self.voicing[sl]
        act = env > self.threshold_db
        voiced = (voi >= self.params.voiced_corr) & act
        vs = float(voiced.sum()) / 100
        ratio = float(voiced.sum()) / max(1, int(act.sum()))
        dur = t1 - t0
        if vs >= self.params.voiced_min_s and ratio >= self.params.voiced_ratio:
            cls = "voiced"
        elif dur <= self.params.click_max_s:
            cls = "click"
        else:
            cls = "breath"
        return {"class": cls, "peak_db": round(float(env.max()) if len(env) else -120.0, 1),
                "voiced_s": round(vs, 2), "voiced_ratio": round(ratio, 2)}

    def silent_runs(self, t0: float, t1: float, min_s: float) -> list[tuple[float, float]]:
        act = self.active(t0, t1)
        base = int(round(t0 * 100))
        out, i = [], 0
        while i < len(act):
            if not act[i]:
                j = i
                while j < len(act) and not act[j]:
                    j += 1
                if (j - i) / 100 >= min_s:
                    out.append(((base + i) / 100, (base + j) / 100))
                i = j
            else:
                i += 1
        return out

    # ---- persistence ----
    def save(self, path: Path) -> None:
        np.savez_compressed(path, env=self.env_db.astype(np.float32), voi=self.voicing.astype(np.float16),
                            meta=np.array([self.floor_db, self.threshold_db, self.duration_s]),
                            key=np.array(self.params.key(), dtype=float))

    @classmethod
    def load(cls, path: Path, params: AcousticParams) -> "Acoustic | None":
        if not path.exists():
            return None
        d = np.load(path)
        if list(d["key"]) != [float(x) for x in params.key()]:
            return None
        floor, thr, dur = (float(x) for x in d["meta"])
        return cls(d["env"].astype(np.float64), d["voi"].astype(np.float64), floor, thr, dur, params)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("expected 16 kHz mono 16-bit WAV")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768.0


def _frames(xp: np.ndarray, win: int, i0: int, i1: int) -> np.ndarray:
    """Frames i0..i1 (hop 10 ms) of the padded signal xp (padded by win//2 in front)."""
    idx = np.arange(win)[None, :] + (np.arange(i0, i1) * HOP)[:, None]
    return xp[idx]


def analyze_wav(path: Path, params: AcousticParams | None = None) -> Acoustic:
    params = params or AcousticParams()
    x = read_wav(path)
    n = 1 + max(0, (len(x) - 1) // HOP)
    xp_e = np.pad(x, (WIN // 2, WIN))
    xp_v = np.pad(x, (VWIN // 2, VWIN))
    env = np.empty(n)
    voi = np.empty(n)
    nfft, hann = 1024, np.hanning(VWIN)[None, :]
    for i0 in range(0, n, 4096):  # chunked: bounded memory for hour-long material
        i1 = min(n, i0 + 4096)
        fe = _frames(xp_e, WIN, i0, i1)
        env[i0:i1] = 10 * np.log10(np.mean(fe * fe, axis=1) + 1e-12)
        fv = _frames(xp_v, VWIN, i0, i1)
        fv = (fv - fv.mean(axis=1, keepdims=True)) * hann
        ac = np.fft.irfft(np.abs(np.fft.rfft(fv, nfft)) ** 2, nfft)[:, :LAG_MAX + 1]
        voi[i0:i1] = np.clip(ac[:, LAG_MIN:LAG_MAX + 1].max(axis=1) / (ac[:, 0] + 1e-12), 0, 1)
    floor = float(np.percentile(env, params.floor_percentile))
    thr = float(np.clip(floor + params.delta_db, params.min_threshold_db, params.max_threshold_db))
    return Acoustic(env, voi, floor, thr, len(x) / SR, params)
