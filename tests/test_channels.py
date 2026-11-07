import json
import subprocess

import pytest

from schnippo import audio
from schnippo.resolve_bridge import remap_channels

# speech-like: tone bursts (on/off) so speech level and noise floor differ
SPEECH = "sine=f=220:d=6,volume='if(lt(mod(t,1),0.6),1,0.001)':eval=frame"


def make(tmp_path, name, filt, streams=2):
    f = tmp_path / name
    maps = sum((["-map", f"[o{k}]"] for k in range(streams)), [])
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", SPEECH, "-f", "lavfi", "-i",
                    "anoisesrc=d=6:c=pink:a=0.002:seed=1", "-f", "lavfi", "-i", "anoisesrc=d=6:c=white:a=0.3:seed=7",
                    "-filter_complex", filt, *maps, "-c:a", "pcm_s16le", str(f)], check=True)
    return str(f)


def test_identical(tmp_path):
    f = make(tmp_path, "id.mov", "[0:a][1:a]amix=inputs=2:normalize=0,asplit[o0][o1]")
    r = audio.channel_analysis(f, seconds=6)
    assert r["class"] == "identisch" and r["best"] == 1 and r["correlation"] > 0.999


def test_unbalanced_picks_cleaner_channel(tmp_path):
    f = make(tmp_path, "unb.mov", "[0:a][1:a]amix=inputs=2:normalize=0,asplit[a][b];[a]volume=-8dB[o0];"
                                  "[b][2:a]amix=inputs=2:normalize=0,volume=0.5[o1]")
    r = audio.channel_analysis(f, seconds=6)
    assert r["class"] == "unausgewogen", r
    assert r["best"] == 1 and "Rauschunterschied" in r["reason"]


def test_different_mics(tmp_path):
    f = make(tmp_path, "diff.mov", "[0:a][1:a]amix=inputs=2:normalize=0[o0];[2:a]volume=0.2[o1]")
    r = audio.channel_analysis(f, seconds=6)
    assert r["class"] == "verschieden" and r["best"] == 1 and "Sprach/Rausch" in r["reason"]


def test_stereo_stays_and_mono(tmp_path):
    f = make(tmp_path, "st.mov", "[0:a][1:a]amix=inputs=2:normalize=0,asplit[a][b];[a]volume=0.95[o0];"
                                 "[b]adelay=1|1,volume=1.0[o1]")
    r = audio.channel_analysis(f, seconds=6)
    assert r["class"] == "stereo" and r["best"] is None
    one = make(tmp_path, "mono.mov", "[0:a]anull[o0]", streams=1)
    assert audio.channel_analysis(one, seconds=6)["class"] == "mono"


class MPI:
    def __init__(self, path): self.path = path
    def GetClipProperty(self, k): return self.path


class AItem:
    def __init__(self, mpi): self.mpi, self.map = mpi, {"embedded_audio_channels": 2, "linked_audio": {},
                                                          "track_mapping": {"1": {"channel_idx": [1], "mute": False, "type": "mono"}}}
    def GetMediaPoolItem(self): return self.mpi
    def GetSourceAudioChannelMapping(self): return json.dumps(self.map)
    def SetSourceAudioChannelMapping(self, s): self.map = json.loads(s); return True


class TL:
    def __init__(self, mpi): self.tracks = {1: [AItem(mpi), AItem(mpi)], 2: [AItem(mpi), AItem(mpi)]}
    def GetTrackCount(self, t): return len(self.tracks)
    def GetItemListInTrack(self, t, k): return self.tracks.get(k, [])
    def DeleteTrack(self, t, k): self.tracks.pop(k); return True


def test_remap_to_one_centred_track():
    m = MPI("/x/take.mov")
    tl = TL(m)
    info = remap_channels(tl, {"c01": m}, {"c01": {"class": "unausgewogen", "best": 2, "reason": "r"}})
    assert info["mapped"] == 2 and info["tracks_before"] == 2 and info["tracks_after"] == 1 and not info["errors"]
    assert all(it.map["track_mapping"] == {"1": {"channel_idx": [2], "mute": False, "type": "mono"}} for it in tl.tracks[1])
    tl2 = TL(m)
    info2 = remap_channels(tl2, {"c01": m}, {"c01": {"class": "stereo", "best": None, "reason": "r"}})
    assert info2["mapped"] == 0 and len(tl2.tracks) == 2  # real stereo stays


def test_speaker_channels_one_mic_per_person(tmp_path):
    # speaker 0 talks 0–3 s into channel 1 (loud) / channel 2 (crosstalk), speaker 1 talks 3–6 s the other way round
    f2 = tmp_path / "iv.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", SPEECH, "-filter_complex",
                    "[0:a]asplit=2[a][b];[a]volume='if(lt(t,3),1,0.05)':eval=frame[l];"
                    "[b]volume='if(lt(t,3),0.05,1)':eval=frame[r];[l][r]amerge=inputs=2[o]", "-map", "[o]",
                    "-c:a", "pcm_s16le", str(f2)], check=True)
    res = audio.speaker_channels(str(f2), {0: [(0.0, 0.6), (1.0, 1.6), (2.0, 2.6)], 1: [(3.0, 3.6), (4.0, 4.6), (5.0, 5.6)]})
    assert res["split"] and res["by_speaker"] == {0: 1, 1: 2}, res
    one = audio.speaker_channels(str(f2), {0: [(0.0, 0.6), (1.0, 1.6)], 1: [(2.0, 2.6)]})  # both loudest on channel 1
    assert not one["split"] and one["by_speaker"] == {}


class OItem(AItem):
    def __init__(self, mpi, off): super().__init__(mpi); self.off = off
    def GetLeftOffset(self): return self.off


def test_remap_per_piece_by_speaker():
    m = MPI("/x/iv.mov")
    tl = TL(m)
    tl.tracks = {1: [OItem(m, 100), OItem(m, 500), OItem(m, 900)]}
    info = remap_channels(tl, {"c01": m}, {"c01": {"class": "je Sprecher", "best": 2, "reason": "r",
                                                   "by_speaker": {0: 2, 1: 1}, "by_start": {100: 2, 500: 1, 900: 2}}})
    assert [it.map["track_mapping"]["1"]["channel_idx"] for it in tl.tracks[1]] == [[2], [1], [2]]
    assert info["per_channel"] == {2: 2, 1: 1} and info["mapped"] == 3


def _stereo(tmp_path, name, left, right):
    f = tmp_path / name
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", SPEECH, "-f", "lavfi", "-i",
                    "anoisesrc=d=6:c=pink:a=0.002:seed=1", "-filter_complex",
                    f"[0:a][1:a]amix=inputs=2:normalize=0,asplit=2[a][b];[a]{left}[l];[b]{right}[r];[l][r]amerge=inputs=2[o]",
                    "-map", "[o]", "-c:a", "pcm_s16le", str(f)], check=True)
    return str(f)


def test_safety_track_prefers_the_louder_main_channel(tmp_path):
    f = _stereo(tmp_path, "safety.wav", "volume=0.5", "volume=0.25")  # channel 2 = −6 dB copy (same SNR)
    res = audio.channel_analysis(f)
    assert res["class"] == "unausgewogen" and res["best"] == 1 and "Sicherheitsspur" in res["reason"], res
    f2 = _stereo(tmp_path, "clip.wav", "volume=12", "volume=1")  # main clips (sine 1/8 × 12 > full scale)
    res2 = audio.channel_analysis(f2)
    assert res2["best"] == 2 and "übersteuert" in res2["reason"], res2
