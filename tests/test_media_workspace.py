import wave

from schnippo import media
from schnippo import workspace as wsmod
from schnippo.cache import fingerprint
from schnippo.workspace import Workspace

from conftest import ffmpeg_clip, make_raw


def test_probe_cfr_vfr_and_audio(tmp_path):
    cfr = ffmpeg_clip(tmp_path / "cfr.mp4", rate="30000/1001")
    vfr = ffmpeg_clip(tmp_path / "vfr.mp4", rate="25", dur=3, vfr=True)
    m = media.clip_metadata(cfr)
    assert (m["fps_num"], m["fps_den"], m["vfr"]) == (30000, 1001, False)
    assert media.clip_metadata(vfr)["vfr"] is True
    wav = media.extract_audio(cfr, tmp_path / "a.wav")
    with wave.open(str(wav)) as w:
        assert (w.getframerate(), w.getnchannels()) == (16000, 1)
    assert media.snap_fps(__import__("fractions").Fraction(2997, 100)).denominator == 1001


def test_speech_in_range():
    sil = [(0.0, 1.0), (2.0, 3.0)]
    assert media.speech_in_range(sil, 0.5, 2.5) == [(1.0, 2.0)]
    assert media.speech_in_range(sil, 0.2, 0.8) == []


class FakeProvider:
    name = "gladia"
    calls = 0

    def __init__(self, cfg):
        pass

    def option_fingerprint(self):
        return "fake"

    def transcribe(self, wav, language, raw_out=None):
        FakeProvider.calls += 1
        return make_raw([("Hallo", 0.1, 0.5), ("Welt", 0.6, 1.0)])


def test_ingest_ids_stable_and_transcript_cached(cfg, tmp_path, monkeypatch):
    folder = tmp_path / "takes"
    folder.mkdir()
    ffmpeg_clip(folder / "b_take.mp4")
    ffmpeg_clip(folder / "a_take.mp4", rate="30")
    monkeypatch.setattr(wsmod, "get_provider", lambda name, c: FakeProvider(c))
    ws = Workspace(cfg)
    res = ws.ingest(folder)
    assert [c.id for c in res["clips"]] == ["c01", "c02"] and res["clips"][0].name == "a_take.mp4"
    out = ws.transcribe("all")
    assert {r["clip"] for r in out} == {"c01", "c02"} and not any(r.get("cached") for r in out)
    assert FakeProvider.calls == 2
    # new file + restart: existing IDs keep their numbers, transcripts come from cache
    ffmpeg_clip(folder / "0_new.mp4", rate="24")
    ws2 = Workspace(cfg)
    assert ws2.folder == folder.resolve()
    res2 = ws2.ingest(folder)
    names = {c.name: c.id for c in res2["clips"]}
    assert names == {"a_take.mp4": "c01", "b_take.mp4": "c02", "0_new.mp4": "c03"}
    out2 = ws2.transcribe(["c01", "c02"])
    assert all(r["cached"] for r in out2) and FakeProvider.calls == 2
    assert "c01 | a_take.mp4" in ws2.list_clips_text()


def test_fingerprint_ignores_mtime(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"x" * 3_000_000)
    a = fingerprint(p)
    import os
    os.utime(p, (1, 1))
    assert fingerprint(p) == a
    p.write_bytes(b"x" * 2_999_999 + b"y")
    assert fingerprint(p) != a


def test_stills_listed_not_transcribed(cfg, tmp_path, monkeypatch):
    import subprocess
    folder = tmp_path / "mix"
    folder.mkdir()
    ffmpeg_clip(folder / "take.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=600x400", "-frames:v", "1",
                    str(folder / "landscape.jpg")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920", "-frames:v", "1",
                    str(folder / "portrait.png")], check=True)
    monkeypatch.setattr(wsmod, "get_provider", lambda name, c: FakeProvider(c))
    ws = Workspace(cfg)
    res = ws.ingest(folder)
    assert [c.id for c in res["clips"]] == ["c01"]
    assert {(s.name, s.width, s.height, s.aspect()) for s in res["stills"]} == {
        ("landscape.jpg", 600, 400, "3:2"), ("portrait.png", 1080, 1920, "9:16")}
    txt = ws.list_clips_text()
    assert "Standbilder" in txt and "9:16 | Hochformat" in txt and "3:2 | Querformat" in txt
    out = ws.transcribe("all")
    assert [r["clip"] for r in out] == ["c01"]
    assert Workspace(cfg).stills.keys() == ws.stills.keys()  # persisted


def test_transcript_variant_follows_current_settings(cfg, tmp_path, monkeypatch):
    folder = tmp_path / "v"
    folder.mkdir()
    ffmpeg_clip(folder / "t.mp4")
    monkeypatch.setattr(wsmod, "get_provider", lambda name, c: FakeProvider(c))
    ws = Workspace(cfg)
    ws.ingest(folder)
    ws.transcribe("all")
    clip = ws.clip("c01")
    assert ws.cached_transcript(clip) is not None
    # a newer file written by different settings must NOT be picked up
    import time
    time.sleep(0.01)
    other = ws.cache.media_dir(clip.fingerprint) / "tokens.gladia.de.ffffffff.json"
    other.write_text(ws._tokens_file(clip, "gladia", "de").read_text().replace("Hallo", "FALSCH"))
    assert ws.cached_transcript(clip).tokens[0].text == "Hallo"
    cfg.gladia_model = "solaria-1"
    assert ws.cached_transcript(clip) is None
    import pytest
    with pytest.raises(LookupError, match="andere Varianten"):
        ws.analyzed(clip)
