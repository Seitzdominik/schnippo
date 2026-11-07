"""ffprobe metadata, VFR detection, audio extraction, speech/silence detection.

Original media is only ever read. All derived files go to the cache.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import statistics
import subprocess
from fractions import Fraction
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp", ".dng", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mxf", ".mkv", ".avi", ".mts", ".m2ts", ".braw", ".r3d", ".webm"}


class MediaError(RuntimeError):
    pass


SYSTEM_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")  # Claude Desktop starts servers with a minimal PATH


def _bundled(name: str) -> str | None:
    """ffmpeg/ffprobe shipped as a Python dependency (see README, section ffmpeg license)."""
    try:
        from . import ffmpeg_dist
    except ImportError:  # pragma: no cover
        return None
    return ffmpeg_dist.path(name)


@functools.cache
def find_tool(name: str) -> tuple[str | None, str | None]:
    """(path, source): system ffmpeg first (PATH, Homebrew, /usr/local), else the bundled one.
    SCHNIPPO_FFMPEG=bundled skips the system lookup (tests of the bundle)."""
    if os.environ.get("SCHNIPPO_FFMPEG") == "bundled":
        b = _bundled(name)
        return (b, "mitgeliefert") if b else (None, None)
    p = shutil.which(name) or next((f"{d}/{name}" for d in SYSTEM_DIRS if Path(f"{d}/{name}").exists()), None)
    if p:
        return p, "System"
    b = _bundled(name)
    return (b, "mitgeliefert") if b else (None, None)


def _bin(name: str) -> str:
    p, _ = find_tool(name)
    if not p:
        raise MediaError(f"{name} nicht gefunden (Erweiterung neu installieren oder brew install ffmpeg)")
    return p


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if res.returncode != 0:
        raise MediaError(f"{Path(cmd[0]).name} failed: {res.stderr.strip()[-400:]}")
    return res


def find_videos(folder: Path, recursive: bool = False, notes: list | None = None) -> list[Path]:
    from .guard import media_files
    files, skipped = media_files(folder, recursive, VIDEO_EXTS)
    if notes is not None:
        notes += skipped
    return files


def find_images(folder: Path, recursive: bool = False, notes: list | None = None) -> list[Path]:
    from .guard import media_files
    files, skipped = media_files(folder, recursive, IMAGE_EXTS)
    if notes is not None:
        notes += skipped
    return files


def image_metadata(path: Path) -> dict:
    data = probe(path)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None or not v.get("width"):
        raise MediaError(f"no image stream in {path.name}")
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    return {"width": int(v["width"]), "height": int(v["height"]), "rotation": rot, "codec": v.get("codec_name")}


def probe(path: Path) -> dict:
    out = _run([_bin("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]).stdout
    return json.loads(out)


def _frac(s: str | None) -> Fraction | None:
    if not s or s in ("0/0", "N/A"):
        return None
    try:
        f = Fraction(s)
        return f if f > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def snap_fps(f: Fraction) -> Fraction:
    """Snap near-standard rates (e.g. 2997/100, 29.97003) to the exact NTSC fraction."""
    for std in (Fraction(24000, 1001), Fraction(30000, 1001), Fraction(60000, 1001), Fraction(120000, 1001)):
        if abs(float(f) - float(std)) < 0.002:
            return std
    if abs(float(f) - round(float(f))) < 0.002:
        return Fraction(round(float(f)))
    return f


def video_frame_times(path: Path, stream_index: int) -> list[float]:
    """Packet PTS of the video stream (no decoding -> fast even for long clips)."""
    out = _run([
        _bin("ffprobe"), "-v", "error", "-select_streams", str(stream_index),
        "-show_entries", "packet=pts_time", "-of", "default=nw=1:nk=1", str(path),
    ]).stdout
    ts = []
    for line in out.split():
        line = line.strip().rstrip(",")
        if line and line != "N/A":
            ts.append(float(line))
    ts.sort()  # packets come in decode order (B-frames)
    return ts


def detect_vfr(times: list[float], nominal: Fraction) -> tuple[bool, str]:
    if len(times) < 3:
        return False, "too few frames"
    deltas = [b - a for a, b in zip(times, times[1:]) if b > a]
    nominal_dt = 1 / float(nominal)
    off = [d for d in deltas if abs(d - nominal_dt) > 0.25 * nominal_dt]
    share = len(off) / len(deltas)
    span = times[-1] - times[0]
    eff = (len(times) - 1) / span if span > 0 else 0
    detail = (f"{len(times)} frames, eff {eff:.3f}fps vs nominal {float(nominal):.3f}, "
              f"dt min/median/max {min(deltas)*1000:.1f}/{statistics.median(deltas)*1000:.1f}/{max(deltas)*1000:.1f} ms, "
              f"{share:.1%} irregular")
    return share > 0.005, detail


def _tc(data: dict, vstream: dict | None) -> str | None:
    for s in [vstream or {}, *data.get("streams", [])]:
        tc = (s.get("tags") or {}).get("timecode")
        if tc:
            return tc
    return (data.get("format", {}).get("tags") or {}).get("timecode")


def clip_metadata(path: Path) -> dict:
    data = probe(path)
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if v is None:
        raise MediaError(f"no video stream in {path.name}")
    r = _frac(v.get("r_frame_rate"))
    avg = _frac(v.get("avg_frame_rate"))
    nominal = snap_fps(r or avg or Fraction(25))
    times = video_frame_times(path, v["index"])
    vfr, detail = detect_vfr(times, nominal)
    if avg and r and abs(float(avg) - float(r)) / float(r) > 0.01:
        vfr = True
        detail = f"r_frame_rate {float(r):.3f} != avg_frame_rate {float(avg):.3f}; " + detail
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    rot = int((v.get("tags") or {}).get("rotate", rot))
    dur = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    return {
        "duration_s": dur,
        "fps_num": nominal.numerator,
        "fps_den": nominal.denominator,
        "avg_fps": float(avg) if avg else None,
        "vfr": vfr,
        "vfr_detail": detail,
        "width": v.get("width"),
        "height": v.get("height"),
        "rotation": rot,
        "video_codec": v.get("codec_name"),
        "audio_channels": int(a.get("channels", 0)) if a else 0,
        "audio_sample_rate": int(a["sample_rate"]) if a and a.get("sample_rate") else None,
        "start_tc": _tc(data, v),
        "start_time_s": float(v.get("start_time") or 0.0),
        "nb_frames": len(times) or (int(v["nb_frames"]) if v.get("nb_frames") else None),
    }


def extract_audio(src: Path, dst: Path) -> Path:
    """16 kHz mono PCM WAV for transcription. Idempotent."""
    if dst.exists() and dst.stat().st_size > 44:
        return dst
    tmp = dst.with_suffix(".tmp.wav")
    _run([_bin("ffmpeg"), "-nostdin", "-y", "-v", "error", "-i", str(src), "-map", "0:a:0", "-vn",
          "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)])
    tmp.replace(dst)
    return dst


_SIL_START = re.compile(r"silence_start: (-?[\d.]+)")
_SIL_END = re.compile(r"silence_end: (-?[\d.]+)")


def detect_silence(wav: Path, noise_db: float = -35.0, min_s: float = 0.12) -> dict:
    """Silence intervals via ffmpeg silencedetect. Threshold is relative to the clip's own level:
    we first measure the speech level (mean volume) and keep noise_db as an absolute floor."""
    vol = _run([_bin("ffmpeg"), "-nostdin", "-v", "info", "-i", str(wav), "-af", "volumedetect", "-f", "null", "-"]).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", vol)
    mean_db = float(m.group(1)) if m else -30.0
    thr = max(noise_db, mean_db - 18.0)  # adaptive: ~18 dB below average loudness
    err = _run([_bin("ffmpeg"), "-nostdin", "-v", "info", "-i", str(wav),
                "-af", f"silencedetect=noise={thr:.1f}dB:d={min_s}", "-f", "null", "-"]).stderr
    starts = [float(x) for x in _SIL_START.findall(err)]
    ends = [float(x) for x in _SIL_END.findall(err)]
    dur_m = re.search(r"time=(\d+):(\d+):([\d.]+)", err.split("silencedetect")[-1]) or re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    total = int(dur_m.group(1)) * 3600 + int(dur_m.group(2)) * 60 + float(dur_m.group(3)) if dur_m else None
    if len(ends) < len(starts) and total is not None:
        ends.append(total)
    sil = [(max(0.0, s), e) for s, e in zip(starts, ends)]
    return {"threshold_db": thr, "mean_db": mean_db, "min_s": min_s, "duration_s": total, "silence": sil}


def speech_in_range(silence: list[tuple[float, float]], t0: float, t1: float) -> list[tuple[float, float]]:
    """Non-silent sub-intervals of [t0, t1] given silence intervals."""
    segs = []
    cur = t0
    for s, e in silence:
        if e <= cur:
            continue
        if s >= t1:
            break
        if s > cur:
            segs.append((cur, min(s, t1)))
        cur = max(cur, e)
        if cur >= t1:
            break
    if cur < t1:
        segs.append((cur, t1))
    return [(a, b) for a, b in segs if b - a > 1e-3]
