"""Frame-rate cascade of build_timeline against a fake Resolve that reproduces behaviour measured on 21.1.2:
  * timelinePlaybackFrameRate is read-only; new projects start 24/24; project rate locked once a timeline exists
    (regression: RC_v1 was built at 30 fps with playback 24 and reported "verified");
  * Timeline.SetSettings(useCustomSettings=1, timelineFrameRate=…) accepts whole rates only, and custom timelines
    report no playback rate;
  * ImportTimelineFromFile(FCPXML) creates a custom timeline with the file's rate, places clips frame-exact
    (source TC honoured), does not import markers and does not link A/V items.
"""

import re
from fractions import Fraction

import pytest

from schnippo.cutlist import Cutlist, Piece
from schnippo.models import Clip
from schnippo.resolve_bridge import BuildError, build_timeline

PATH = "/media/take.mov"


class Item:
    def __init__(self, start, dur, left, kind="video"):
        self.s, self.d, self.l, self.kind, self.linked = start, dur, left, kind, []

    def GetStart(self): return self.s
    def GetEnd(self): return self.s + self.d
    def GetDuration(self): return self.d
    def GetLeftOffset(self): return self.l
    def GetType(self): return self.kind
    def GetLinkedItems(self): return self.linked
    def AddTransition(self, opts): return object()


class Timeline:
    def __init__(self, name, project, fps=None, custom=False):
        self.name, self.p, self.items, self.markers = name, project, [], {}
        self.custom = custom
        self.fps = fps if fps is not None else project.settings["timelineFrameRate"]

    def GetName(self): return self.name
    def SetName(self, n): self.name = n; return True
    def GetStartFrame(self): return 108000
    def GetEndFrame(self): return max([i.GetEnd() for i in self.items] or [108000])
    def GetMarkers(self): return dict(self.markers)
    def AddMarker(self, f, c, n, note, d, cd=None): self.markers[f] = n; return True
    def GetItemListInTrack(self, kind, idx): return [i for i in self.items if i.kind == kind]

    def GetSettings(self):
        if self.custom:
            return {"timelineFrameRate": self.fps, "useCustomSettings": "1"}
        return {"timelineFrameRate": self.p.settings["timelineFrameRate"],
                "timelinePlaybackFrameRate": self.p.settings["timelinePlaybackFrameRate"]}

    def SetSettings(self, d):
        if self.p.custom_settings_broken:
            return False
        ok = True
        for k, v in d.items():
            if k == "useCustomSettings":
                self.custom = v == "1"
            elif k == "timelineFrameRate":
                if not self.custom or float(v) != int(float(v)):
                    ok = False  # 21.1.2: fractional custom rates are refused
                else:
                    self.fps = float(v)
        return ok


class MediaPool:
    def __init__(self, project): self.p = project
    def GetRootFolder(self): return self
    def GetClipList(self): return [self.p.clip_item]
    def GetSubFolderList(self): return []

    def CreateEmptyTimeline(self, name):
        tl = Timeline(name, self.p)
        self.p.timelines.append(tl)
        return tl

    def DeleteTimelines(self, tls):
        for t in tls:
            assert not t.items, "must only delete empty timelines it created"
            self.p.timelines.remove(t)
        self.p.deleted += len(tls)
        return True

    def AppendToTimeline(self, infos):
        tl, out = self.p.current, []
        for ci in infos:
            dur = ci["endFrame"] - ci["startFrame"]
            v, a = Item(ci["recordFrame"], dur, ci["startFrame"]), Item(ci["recordFrame"], dur, ci["startFrame"], "audio")
            v.linked = [a]
            tl.items += [v, a]
            out.append(v)
        return out

    def ImportTimelineFromFile(self, path, opts):
        self.p.imports.append(path)
        if self.p.import_broken:
            return None
        xml = open(path, encoding="utf-8").read()
        fd = Fraction(re.search(r'frameDuration="([\d/]+)s"', xml).group(1))
        fps = 1 / fd
        tl = Timeline(opts["timelineName"], self.p, fps=round(float(fps), 3), custom=True)
        a_start = Fraction(re.search(r'<asset [^>]*start="([\d/]+)s"', xml).group(1))
        tc0 = Fraction(re.search(r'tcStart="([\d/]+)s"', xml).group(1))
        for m in re.finditer(r'<asset-clip [^>]*offset="([\d/]+)s" start="([\d/]+)s" duration="([\d/]+)s"', xml):
            off, st, du = (Fraction(x) for x in m.groups())
            rec = 108000 + int((off - tc0) * fps)
            left, dur = int((st - a_start) * fps), int(du * fps)
            tl.items += [Item(rec, dur, left), Item(rec, dur, left, "audio")]  # not linked
        self.p.timelines.append(tl)
        return tl


class ClipItem:
    def __init__(self, fps, frames, tc): self.props = {"File Path": PATH, "FPS": fps, "Frames": str(frames), "Start TC": tc}
    def GetClipProperty(self, k=None): return self.props[k] if k else dict(self.props)
    def GetParentFolder(self): return "bin"


class Project:
    def __init__(self, name, fps=24.0, playback="24", timelines=0, clip_fps=30.0, frames=6705, tc="23:52:51:00"):
        self.name = name
        self.settings = {"timelineFrameRate": fps, "timelinePlaybackFrameRate": playback,
                         "timelineResolutionWidth": "1920", "timelineResolutionHeight": "1080"}
        self.timelines, self.current = [], None
        self.timelines += [Timeline(f"old{i}", self) for i in range(timelines)]
        self.mp, self.clip_item = MediaPool(self), ClipItem(clip_fps, frames, tc)
        self.custom_settings_broken = self.import_broken = False
        self.deleted, self.imports = 0, []

    def GetName(self): return self.name
    def GetSettings(self): return dict(self.settings)
    def GetTimelineCount(self): return len(self.timelines)
    def GetTimelineByIndex(self, i): return self.timelines[i - 1]
    def SetCurrentTimeline(self, tl): self.current = tl; return True
    def GetMediaPool(self): return self.mp

    def SetSettings(self, d):
        ok = True
        for k, v in d.items():
            if k == "timelinePlaybackFrameRate":
                ok = False  # read-only
            elif k == "timelineFrameRate":
                if self.timelines:
                    ok = False
                else:
                    self.settings[k] = float(v)
            else:
                self.settings[k] = v
        return ok


class Bridge:
    def __init__(self, p): self.p = p
    def resolve(self): return self
    def GetProjectManager(self): return self
    def SaveProject(self): return True
    def project(self): return self.p
    def import_clips(self, *a): return {}


def clip(fps, num, den, frames, w=1920, h=1080, rot=90):
    return Clip(id="c01", path=PATH, fingerprint="f", duration_s=frames / fps, fps_num=num, fps_den=den, width=w,
                height=h, rotation=rot, resolve_fps=fps, resolve_frames=frames, audio_channels=1)


CL = Cutlist(timeline_name="RC", items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0008", "note": "Hook"},
                                         {"clip": "c01", "from_word": "w0018", "to_word": "w0027"}])
PIECES = [Piece(item=1, clip="c01", start_s=3.75, end_s=6.4, start_frame=112, end_frame=192, text="a"),
          Piece(item=2, clip="c01", start_s=13.0, end_s=15.43, start_frame=389, end_frame=463, text="b")]


def build(p, c, tmp_path, **kw):
    secs = sum(pc.frames for pc in PIECES) / c.resolve_fps
    return build_timeline(Bridge(p), CL, PIECES, {"c01": c}, None, "testdata", master_clip="c01", plan_seconds=secs,
                          work_dir=str(tmp_path), **kw)


C30 = clip(30.0, 30, 1, 6705)


def test_project_already_right_uses_project_settings(tmp_path):
    p = Project("P30", fps=30.0, playback="30", timelines=2)
    t = build(p, C30, tmp_path)["timeline"]
    assert t["way"] == "Projekt-Einstellungen" and t["verified"], t["errors"]


def test_30p_take_in_existing_24p_project_uses_own_timeline_settings(tmp_path):
    p = Project("P24", timelines=1)
    t = build(p, C30, tmp_path)["timeline"]
    assert t["way"] == "eigene Timeline-Einstellungen" and t["verified"], t["errors"]
    rb = t["readback"]
    assert (rb["project_fps"], rb["timeline_fps"], rb["timeline_playback_fps"]) == (24.0, 30.0, None)
    assert t["seconds"] == pytest.approx(154 / 30, abs=1e-3) and t["markers"] == 2
    assert p.settings["timelineFrameRate"] == 24.0  # the user's project is not touched


def test_regression_rc_v1_playback_24_is_not_accepted(tmp_path):
    """Project rate 30 but playback 24 (the RC_v1 state) must not be built with project settings."""
    p = Project("Testprojekt", fps=30.0, playback="24", timelines=2)
    t = build(p, C30, tmp_path)["timeline"]
    assert t["way"] != "Projekt-Einstellungen" and t["verified"]
    assert any("project_playback_fps=24" in a for a in t["attempts"])


def test_empty_project_sets_rate_but_playback_does_not_follow(tmp_path):
    p = Project("Empty", timelines=0)
    rc = build(p, C30, tmp_path)
    assert p.settings["timelineFrameRate"] == 30.0 and p.settings["timelinePlaybackFrameRate"] == "24"
    assert rc["timeline"]["way"] == "eigene Timeline-Einstellungen" and rc["timeline"]["verified"]
    assert any("leer" in n for n in rc["notes"]) and p.deleted == 0  # playback checked before creating anything


def test_2997_clip_in_25p_project_goes_via_fcpxml(tmp_path):
    p = Project("P25", fps=25.0, playback="25", timelines=1, clip_fps=29.97, frames=599, tc="00:00:00:00")
    c = clip(29.97, 30000, 1001, 599, 640, 360, 0)
    t = build(p, c, tmp_path)["timeline"]
    assert t["way"] == "FCPXML-Import" and t["verified"], t["errors"]
    assert t["readback"]["timeline_fps"] == pytest.approx(29.97)
    assert t["markers_from_file"] == 0 and t["markers"] == 2  # markers added via API after import
    xml = open(p.imports[0], encoding="utf-8").read()
    assert 'frameDuration="1001/30000s"' in xml and 'width="640" height="360"' in xml


def test_take_timecode_is_written_so_import_lands_frame_exact(tmp_path):
    p = Project("P24", timelines=1)
    t = build(p, C30, tmp_path, force_way="fcpxml")["timeline"]
    assert t["way"] == "FCPXML-Import" and t["verified"], t["errors"]  # left offsets 112/389 despite TC 23:52:51:00


def test_custom_settings_refused_falls_back_to_fcpxml_and_cleans_up(tmp_path):
    p = Project("P24", timelines=1)
    p.custom_settings_broken = True
    t = build(p, C30, tmp_path)["timeline"]
    assert t["way"] == "FCPXML-Import" and t["verified"]
    assert p.deleted == 1 and [x.name for x in p.timelines] == ["old0", "RC"]


def test_everything_fails_gives_instructions_and_leaves_nothing(tmp_path):
    p = Project("P25", fps=25.0, playback="25", timelines=1, clip_fps=29.97, frames=599, tc="00:00:00:00")
    p.import_broken = True
    c = clip(29.97, 30000, 1001, 599, 640, 360, 0)
    with pytest.raises(BuildError, match="Use Project Settings.*29.97"):
        build(p, c, tmp_path)
    assert [x.name for x in p.timelines] == ["old0"]
