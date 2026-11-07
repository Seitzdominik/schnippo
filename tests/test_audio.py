import subprocess

import numpy as np

from schnippo import audio
from schnippo.cutlist import AudioOptions
from schnippo.resolve_bridge import apply_audio


def test_ebur128_and_program_filter(tmp_path):
    f = tmp_path / "t.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=1000:d=4:sample_rate=48000", "-af", "volume=-20dB",
                    str(f)], check=True)
    m = audio.ebur128(["-i", str(f)])
    assert -42 < m["lufs"] < -40 and -39 < m["true_peak"] < -37  # sine amplitude 1/8 (−18 dBFS) − 20 dB
    p = audio.ebur128(["-i", str(f)], audio.program_filter([(0.0, 1.0), (2.0, 3.0)]))
    assert abs(p["lufs"] - m["lufs"]) < 1.0


def test_spectral_profile_flags_sibilance_and_rumble():
    ref = dict(audio.LTASS)
    flat = audio.spectral_profile(ref)
    assert flat["rumble_db"] == 0 and flat["sibilance_db"] == 0
    hissy = {f: v + (8 if f >= 5000 else 0) + (7 if f <= 63 else 0) for f, v in ref.items()}
    sp = audio.spectral_profile(hissy)
    rec = audio.recommendations({"lufs": -30, "true_peak": -3, "spectrum": sp})
    assert sp["sibilance_db"] > 4 and any("De-Esser" in r for r in rec) and any("Rumpeln +" in r for r in rec)
    assert any("Limiter nötig" in r for r in rec)


class Item:
    def __init__(self): self.props, self.fx = {"AudioVolume": 0.0}, []
    def GetType(self): return "audio"
    def SetProperties(self, d): self.props.update(d); return True
    def GetProperty(self, k): return self.props.get(k)
    def AddEffect(self, cat, i): self.fx.append(i); return object()


class TL:
    def __init__(self, tracks=1):
        self.items, self.a2, self.n, self.disabled = [Item(), Item()], [Item(), Item()], tracks, []
    def GetTrackCount(self, k): return self.n
    def GetItemListInTrack(self, k, i): return self.items if i == 1 else self.a2
    def SetTrackEnable(self, k, i, on): self.disabled.append(i); return True


class R:
    def GetEffectsList(self, t): return [{"name": "Limiter", "id": "lim"}, {"name": "De-Esser", "id": "dees"},
                                         {"name": "Multiband Compressor", "id": "mbc"}]


def test_apply_audio_iterates_gain_to_target(tmp_path):
    tl = TL()
    # fake render/measure: loudness responds to gain with a compressor-like slope of 0.8; limiter caps TP at -0.2
    def measure(tag):
        g = tl.items[0].props["AudioVolume"]
        return {"lufs": -27.7 + 0.8 * g, "true_peak": min(-2.9 + g, -0.2 if tl.items[0].fx else 99), "lra": 7}
    res = apply_audio(R(), None, tl, AudioOptions(tp_strategy="limiter_only"), {"sibilance_db": -11.3}, tmp_path,
                      render=lambda t, preset=None: t, measure=measure)
    assert res["lufs_ok"] and abs(res["after"]["lufs"] + 14) <= 0.5 and res["iterations"] >= 2
    assert all(i.fx == ["lim"] for i in tl.items)  # no de-esser: sibilance below threshold
    assert not res["tp_ok"] and any("Ceiling" in n for n in res["notes"])
    assert any("kein De-Esser" in n for n in res["notes"])


def test_duplicate_tracks_are_muted_not_doubled(tmp_path):
    tl = TL(tracks=2)
    measure = lambda tag: {"lufs": -14.0, "true_peak": -0.2, "lra": 7}
    res = apply_audio(R(), None, tl, AudioOptions(), None, tmp_path, render=lambda t, preset=None: t, measure=measure, duplicate_tracks=True)
    assert tl.disabled == [2] and any("stummgeschaltet" in a for a in res["actions"])
    assert all(i.fx == ["lim", "mbc"] for i in tl.items) and all(i.fx == [] for i in tl.a2)
    assert all(i.props["AudioVolume"] == -100.0 for i in tl.a2)  # disabled tracks were still rendered with a preset
    tl2 = TL(tracks=2)
    apply_audio(R(), None, tl2, AudioOptions(), None, tmp_path, render=lambda t, preset=None: t, measure=measure, duplicate_tracks=False)
    assert tl2.disabled == [] and all(i.fx == ["lim", "mbc"] for i in tl2.items + tl2.a2)


def test_identical_audio_streams(tmp_path):
    f = tmp_path / "two.mov"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=2", "-filter_complex", "[0:a]asplit[a][b]",
                    "-map", "[a]", "-map", "[b]", "-c:a", "pcm_s16le", str(f)], check=True)
    assert audio.identical_audio_streams(str(f)) is True
    g = tmp_path / "one.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(g)], check=True)
    assert audio.identical_audio_streams(str(g)) is None


def test_post_compressor_chain_and_export_preset(tmp_path):
    """Default tp_strategy: Limiter → Multiband Compressor; the compressor after the limiter lowers level and peaks
    (fake: −6 LU, TP ceiling −0.2 − 2.6); gain iterated to −14; export preset created and reported."""
    tl = TL()
    used = []

    def measure(tag):
        g = tl.items[0].props["AudioVolume"]
        mbc = "mbc" in tl.items[0].fx
        lufs = -27.7 + g - (6.0 if mbc else 0.0)
        tp = min(-2.9 + g, -0.2) - (2.6 if mbc else 0.0)
        return {"lufs": round(lufs, 2), "true_peak": tp, "lra": 4}

    res = apply_audio(R(), P(), tl, AudioOptions(), None, tmp_path, render=lambda t, preset=None: used.append(preset) or t,
                      measure=measure, presets={"check": lambda: "chk", "delivery": lambda: "deliv"})
    assert all(i.fx == ["lim", "mbc"] for i in tl.items) and res["chain"] == ["Limiter", "Multiband Compressor"]
    assert res["lufs_ok"] and res["tp_ok"] and res["after"]["true_peak"] <= -1.0 and res["iterations"] == 1
    assert set(used) == {"chk"} and res["delivery_preset"] == "deliv"
    res2 = apply_audio(R(), P(), TL(), AudioOptions(tp_strategy="limiter_only"), None, tmp_path,
                       render=lambda t, preset=None: t, measure=lambda t: {"lufs": -14.0, "true_peak": -0.2, "lra": 7})
    assert not res2["tp_ok"] and any("limiter_only" in n for n in res2["notes"])


class P:
    def LoadRenderPreset(self, n): return True
