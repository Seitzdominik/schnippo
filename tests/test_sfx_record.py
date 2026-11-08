import json
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

from schnippo import sfx, sfx_record
from schnippo.media import _bin


def _own_whoosh(folder: Path) -> None:
    (folder / "whoosh").mkdir(parents=True)
    subprocess.run([_bin("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=500:d=0.3", str(folder / "whoosh" / "mein_luftzug.wav")], check=True)


def test_library_is_the_default():
    lib = sfx.load(None)
    assert not [e for e in lib if e["id"].startswith("user:")]
    assert sfx._pick(lib, NS(file=None), "whoosh", 2, False, {}) is not None


def test_own_sounds_win_their_category_and_the_library_fills_the_rest(tmp_path):
    _own_whoosh(tmp_path / "Eigene")
    lib = sfx.load(tmp_path / "Eigene", tmp_path / "c")
    cue = NS(file=None)
    for uses in ({}, {"user:mein_luftzug": 5}):  # variety never brings the library back in
        assert sfx._pick(lib, cue, "whoosh", 2, False, uses)["id"] == "user:mein_luftzug"
    assert sfx._pick(lib, cue, "whoosh", 1, True, {})["id"] == "user:mein_luftzug"
    assert not sfx._pick(lib, cue, "pop", 2, False, {})["id"].startswith("user:")
    assert sfx._pick(lib, NS(file="mein_luftzug"), None, 2, False, {})["id"] == "user:mein_luftzug"


def test_cc_by_credit_reaches_the_library(tmp_path):
    (tmp_path / "whoosh").mkdir()
    subprocess.run([_bin("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=500:d=0.3", str(tmp_path / "whoosh" / "a.wav")], check=True)
    (tmp_path / "whoosh" / "a.wav.json").write_text(json.dumps({"license": "Attribution", "credit": "von ana"}))
    e = [x for x in sfx.load(tmp_path, tmp_path / "c") if x["id"] == "user:a"][0]
    assert e["license"] == "Attribution" and e["credit"] == "von ana"


def _recording(path: Path, gaps=(0.6, 1.4, 2.2)):
    """Noise floor with mouse-like clicks: press and, 90 ms later, release."""
    rng = np.random.default_rng(3)
    x = rng.standard_normal((3 * 48000, 2)) * 0.002
    for t in gaps:
        for off, lvl in ((0.0, 0.6), (0.09, 0.3)):
            s = int((t + off) * 48000)
            k = np.exp(-np.arange(600) / 90)
            x[s:s + 600] += (rng.standard_normal(600) * k * lvl)[:, None]
    sfx.write_wav(path, x)


def test_recordings_split_into_clicks_and_stay_untouched(tmp_path):
    src = tmp_path / "maus.wav"
    _recording(src)
    before = src.read_bytes()
    lines = sfx_record.prepare([src], tmp_path / "Aufnahmen", "click")
    out = sorted((tmp_path / "Aufnahmen" / "click").glob("*.wav"))
    assert len(out) == 3 and "3 Einzelanschläge" in lines[0] and src.read_bytes() == before
    x = sfx.decode(out[0])
    assert abs(20 * np.log10(np.abs(x).max()) + 3) < 0.3 and 0.09 < len(x) / 48000 < 0.35  # press and release stay together


def test_denoise_lowers_the_floor_but_not_the_hits():
    rng = np.random.default_rng(1)
    x = rng.standard_normal((48000, 2)) * 0.01
    x[20000:20400] += 0.5
    y = sfx_record.denoise(x)
    quiet = lambda v: np.sqrt(np.mean(v[:15000] ** 2))
    assert 20 * np.log10(quiet(x) / quiet(y)) > 4 and np.abs(y[20000:20400]).max() > 0.4


def test_whole_categories_stay_one_piece(tmp_path):
    src = tmp_path / "tastatur.wav"
    _recording(src)
    lines = sfx_record.prepare([src], tmp_path / "A")
    assert list((tmp_path / "A" / "typing").glob("*.wav")) and "ein Stück" in lines[0]
