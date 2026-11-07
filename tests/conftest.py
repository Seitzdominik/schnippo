import os

os.environ.setdefault("SCHNIPPO_NO_MIGRATE", "1")  # tests never touch the real home
import subprocess
from pathlib import Path

import pytest

import numpy as np

from schnippo.acoustic import Acoustic, AcousticParams
from schnippo.config import Config
from schnippo.models import RawTranscript, Word


def make_raw(spec: list[tuple[str, float, float]]) -> RawTranscript:
    return RawTranscript(provider="fake", language="de", tokens=[
        Word(id=f"w{i:04d}", text=t, start_s=s, end_s=e, confidence=0.9) for i, (t, s, e) in enumerate(spec, 1)])


@pytest.fixture
def cfg(tmp_path) -> Config:
    return Config(gladia_api_key="test-key-123", cache_dir=tmp_path / "cache")


def ffmpeg_clip(out: Path, rate: str = "25", dur: float = 2.0, vfr: bool = False, tone: bool = True) -> Path:
    v = f"testsrc2=s=320x180:r={rate}:d={dur}"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", v]
    cmd += ["-f", "lavfi", "-i", f"sine=f=440:d={dur}:sample_rate=48000"] if tone else []
    if vfr:
        cmd += ["-vf", "setpts='if(lt(N,20),N/25,0.8+(N-20)/10)/TB'", "-fps_mode", "passthrough"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)]
    subprocess.run(cmd, check=True)
    return out


def make_acoustic(duration: float, voiced: list[tuple[float, float]] = (), breath: list[tuple[float, float]] = (),
                  level: float = -30.0) -> Acoustic:
    """Synthetic envelope: -80 dB floor; voiced regions periodic (0.9), breath regions noisy (0.1)."""
    n = int(round(duration * 100)) + 1
    env = np.full(n, -80.0)
    voi = np.full(n, 0.05)
    for regs, v in ((voiced, 0.9), (breath, 0.1)):
        for a, b in regs:
            env[int(round(a * 100)):int(round(b * 100))] = level
            voi[int(round(a * 100)):int(round(b * 100))] = v
    p = AcousticParams()
    return Acoustic(env, voi, -80.0, -55.0, duration, p)
