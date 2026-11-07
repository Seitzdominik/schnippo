import json
import subprocess
from pathlib import Path

import httpx
import numpy as np
import pytest

from schnippo import sfx, sfx_record, sfx_sources
from schnippo.media import _bin


def _mp3(tmp_path) -> bytes:
    f = tmp_path / "x.mp3"
    subprocess.run([_bin("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=0.6:c=pink:a=0.5", "-af", "afade=in:d=0.2,afade=out:st=0.3:d=0.3", "-ac", "2", str(f)], check=True)
    return f.read_bytes()


def _freesound(tmp_path, seen):
    audio = _mp3(tmp_path)
    sound = {"id": 7, "name": "Air Whoosh", "username": "ana", "license": "Creative Commons 0", "duration": 0.6, "url": "https://freesound.org/s/7/",
             "previews": {"preview-hq-mp3": "https://cdn.freesound.org/7.mp3"}}
    bad = {**sound, "id": 8, "license": "Attribution NonCommercial"}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path.endswith("/search/"):
            return httpx.Response(200, json={"results": [sound, bad, {**sound, "id": 9, "duration": 40}]})
        if req.url.path.endswith("/sounds/7/"):
            return httpx.Response(200, json=sound)
        if req.url.path.endswith("/sounds/8/"):
            return httpx.Response(200, json=bad)
        return httpx.Response(200, content=audio)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_freesound_search_filters_and_ranks(tmp_path):
    seen = []
    rows = sfx_sources.freesound_search("KEY", "whoosh", client=_freesound(tmp_path, seen))
    assert [r["id"] for r in rows] == [7] and rows[0]["distance"] is not None  # NonCommercial and too long are out
    assert 'license:("Creative Commons 0")' in seen[0].url.params["filter"]
    assert seen[0].headers["authorization"] == "Token KEY" and "KEY" not in str(seen[0].url)


def test_freesound_fetch_keeps_licence_and_refuses_noncommercial(tmp_path):
    f = sfx_sources.freesound_fetch("KEY", 7, "whoosh", tmp_path, client=_freesound(tmp_path, []))
    meta = json.loads(f.with_name(f.name + ".json").read_text())
    assert f.parent == tmp_path / "freesound" / "whoosh" and meta["author"] == "ana" and meta["credit"] == ""
    with pytest.raises(ValueError):
        sfx_sources.freesound_fetch("KEY", 8, "whoosh", tmp_path, client=_freesound(tmp_path, []))


def test_cc_by_credit_reaches_the_library(tmp_path):
    (tmp_path / "whoosh").mkdir()
    subprocess.run([_bin("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=500:d=0.3", str(tmp_path / "whoosh" / "a.wav")], check=True)
    (tmp_path / "whoosh" / "a.wav.json").write_text(json.dumps({"license": "Attribution", "credit": "von ana"}))
    e = [x for x in sfx.load(tmp_path, tmp_path / "c") if x["id"] == "user:a"][0]
    assert e["license"] == "Attribution" and e["credit"] == "von ana"


def test_elevenlabs_request(tmp_path):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, content=b"mp3")
    f = sfx_sources.elevenlabs_generate("KEY", "soft air swoosh", "whoosh", tmp_path, 0.5, client=httpx.Client(transport=httpx.MockTransport(handler)))
    body = json.loads(seen[0].content)
    assert body == {"text": "soft air swoosh", "loop": False, "duration_seconds": 0.5} and seen[0].headers["xi-api-key"] == "KEY"
    assert f.parent == tmp_path / "elevenlabs" / "whoosh"
    with pytest.raises(ValueError):
        sfx_sources.elevenlabs_generate("KEY", "x", "whoosh", tmp_path, 40)


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
