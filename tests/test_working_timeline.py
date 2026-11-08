"""Phase 13: backups of the working timeline, hand edits without words, changes directly on the timeline."""
from types import SimpleNamespace as NS

import pytest

from schnippo import prefs, versions
from schnippo.cutlist import Cutlist, CutItem, ManualItem, Piece, Plan, splice_manual
from schnippo.models import AnalyzedTranscript, Clip, Word
from schnippo.resolve_bridge import NotInPlace, apply_edit_steps, edit_steps, free_track, lanes, occupied
from schnippo.revise import timeline_changes


class Item:
    def __init__(self, kind, start, dur, left=0, name="c.mov", mpi=None):
        self.kind, self.s, self.d, self.l, self.name, self.mpi, self.linked, self.right = kind, start, dur, left, name, mpi, [], 500

    def GetType(self): return self.kind
    def GetStart(self): return self.s
    def GetEnd(self): return self.s + self.d
    def GetDuration(self): return self.d
    def GetLeftOffset(self): return self.l
    def GetRightOffset(self): return self.right
    def GetLinkedItems(self): return self.linked
    def GetMediaPoolItem(self): return self.mpi

    def SetRightOffset(self, v):
        self.d -= v - self.right
        self.right = v
        for a in self.linked:
            a.d, a.right = self.d, v
        return True

    def SetLeftOffset(self, v):
        delta = v - self.l
        self.l, self.s, self.d = v, self.s + delta, self.d - delta
        for a in self.linked:
            a.l, a.s, a.d = self.l, self.s, self.d
        return True

    def SetPosition(self, pos, linked=True):
        delta = pos["startFrame"] - self.s
        self.s += delta
        for a in self.linked:
            a.s += delta
        return True

    def SetProperties(self, d): return True
    def GetProperty(self, k): return 1.0


class TL:
    def __init__(self, name, p):
        self.name, self.p, self.items, self.markers = name, p, [], {0: {}}

    def GetName(self): return self.name
    def SetName(self, n): self.name = n; return True
    def GetStartFrame(self): return 1000
    def GetTrackCount(self, k): return max([t for (kk, t) in self.tracks() if kk == k] or [1])
    def tracks(self): return {(i[0], i[1]) for i in self.items}
    def GetItemListInTrack(self, k, n): return [i[2] for i in self.items if i[0] == k and i[1] == n]
    def GetMarkers(self): return dict(self.markers)

    def DuplicateTimeline(self, name):
        if self.p.no_duplicate:
            return None
        t = TL(name, self.p)
        t.items = [(a, b, Item(i.kind, i.GetStart(), i.GetDuration(), i.GetLeftOffset())) for a, b, i in self.items]
        t.markers = dict(self.markers)
        self.p.timelines.append(t)
        self.p.current = t
        self.p.src_bin.append(t)
        return t

    def GetMediaPoolItem(self):
        return NS(tl=self, GetName=lambda: self.name, GetClipProperty=lambda k: "Timeline")

    def DeleteClips(self, items, ripple=False):
        assert not ripple, "ripple shortens clips above the cut"
        self.items = [x for x in self.items if x[2] not in items]
        return True

    def MoveItems(self, items, pos, linked=False):
        delta = pos["startFrame"] - min(i.GetStart() for i in items)
        for i in items:
            i.s += delta
        return True


class Bin:
    def __init__(self, name): self.name, self.subs, self.clips = name, [], []
    def GetName(self): return self.name
    def GetSubFolderList(self): return self.subs
    def GetClipList(self): return self.clips


class MP:
    def __init__(self, p): self.p, self.root, self.cur = p, Bin("Master"), None
    def GetRootFolder(self): return self.root
    def GetCurrentFolder(self): return self.cur
    def SetCurrentFolder(self, f): self.cur = f; return True

    def AddSubFolder(self, parent, name):
        b = Bin(name)
        parent.subs.append(b)
        self.cur = b
        return b

    def MoveClips(self, items, target):
        target.clips += items
        return True

    def DeleteTimelines(self, tls):
        for t in tls:
            self.p.timelines.remove(t)
            self.p.deleted.append(t.name)
            for b in self._bins(self.root):
                b.clips = [c for c in b.clips if c.tl is not t]
        return True

    def _bins(self, f):
        yield f
        for s in f.subs:
            yield from self._bins(s)

    def AppendToTimeline(self, infos):
        out = []
        for ci in infos:
            v = Item("video", ci["recordFrame"], ci["endFrame"] - ci["startFrame"], ci["startFrame"])
            self.p.current.items.append(("video", ci["trackIndex"], v))
            out.append(v)
        return out


class Project:
    def __init__(self):
        self.timelines, self.deleted, self.current, self.src_bin, self.no_duplicate = [], [], None, [], False
        self.mp = MP(self)

    def GetMediaPool(self): return self.mp
    def GetCurrentTimeline(self): return self.current
    def SetCurrentTimeline(self, t): self.current = t; return True
    def GetTimelineCount(self): return len(self.timelines)
    def GetTimelineByIndex(self, i): return self.timelines[i - 1]

    def make(self, name):
        t = TL(name, self)
        t.items = [("video", 1, Item("video", 1000, 100, 7))]
        self.timelines.append(t)
        self.current = t
        return t


def test_name_of_a_backup_and_the_way_back():
    n = versions.version_name("Kurs_Schnippo", "vor Ton-Mastering")
    info = versions.parse(n)
    assert n.startswith("Kurs_Schnippo__") and info["work"] == "Kurs_Schnippo" and info["label"] == "vor Ton-Mastering"
    assert versions.parse("Kurs_Schnippo") is None and versions.parse("Meine_Timeline__alt") is None
    assert versions.work_name("Kurs") == "Kurs_Schnippo" and versions.work_name("Kurs_Schnippo") == "Kurs_Schnippo"


def test_backup_lands_in_the_bin_and_the_working_timeline_stays_current():
    p = Project()
    w = p.make("K_Schnippo")
    b = versions.backup(p, w, "vor Neubau")
    assert p.current is w
    assert [v["name"] for v in versions.versions_of(p, "K_Schnippo")] == [b["name"]]


def test_only_own_backups_are_tidied_up(monkeypatch):
    p = Project()
    w = p.make("K_Schnippo")
    user = p.make("K_Schnippo__mein_Schnitt")  # looks similar, is the user's
    other = p.make("Anderes")
    from datetime import datetime
    for k in range(8):
        versions.backup(p, w, f"t{k}", keep=5, now=datetime(2026, 1, 1, 10, 0, k))
    left = [v["label"] for v in versions.versions_of(p, "K_Schnippo")]
    assert left == ["t7", "t6", "t5", "t4", "t3"]
    assert len(p.deleted) == 3 and all("__2026-01-01" in n for n in p.deleted)
    assert user in p.timelines and other in p.timelines and w in p.timelines


def test_no_backup_no_change():
    p = Project()
    w = p.make("K_Schnippo")
    p.no_duplicate = True
    with pytest.raises(versions.BackupFailed):
        versions.backup(p, w, "x")


def test_a_copy_that_differs_is_no_backup():
    p = Project()
    w = p.make("K_Schnippo")
    original = w.DuplicateTimeline

    def faulty(name):
        t = original(name)
        t.items = []
        return t
    w.DuplicateTimeline = faulty
    with pytest.raises(versions.BackupFailed):
        versions.backup(p, w, "x")
    assert not versions.versions_of(p, "K_Schnippo")


def test_restore_keeps_the_state_it_replaces():
    p = Project()
    w = p.make("K_Schnippo")
    b = versions.backup(p, w, "vor Änderung")
    w.items[0][2].d = 40  # changed after the backup
    res = versions.restore(p, b["name"])
    now = next(t for t in p.timelines if t.name == "K_Schnippo")
    assert now is not w and now.items[0][2].GetDuration() == 100
    assert res["before"] and any(v["name"] == res["before"] for v in versions.versions_of(p, "K_Schnippo"))


def test_restore_refuses_what_is_no_backup():
    p = Project()
    p.make("K_Schnippo")
    with pytest.raises(ValueError):
        versions.restore(p, "K_Schnippo")


CLIP = Clip(id="c01", path="/x/a.mov", fingerprint="f", duration_s=100.0, fps_num=25, fps_den=1, width=1920, height=1080)


def piece(start, end, item=1, **kw):
    return Piece(item=item, clip="c01", start_s=start / 25, end_s=end / 25, start_frame=start, end_frame=end, text="x", **kw)


def v(rec, start, frames):
    return {"clip": "c01", "rec": rec, "src_start": start, "frames": frames}


def test_steps_only_where_something_changes():
    cur = [v(0, 0, 50), v(50, 100, 50), v(100, 200, 50)]
    assert edit_steps(cur, [piece(0, 50), piece(100, 150), piece(200, 250)]) == []
    st = edit_steps(cur, [piece(0, 50), piece(200, 250)])
    assert len(st) == 1 and st[0]["at"] == 50 and st[0]["old"] == 50 and st[0]["new"] == 0 and len(st[0]["cut"]) == 1


def test_a_shorter_piece_is_a_trim_and_keeps_the_item():
    cur = [v(0, 0, 50), v(50, 100, 50)]
    st = edit_steps(cur, [piece(10, 50), piece(100, 150)])
    assert len(st) == 1 and st[0]["trim"] and not st[0]["cut"] and st[0]["new"] == 40


def test_order_changes_are_a_rebuild():
    cur = [v(0, 0, 50), v(50, 100, 50)]
    with pytest.raises(NotInPlace):
        edit_steps(cur, [piece(100, 150), piece(0, 50)])


def test_cut_moves_what_follows_and_leaves_a_clip_over_the_cut_alone():
    p = Project()
    tl = p.make("T")
    tl.items = [("video", 1, Item("video", 1000, 50, 0)), ("video", 1, Item("video", 1050, 50, 100)), ("video", 1, Item("video", 1100, 50, 200))]
    over, later = Item("video", 1040, 30, 0), Item("video", 1120, 10, 0)  # by hand on V2: across the cut, behind the cut
    tl.items += [("video", 2, over), ("video", 2, later)]
    cur = [v(0, 0, 50), v(50, 100, 50), v(100, 200, 50)]
    steps = edit_steps(cur, [piece(0, 50), piece(200, 250)])
    apply_edit_steps(p, tl, steps, {}, 1000)
    got = sorted((i.GetStart() - 1000, i.GetDuration()) for k, n, i in tl.items if n == 1)
    assert got == [(0, 50), (50, 50)]
    assert (over.GetStart(), over.GetDuration()) == (1040, 30)  # keeps its length, unlike a ripple delete
    assert later.GetStart() == 1070


def test_insert_makes_room_first():
    p = Project()
    tl = p.make("T")
    tl.items = [("video", 1, Item("video", 1000, 50, 0)), ("video", 1, Item("video", 1050, 50, 200))]
    cur = [v(0, 0, 50), v(50, 200, 50)]
    target = [piece(0, 50), piece(100, 130), piece(200, 250)]
    apply_edit_steps(p, tl, edit_steps(cur, target), {"c01": object()}, 1000)
    assert sorted((i.GetStart() - 1000, i.GetDuration(), i.GetLeftOffset()) for k, n, i in tl.items) == [(0, 50, 0), (50, 30, 100), (80, 50, 200)]


def test_trim_closes_the_gap():
    p = Project()
    tl = p.make("T")
    tl.items = [("video", 1, Item("video", 1000, 50, 0)), ("video", 1, Item("video", 1050, 50, 100)), ("video", 1, Item("video", 1100, 50, 200))]
    cur = [v(0, 0, 50), v(50, 100, 50), v(100, 200, 50)]
    target = [piece(0, 50), piece(110, 140), piece(200, 250)]
    apply_edit_steps(p, tl, edit_steps(cur, target), {}, 1000)
    assert sorted((i.GetStart() - 1000, i.GetDuration(), i.GetLeftOffset()) for k, n, i in tl.items) == [(0, 50, 0), (50, 30, 110), (80, 50, 200)]


def test_free_track_never_lands_on_something_placed_by_hand():
    items = [{"kind": "video", "track": 2, "rec": 100, "frames": 50}, {"kind": "video", "track": 3, "rec": 120, "frames": 10}]
    assert free_track(items, "video", 2, 0, 50) == 2
    assert free_track(items, "video", 2, 110, 130) == 4
    assert not occupied(items, "video", 2, 150, 160)


def test_manual_clips_follow_the_frame_they_belong_to():
    clips = {"c01": CLIP}
    plan = Plan(pieces=[piece(0, 50, 1), piece(100, 150, 2)])
    cl = Cutlist(items=[], manual=[
        ManualItem(media="/x/a.mov", source_in_frame=500, source_out_frame=520, track=1, record_frame=50, frames=20, anchor=("c01", 49)),
        ManualItem(media="/x/b.mov", source_in_frame=0, source_out_frame=30, track=2, record_frame=90, frames=30, anchor=("c01", 120)),
    ])
    splice_manual(cl, plan, clips)
    assert [(p.clip, p.frames, p.manual) for p in plan.pieces] == [("c01", 50, False), ("c01", 20, True), ("c01", 50, False)]
    assert plan.manual[0]["tl_start"] == 50 + 20 + 20  # over the same frame, shifted by the inserted clip


def test_a_manual_clip_whose_frame_is_gone_stays_where_it_was_and_says_so():
    clips = {"c01": CLIP}
    plan = Plan(pieces=[piece(0, 50)])
    cl = Cutlist(items=[], manual=[ManualItem(media="/x/b.mov", source_in_frame=0, source_out_frame=30, track=2, record_frame=90, frames=30, anchor=("c01", 700))])
    splice_manual(cl, plan, clips)
    assert plan.manual[0]["tl_start"] == 90 and any("bleibt bei Position 90" in w for w in plan.warnings)


def transcript():
    entries = [Word(id=f"w{k:04d}", text="wort", start_s=k * 1.0, end_s=k * 1.0 + 0.5, kind="word", confidence=0.9) for k in range(1, 20)]
    return AnalyzedTranscript(clip_id="c01", provider="fake", language="de", entries=entries)


def built():
    cl = Cutlist(timeline_name="K_Schnippo", items=[CutItem(clip="c01", from_word="w0001", to_word="w0002"), CutItem(clip="c01", from_word="w0005", to_word="w0006")])
    plan = Plan(pieces=[Piece(item=1, clip="c01", start_s=1, end_s=2.5, start_frame=25, end_frame=63, text="wort wort", word_ids=["w0001", "w0002"]),
                        Piece(item=2, clip="c01", start_s=5, end_s=6.5, start_frame=125, end_frame=163, text="wort wort", word_ids=["w0005", "w0006"])])
    return cl, plan


def row(rec, src, frames, clip="c01", path="/x/a.mov", name="a.mov", zoom=1.0):
    return {"clip": clip, "name": name, "path": path, "rec": rec, "frames": frames, "src_start": src, "fps": 25.0, "zoom": zoom, "pan": 0.0, "tilt": 0.0, "linked_audio": [(rec, frames)]}


def test_a_clip_without_words_becomes_a_manual_item():
    cl, plan = built()
    tl = {"name": "K_Schnippo", "v1": [row(0, 25, 38), row(38, 800, 20), row(58, 125, 38)], "upper": {}, "fps": 25.0}  # 800–820: no word there
    res = timeline_changes(cl, plan, tl, {"c01": transcript()}, {"c01": CLIP})
    assert res["changed"] and not [u for u in res["unclear"] if "bleibt nur" in u]
    assert [(m.source_in_frame, m.source_out_frame, m.track, m.anchor) for m in res["cutlist"].manual] == [(800, 820, 1, ("c01", 62))]


def test_a_foreign_clip_is_kept_by_its_file():
    cl, plan = built()
    tl = {"name": "K_Schnippo", "v1": [row(0, 25, 38), row(38, 0, 20, clip=None, path="/elsewhere/logo.mov", name="logo.mov"), row(58, 125, 38)], "upper": {}, "fps": 25.0}
    res = timeline_changes(cl, plan, tl, {"c01": transcript()}, {"c01": CLIP})
    assert res["cutlist"].manual[0].media == "/elsewhere/logo.mov"


def test_a_title_without_a_file_is_reported():
    cl, plan = built()
    tl = {"name": "K_Schnippo", "v1": [row(0, 25, 38), row(38, 0, 20, clip=None, path="", name="Titel"), row(58, 125, 38)], "upper": {}, "fps": 25.0}
    res = timeline_changes(cl, plan, tl, {"c01": transcript()}, {"c01": CLIP})
    assert any("Titel" in u and "Neubau" in u for u in res["unclear"])


def test_a_gap_on_v1_survives():
    cl, plan = built()
    tl = {"name": "K_Schnippo", "v1": [row(0, 25, 38), row(50, 125, 38)], "upper": {}, "fps": 25.0}
    res = timeline_changes(cl, plan, tl, {"c01": transcript()}, {"c01": CLIP})
    gap = res["cutlist"].manual[0]
    assert res["changed"] and gap.media == "" and gap.frames == 12 and gap.anchor == ("c01", 62)


def test_a_zoom_set_by_hand_is_adopted():
    cl, plan = built()
    tl = {"name": "K_Schnippo", "v1": [row(0, 25, 38, zoom=1.3), row(38, 125, 38)], "upper": {}, "fps": 25.0}
    res = timeline_changes(cl, plan, tl, {"c01": transcript()}, {"c01": CLIP})
    assert res["changed"] and res["cutlist"].items[0].zoom == 1.3


def test_nothing_changed_is_nothing_changed():
    cl, plan = built()
    tl = {"name": "K_Schnippo", "v1": [row(0, 25, 38), row(38, 125, 38)], "upper": {}, "fps": 25.0}
    assert not timeline_changes(cl, plan, tl, {"c01": transcript()}, {"c01": CLIP})["changed"]


def test_checkpoints_are_a_preference(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHNIPPO_CONFIG", str(tmp_path / "config.toml"))
    d = prefs.load()
    d["preferences"]["checkpoints"] = "keine"
    prefs.save(d)
    cfg = NS(checkpoints="nur wenn nötig", setting_problems=[])
    prefs.apply(cfg)
    assert cfg.checkpoints == "keine"


def test_sfx_lanes_stay_separate():
    cues = [{"tl_start": 0, "frames": 10}, {"tl_start": 5, "frames": 10}, {"tl_start": 20, "frames": 5}]
    assert len(lanes(cues)) == 2
