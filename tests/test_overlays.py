import pytest

from schnippo import kenburns
from schnippo.cutlist import Cutlist, build_plan, plan_text
from schnippo.models import Still
from schnippo.resolve_bridge import place_overlays

from test_cutlist import CLIP, at  # noqa: F401  (fixture)


def cl_with(*overlays):
    return Cutlist(timeline_name="T", items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0003"},
                                             {"clip": "c01", "from_word": "w0004", "to_word": "w0007"}],
                   overlays=list(overlays))


# word→timeline mapping without the snapping to cuts (snapping has its own tests in test_snap.py)
from schnippo.profiles import make_profile  # noqa: E402

RAW = make_profile("reel", "ruhig-dicht", {"overlay_snap_s": 0, "sliver_s": 0, "cover_margin_frames": 0, "broll_min_s": 0,
                                           "broll_max_s": 99})


def test_overlay_maps_words_to_cut_timeline_across_items(at):
    cl = cl_with({"media": "i01", "from_word": "c01:w0002", "to_word": "c01:w0005", "note": "Bild"})
    plan = build_plan(cl, {"c01": CLIP}, {"c01": at}, stills={"i01"}, prof=RAW)
    assert plan.ok, plan.errors
    (o,) = plan.overlays
    p1 = plan.pieces[0]
    assert o.tl_start == round(1.35 * 30) - p1.start_frame  # 'zwei' starts 1.35 s, piece 1 starts at frame 27
    # 'fünf' (w0005) ends 4.60 s inside the second item's second piece → mapped through the pieces
    recs = [0]
    for pc in plan.pieces[:-1]:
        recs.append(recs[-1] + pc.frames)
    pc = next((pc, r) for pc, r in zip(plan.pieces, recs) if pc.start_frame <= 138 <= pc.end_frame)
    assert o.tl_end == pc[1] + 138 - pc[0].start_frame
    txt = plan_text(cl, plan, {"c01": CLIP})
    assert "O1 i01 V2" in txt and "Eins [i01 ▶ zwei drei." in txt and "fünf ◀]" in txt


@pytest.mark.parametrize("ov,msg", [
    ({"media": "i09", "from_word": "c01:w0001", "to_word": "c01:w0002"}, "unbekanntes Standbild"),
    ({"media": "i01", "from_word": "w0001", "to_word": "c01:w0002"}, "braucht den Clip"),
    ({"media": "i01", "from_word": "c01:w0008", "to_word": "c01:w0008"}, "nicht (vollständig) im Schnitt"),
    ({"media": "i01", "from_word": "c01:w0003", "to_word": "c01:w0001"}, "Ende liegt vor dem Anfang"),
    ({"media": "c05", "from_word": "c01:w0001", "to_word": "c01:w0002", "from_frame": "c05:f0001"}, "unbekannter Clip"),
    ({"media": "c01", "from_word": "c01:w0001", "to_word": "c01:w0002"}, "braucht from_frame"),
    ({"media": "i01", "from_word": "c01:w0001", "to_word": "c01:w0002", "track": 1}, "Spur muss"),
])
def test_overlay_validation_errors(at, ov, msg):
    plan = build_plan(cl_with(ov), {"c01": CLIP}, {"c01": at}, stills={"i01"})
    assert any(msg in e for e in plan.errors), plan.errors


def test_overlapping_overlays_on_same_track_rejected(at):
    plan = build_plan(cl_with({"media": "i01", "from_word": "c01:w0001", "to_word": "c01:w0003"},
                              {"media": "i01", "from_word": "c01:w0002", "to_word": "c01:w0004"}),
                      {"c01": CLIP}, {"c01": at}, stills={"i01"})
    assert any("überlappt Overlay 1" in e for e in plan.errors)


def test_bad_option_values():
    with pytest.raises(ValueError):
        cl_with({"media": "i01", "from_word": "c01:w0001", "to_word": "c01:w0002", "motion": "spin"})


# ---------------- placement against a fake Resolve (behaviour measured on 21.1.2)
class Item:
    def __init__(self, start, dur, still):
        self.s, self.d, self.still, self.props, self.ro = start, dur, still, {"Scaling": 0, "DynamicZoomEnabled": False}, 10**6

    def GetStart(self): return self.s
    def GetDuration(self): return self.d
    def GetLinkedItems(self): return []
    def GetRightOffset(self): return self.ro
    def GetProperty(self, k): return self.props.get(k)

    def SetRightOffset(self, v):
        self.d -= v - self.ro
        self.ro = v
        return True

    def SetProperties(self, d):
        self.props.update(d)
        return True


class TL:
    def __init__(self): self.tracks = {1: [Item(108000, 300, False)], 2: []}
    def GetStartFrame(self): return 108000
    def GetTrackCount(self, k): return len(self.tracks)
    def AddTrack(self, k): self.tracks[len(self.tracks) + 1] = []; return True
    def GetItemListInTrack(self, k, i): return self.tracks.get(i, [])


class Pool:
    def __init__(self, tl): self.tl, self.files = tl, {}
    def GetRootFolder(self): return self
    def GetSubFolderList(self): return []
    def GetClipList(self): return list(self.files.values())

    def AppendToTimeline(self, infos):
        out = []
        for ci in infos:
            still = ci["mediaPoolItem"].still
            dur = 150 if still else ci["endFrame"] - ci["startFrame"]  # stills ignore endFrame
            it = Item(ci["recordFrame"], dur, still)
            self.tl.tracks[ci["trackIndex"]].append(it)
            out.append(it)
        return out


class File:
    def __init__(self, path): self.path, self.still = path, not path.endswith(".mov")
    def GetClipProperty(self, k=None): return self.path


class Bridge:
    def __init__(self, pool): self.pool = pool
    def import_clips(self, paths, bin_name):
        for x in paths:
            self.pool.files[str(x)] = File(str(x))


class R:
    SCALE_FILL, SCALE_FIT, DYNAMIC_ZOOM_EASE_LINEAR = 3, 2, 0


class P:
    def __init__(self, pool): self.pool = pool
    def GetMediaPool(self): return self.pool


def test_place_overlays_native_and_rendered(at, tmp_path, monkeypatch):
    rendered = []

    def fake_render(src, out_dir, w, h, num, den, frames, motion, focus, rot):
        rendered.append((motion, focus, frames, w, h))
        return tmp_path / f"r_{motion}_{focus}.mov"
    monkeypatch.setattr(kenburns, "render_still", fake_render)
    plan = build_plan(cl_with({"media": "i01", "from_word": "c01:w0001", "to_word": "c01:w0002", "motion": "slow_zoom_out"},
                              {"media": "i01", "from_word": "c01:w0004", "to_word": "c01:w0005", "motion": "slow_zoom_in"},
                              {"media": "i01", "from_word": "c01:w0006", "to_word": "c01:w0007", "focus": "left", "track": 3}),
                      {"c01": CLIP}, {"c01": at}, stills={"i01"}, prof=RAW)
    assert plan.ok, plan.errors
    tl = TL()
    pool = Pool(tl)
    st = Still(id="i01", path=str(tmp_path / "a.jpg"), fingerprint="x", width=600, height=400)
    res = place_overlays(Bridge(pool), R, P(pool), tl, plan.overlays, {"i01": st}, "bin", 30.0, 1080, 1920, tmp_path, plan.pieces)
    assert all(r["verified"] for r in res), res
    o1, o2, o3 = res
    assert o1["way"] == "nativ + Dynamic Zoom" and tl.tracks[2][0].d == plan.overlays[0].frames  # trimmed from 150
    assert tl.tracks[2][0].props["Scaling"] == 3 and tl.tracks[2][0].props["DynamicZoomEnabled"] is True
    assert o2["way"].startswith("gerendert") and o3["track"] == 3 and len(tl.tracks) == 3
    assert [(m, f) for m, f, *_ in rendered] == [("slow_zoom_in", "center"), ("none", "left")]
    assert rendered[0][3:] == (1080, 1920)


def test_render_still_real_ffmpeg(tmp_path):
    import subprocess
    src = tmp_path / "s.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=600x400", "-frames:v", "1", str(src)], check=True)
    out = kenburns.render_still(src, tmp_path / "r", 108, 192, 30000, 1001, 12, "slow_zoom_in", "center")
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_frames",
                           "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    assert info == "prores,108,192,30000/1001,12"
    assert kenburns.render_still(src, tmp_path / "r", 108, 192, 30000, 1001, 12, "slow_zoom_in", "center") == out  # cached
    assert kenburns.needs_render("slow_zoom_out", "center") is False and kenburns.needs_render("none", "left") is True
