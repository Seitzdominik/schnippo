"""Deterministic audio measurement: loudness (EBU R128 via ffmpeg ebur128), true peak, noise floor and a speech
spectral profile compared to a neutral long-term speech spectrum. Recommendations only – Resolve applies them.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np

from .media import _bin

SR = 48000
# Long-term average speech spectrum, 1/3-octave levels in dB (approximation of Byrne et al. 1994, male/female average).
LTASS = {50: 32, 63: 38, 80: 43, 100: 47, 125: 53, 160: 57, 200: 58, 250: 59, 315: 59, 400: 58, 500: 57, 630: 55,
         800: 53, 1000: 51, 1250: 49, 1600: 48, 2000: 47, 2500: 45, 3150: 44, 4000: 43, 5000: 42, 6300: 41, 8000: 39,
         10000: 37}
BANDS = {"rumble": (50, 63), "boxy": (200, 250, 315, 400, 500), "sibilance": (5000, 6300, 8000)}
REF_NORM = (500, 630, 800, 1000, 1250, 1600, 2000)  # both spectra are aligned on this range


def ebur128(input_args: list[str], filter_complex: str | None = None) -> dict:
    """Integrated loudness (LUFS), loudness range (LU) and true peak (dBTP) of an ffmpeg input."""
    cmd = [_bin("ffmpeg"), "-nostdin", "-hide_banner", "-v", "info", *input_args]
    if filter_complex:
        cmd += ["-filter_complex", filter_complex + ",ebur128=peak=true[out]", "-map", "[out]"]
    else:
        cmd += ["-map", "0:a:0", "-af", "ebur128=peak=true"]
    err = subprocess.run(cmd + ["-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    summ = err[err.rfind("Summary:"):]
    get = lambda pat: float(m.group(1)) if (m := re.search(pat, summ, re.S)) else None
    return {"lufs": get(r"I:\s+(-?[\d.]+) LUFS"), "lra": get(r"LRA:\s+(-?[\d.]+) LU"), "true_peak": get(r"Peak:\s+(-?[\d.inf]+) dBFS")}


def program_filter(pieces: list[tuple[float, float]]) -> str:
    """ffmpeg filter that concatenates source time ranges of input 0 (the planned cut, without Resolve)."""
    parts = [f"[0:a:0]atrim=start={a:.5f}:end={b:.5f},asetpts=PTS-STARTPTS[p{k}]" for k, (a, b) in enumerate(pieces)]
    return ";".join(parts) + ";" + "".join(f"[p{k}]" for k in range(len(pieces))) + f"concat=n={len(pieces)}:v=0:a=1"


def read_pcm(path: Path) -> np.ndarray:
    raw = subprocess.run([_bin("ffmpeg"), "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float64) / 32768.0


def third_octave_levels(x: np.ndarray, active: list[tuple[float, float]]) -> dict[int, float]:
    """Mean power per 1/3-octave band over the active (speech) intervals, in dB."""
    nfft = 4096
    win = np.hanning(nfft)
    acc, n = np.zeros(nfft // 2 + 1), 0
    for a, b in active:
        seg = x[int(a * SR):int(b * SR)]
        for s in range(0, len(seg) - nfft, nfft // 2):
            acc += np.abs(np.fft.rfft(seg[s:s + nfft] * win)) ** 2
            n += 1
    if n == 0:
        return {}
    psd = acc / n
    freqs = np.fft.rfftfreq(nfft, 1 / SR)
    out = {}
    for fc in LTASS:
        lo, hi = fc / 2 ** (1 / 6), fc * 2 ** (1 / 6)
        sel = (freqs >= lo) & (freqs < hi)
        out[fc] = float(10 * np.log10(psd[sel].sum() + 1e-20)) if sel.any() else -200.0
    return out


def spectral_profile(levels: dict[int, float]) -> dict:
    """Band deviations (dB) of measured vs LTASS after aligning both on 500–2000 Hz."""
    if not levels:
        return {}
    off = np.mean([levels[f] for f in REF_NORM]) - np.mean([LTASS[f] for f in REF_NORM])
    dev = {f: levels[f] - off - LTASS[f] for f in LTASS}
    band = lambda fs: 10 * np.log10(np.mean([10 ** (dev[f] / 10) for f in fs]))
    return {"rumble_db": round(float(band(BANDS["rumble"])), 1), "boxy_db": round(float(band(BANDS["boxy"])), 1),
            "sibilance_db": round(float(band(BANDS["sibilance"])), 1), "per_band": {f: round(float(v), 1) for f, v in dev.items()}}


def recommendations(m: dict, target_lufs: float = -14.0, tp_max: float = -1.0) -> list[str]:
    rec = []
    if m.get("lufs") is not None:
        rec.append(f"Normalisieren: {m['lufs']:.1f} → {target_lufs:.1f} LUFS ({target_lufs - m['lufs']:+.1f} dB)")
        if m.get("true_peak") is not None and m["true_peak"] + (target_lufs - m["lufs"]) > tp_max:
            rec.append(f"Limiter nötig: True Peak nach Verstärkung ≈ {m['true_peak'] + target_lufs - m['lufs']:+.1f} dBTP > {tp_max} dBTP "
                       "(Server: Limiter → Multiband Compressor, True Peak ≈ −2,8 dBTP)")
    sp = m.get("spectrum") or {}
    if sp:
        if sp["rumble_db"] > 3:  # 04_polish: every EQ measure needs a reason from the measurement
            rec.append(f"Hochpass ~80 Hz: Rumpeln {sp['rumble_db']:+.1f} dB über Referenz")
        else:
            rec.append(f"Kein Hochpass nötig: Rumpeln unauffällig ({sp['rumble_db']:+.1f} dB)")
        if sp["boxy_db"] > 3:
            rec.append(f"Leichte Absenkung 200–500 Hz (−2 bis −3 dB): dumpf/boxy {sp['boxy_db']:+.1f} dB über Referenz")
        if sp["sibilance_db"] > 4:
            rec.append(f"De-Esser: Zischlaute 5–8 kHz {sp['sibilance_db']:+.1f} dB über Referenz")
    return rec


def identical_audio_streams(path: str, seconds: float = 30.0) -> bool | None:
    """True if the file has ≥ 2 audio streams and stream 2 equals stream 1 (difference < −80 dB over the first seconds).
    Phones/apps often record the same mic twice; Resolve then puts both on A1/A2 and the programme is doubled."""
    import json as _json

    info = _json.loads(subprocess.run([_bin("ffprobe"), "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                                       "-of", "json", path], capture_output=True, text=True).stdout or "{}")
    if len(info.get("streams", [])) < 2:
        return None
    err = subprocess.run([_bin("ffmpeg"), "-nostdin", "-v", "info", "-t", str(seconds), "-i", path, "-filter_complex",
                          "[0:a:0][0:a:1]amerge=inputs=2,pan=mono|c0=c0-c1,volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = re.search(r"max_volume: (-?[\d.inf]+) dB", err)
    return bool(m) and (m.group(1) == "-inf" or float(m.group(1)) < -80.0)


# ---------- phase 6: source channels ----------
CH_SR = 16000
SAFETY_SNR_DB = 1.5  # SNR closer than this on two correlated channels → same mic, different gain
CLIP_SAMPLES = 10  # more full-scale samples than this in the analysed span → channel counts as clipped


def source_channels(path: str) -> list[tuple[int, int]]:
    """(audio stream ordinal, channel in stream) in Resolve's numbering order: channel k+1 = k-th entry
    (embedded_audio_channels counts across streams, measured on 21.1.2 with 2 mono AAC streams)."""
    import json as _json

    info = _json.loads(subprocess.run([_bin("ffprobe"), "-v", "error", "-select_streams", "a", "-show_entries",
                                       "stream=index,channels", "-of", "json", path], capture_output=True, text=True).stdout or "{}")
    return [(s, c) for s, st in enumerate(info.get("streams", [])) for c in range(int(st.get("channels") or 1))]


def _channel_pcm(path: str, stream: int, ch: int, seconds: float) -> np.ndarray:
    raw = subprocess.run([_bin("ffmpeg"), "-nostdin", "-v", "error", "-t", str(seconds), "-i", path, "-map", f"0:a:{stream}",
                          "-af", f"pan=mono|c0=c{ch}", "-ar", str(CH_SR), "-f", "s16le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float64) / 32768.0


def _max_corr(a: np.ndarray, b: np.ndarray, max_lag: int) -> float:
    """Highest Pearson correlation over lags ±max_lag samples (spaced stereo mics are up to ~1–2 ms apart)."""
    m = min(len(a), len(b), 60 * CH_SR)
    a, b = a[:m] - a[:m].mean(), b[:m] - b[:m].mean()
    if m < 2 * max_lag + 2 or a.std() == 0 or b.std() == 0:
        return 0.0
    best = 0.0
    for lag in range(-max_lag, max_lag + 1):
        x, y = (a[lag:], b[:m - lag]) if lag >= 0 else (a[:m + lag], b[-lag:])
        c = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-12))
        best = max(best, c)
    return best


def channel_analysis(path: str, seconds: float = 180.0, unbalanced_db: float = 3.0) -> dict:
    """Per source channel: level (RMS, LUFS), speech level (p90 of 50-ms RMS), noise floor (p10), speech/noise ratio;
    correlation between channels (best over ±2 ms lag); class identisch | unausgewogen | verschieden | stereo | mono; best channel.

    Classes: corr ≥ 0.999 and < 0.1 dB apart → identisch; level or noise floor > unbalanced_db apart (corr ≥ 0.5)
    → unausgewogen; corr < 0.5 → verschieden (two mics, e.g. lavalier + camera); otherwise → stereo (kept).
    Best = highest speech/noise ratio, ties → higher speech level."""
    chans = source_channels(path)
    if not chans:
        return {"channels": [], "class": "none", "best": None, "reason": "keine Tonspur"}
    win = CH_SR // 20
    stats, pcms = [], []
    for k, (s, c) in enumerate(chans, 1):
        x = _channel_pcm(path, s, c, seconds)
        pcms.append(x)
        n = len(x) // win
        rms = np.sqrt(np.mean(x[:n * win].reshape(n, win) ** 2, axis=1) + 1e-12) if n else np.array([1e-6])
        db = 20 * np.log10(rms)
        speech, floor = float(np.percentile(db, 90)), float(np.percentile(db, 10))
        loud = ebur128(["-t", str(seconds), "-i", path], f"[0:a:{s}]pan=mono|c0=c{c}")
        stats.append({"channel": k, "stream": s, "in_stream": c, "rms_db": round(float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)), 1),
                      "lufs": loud.get("lufs"), "speech_db": round(speech, 1), "noise_db": round(floor, 1),
                      "snr_db": round(speech - floor, 1),
                      "clipped": int(np.sum(np.abs(x) >= 0.97)) if len(x) else 0})  # 16-kHz resample rounds the plateaus
    out = {"channels": stats, "correlation": None}
    if len(stats) == 1:
        out.update({"class": "mono", "best": 1, "reason": "nur ein Kanal"})
        return out
    corr = _max_corr(pcms[0], pcms[1], max_lag=int(0.002 * CH_SR))
    out["correlation"] = round(corr, 4)
    s1, s2 = stats[0], stats[1]
    level_gap, noise_gap = abs(s1["speech_db"] - s2["speech_db"]), abs(s1["noise_db"] - s2["noise_db"])
    best = max(stats[:2], key=lambda s: (s["snr_db"], s["speech_db"]))
    safety = None
    loud_ch = s1 if s1["speech_db"] >= s2["speech_db"] else s2
    if corr >= 0.5 and level_gap > unbalanced_db and (abs(s1["snr_db"] - s2["snr_db"]) < SAFETY_SNR_DB
                                                      or loud_ch.get("clipped", 0) > CLIP_SAMPLES):
        # same mic, one channel recorded quieter (safety track, typically −6 dB): the SNR is equal, so take the louder
        # main channel – unless it clips (that is what the safety track is for). Phase 8: the choice flipped per clip.
        main, quiet = (s1, s2) if s1["speech_db"] >= s2["speech_db"] else (s2, s1)
        best = quiet if main.get("clipped", 0) > CLIP_SAMPLES else main
        safety = (f"Sicherheitsspur: Kanal {quiet['channel']} ist {level_gap:.1f} dB leiser bei gleichem Rauschabstand → "
                  + (f"Kanal {main['channel']} übersteuert ({main['clipped']} Samples), deshalb die leise Spur"
                     if best is quiet else f"lauter Hauptkanal {main['channel']}"))
    if corr >= 0.999 and level_gap < 0.1 and noise_gap < 0.1:
        cls, reason = "identisch", f"Kanäle identisch (Korrelation {corr:.4f}) → Kanal {best['channel']} mittig, Kopie weg"
    elif corr >= 0.5 and (level_gap > unbalanced_db or noise_gap > unbalanced_db):
        cls = "unausgewogen"
        reason = safety or (f"Kanal {best['channel']}: Sprache {best['speech_db']} dB, Rauschen {best['noise_db']} dB "
                  f"(Abstand {best['snr_db']} dB) – Pegelunterschied {level_gap:.1f} dB, Rauschunterschied {noise_gap:.1f} dB")
    elif corr < 0.5:
        cls = "verschieden"
        other = s2 if best is s1 else s1
        reason = (f"zwei verschiedene Mikrofone (Korrelation {corr:.2f}); Kanal {best['channel']} hat das bessere "
                  f"Sprach/Rausch-Verhältnis ({best['snr_db']} dB gegenüber {other['snr_db']} dB)")
    else:
        cls, best, reason = "stereo", None, f"echtes Stereo (Korrelation {corr:.2f}, Pegel ausgeglichen) → bleibt Stereo"
    out.update({"class": cls, "best": best["channel"] if best else None, "reason": reason})
    return out


def speaker_channels(path: str, spans: dict, min_gap_db: float = 6.0, max_s: float = 90.0) -> dict:
    """Interview with one mic per person: which source channel carries which speaker. spans = {speaker: [(t0, t1), …]}
    (word times from the diarized transcript). Per speaker the speech level (RMS over its words, up to max_s) per channel;
    a speaker gets its own channel if that channel is ≥ min_gap_db louder for it. Returns {"by_speaker": {spk: channel},
    "levels": {spk: [dB per channel]}, "split": bool}."""
    chans = source_channels(path)
    if len(chans) < 2 or len(spans) < 2:
        return {"by_speaker": {}, "levels": {}, "split": False}
    pcm = [_channel_pcm(path, s, c, 1e6) for s, c in chans[:2]]
    levels, best = {}, {}
    for spk, sp in spans.items():
        acc, used = [[], []], 0.0
        for t0, t1 in sp:
            if used >= max_s:
                break
            a, b = int(t0 * CH_SR), int(t1 * CH_SR)
            for k in (0, 1):
                acc[k].append(pcm[k][a:b])
            used += t1 - t0
        if used < 1.0:
            continue
        db = [round(float(20 * np.log10(np.sqrt(np.mean(np.concatenate(x) ** 2)) + 1e-12)), 1) for x in acc]
        levels[spk] = db
        if abs(db[0] - db[1]) >= min_gap_db:
            best[spk] = 1 if db[0] > db[1] else 2
    split = len(set(best.values())) >= 2
    return {"by_speaker": best if split else {}, "levels": levels, "split": split}


def louder_channels(path: str, spans: list[tuple[float, float]], min_gap_db: float = 6.0) -> list[int | None]:
    """Per time span the clearly louder of the first two source channels (1 or 2), None if they are within min_gap_db.
    The signal decides, not the diarization: it took two interviewer questions for the guest (Phase 8)."""
    chans = source_channels(path)
    if len(chans) < 2:
        return [None] * len(spans)
    pcm = [_channel_pcm(path, s, c, 1e6) for s, c in chans[:2]]
    out: list[int | None] = []
    for t0, t1 in spans:
        db = []
        for x in pcm:
            seg = x[int(t0 * CH_SR):int(t1 * CH_SR)]
            db.append(float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12)) if len(seg) else -120.0)
        out.append(None if abs(db[0] - db[1]) < min_gap_db else (1 if db[0] > db[1] else 2))
    return out


def channel_balance(path: Path) -> dict:
    """RMS per output channel of a render (dB) → verification that both speakers play equally loud."""
    err = subprocess.run([_bin("ffmpeg"), "-nostdin", "-nostats", "-v", "info", "-i", str(path), "-map", "0:a:0", "-af",
                          "astats=measure_perchannel=RMS_level:measure_overall=none", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    vals = [float(v) for v in re.findall(r"RMS level dB: (-?[\d.inf]+)", err) if v not in ("-inf", "inf")]
    return {"rms_db": [round(v, 2) for v in vals], "diff_db": round(abs(vals[0] - vals[1]), 2) if len(vals) >= 2 else None}
