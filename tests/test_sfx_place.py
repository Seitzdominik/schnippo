from types import SimpleNamespace as NS

import pytest

from schnippo import sfx
from schnippo.cutlist import Cutlist, PlacedGraphic, PlacedOverlay, Piece, Plan, SfxCue
from schnippo.passes import resolve
from schnippo.profiles import make_profile
from schnippo.resolve_bridge import _apply_audio, lanes, place_sfx, sfx_tracks
from schnippo.revise import apply_ops

FPS = 25.0
LIB = [{"id": "riser_a", "file": "/l/riser_a.wav", "category": "riser", "intensity": 1, "duration_ms": 1500, "hit_offset_ms": 1500, "audible_ms": 1500, "peak_rms_db": -13.0, "event_align": "end"},
       {"id": "bird", "file": "/u/bird.wav", "category": "atmo", "intensity": 2, "duration_ms": 9000, "hit_offset_ms": 0, "audible_ms": 9000, "peak_rms_db": -20.0, "type": "bed", "event_align": "start"},
       {"id": "clock_a", "file": "/l/clock_a.wav", "category": "clock", "intensity": 1, "duration_ms": 3000, "hit_offset_ms": 0, "audible_ms": 3000, "peak_rms_db": -25.0, "type": "bed", "event_align": "start"},
       {"id": "type_a", "file": "/l/type_a.wav", "category": "typing", "intensity": 1, "duration_ms": 3000, "hit_offset_ms": 0, "audible_ms": 3000, "peak_rms_db": -23.0, "type": "sequence", "event_align": "start"},
       {"id": "down_a", "file": "/l/down_a.wav", "category": "downer", "intensity": 2, "duration_ms": 700, "hit_offset_ms": 2, "audible_ms": 500, "peak_rms_db": -10.0},
       {"id": "swish_a", "file": "/l/swish_a.wav", "category": "swish", "intensity": 1, "duration_ms": 240, "hit_offset_ms": 120, "audible_ms": 200, "peak_rms_db": -15.0},
       {"id": "tick_a", "file": "/l/tick_a.wav", "category": "tick", "intensity": 1, "duration_ms": 90, "hit_offset_ms": 8, "audible_ms": 40, "peak_rms_db": -18.0},
       {"id": "tick_b", "file": "/l/tick_b.wav", "category": "tick", "intensity": 2, "duration_ms": 70, "hit_offset_ms": 8, "audible_ms": 40, "peak_rms_db": -18.0},
       {"id": "impact_a", "file": "/l/impact_a.wav", "category": "impact_soft", "intensity": 2, "duration_ms": 800, "hit_offset_ms": 20, "audible_ms": 600, "peak_rms_db": -10.0},
       {"id": "whoosh_a", "file": "/l/whoosh_a.wav", "category": "whoosh", "intensity": 1, "duration_ms": 500, "hit_offset_ms": 318, "audible_ms": 450, "peak_rms_db": -14.0}]
TOK = {"motion": {"dur": {"in_ms": 300, "emph_ms": 500}, "stagger": {"text_after_box_frames": 2, "line_ms": 0}}}


def _word(i, a, b, text):
    return NS(id=f"w{i:04d}", start_s=a, end_s=b, text=text, kind="word", flags=[])


def _setup(cues, seconds=40, **kw):
    """One sentence of one word per 2 s; the hook sentence ends at 2 s."""
    n = seconds // 2
    words = [_word(i + 1, i * 2.0, i * 2.0 + 1.5, f"Satz{i}.") for i in range(n)]
    pc = Piece(item=1, clip="c01", start_s=0, end_s=seconds, start_frame=0, end_frame=seconds * 25, text="x", word_ids=[w.id for w in words])
    plan = Plan(pieces=[pc])
    plan.graphics = [PlacedGraphic(index=1, template="counter", params={}, track=3, tl_start=250, tl_end=325, words=("c01:w0001", "c01:w0002")),
                     PlacedGraphic(index=2, template="callout", params={}, track=3, tl_start=500, tl_end=575, words=("c01:w0001", "c01:w0002"))]
    plan.overlays = [PlacedOverlay(index=1, media="i01", track=2, tl_start=400, tl_end=475, words=("c01:w0001", "c01:w0002"), fit="", focus="", motion="")]
    cl = Cutlist(sfx=cues)
    clips = {"c01": NS(resolve_fps=FPS, fps=FPS)}
    analyzed = {"c01": NS(entries=words)}
    prof = make_profile(kw.pop("fmt", "reel"), "ruhig-dicht", {}, None)
    sfx.place(cl, plan, clips, analyzed, prof, TOK, {"library": LIB, "mode": kw.pop("mode", "subtil"), "style": kw.pop("style", None), "voice_lufs": -14.0})
    return plan


def test_transient_lands_on_the_event():
    plan = _setup([SfxCue(category="swish", at="O1"), SfxCue(category="tick", at="G1"), SfxCue(category="impact_soft", at="G2", event="in")])
    s1, s2, s3 = plan.sfx
    assert (s1.event_frame, s1.tl_start) == (400, 397)  # 120 ms = 3 frames before the picture change
    assert s2.event == "end" and s2.what == "Endwert" and s2.event_frame == 250 + round((80 + 500) / 40)
    assert s3.event_frame == 250 + 250 + 4 and s3.what == "Box öffnet"
    assert s1.gain_db == -22 and s2.gain_db == -20
    assert s1.volume_db == round(-14 - 22 + 15, 1)


def test_word_reference_and_unknown_elements():
    plan = _setup([SfxCue(category="impact_soft", at="c01:w0005")])
    assert plan.sfx[0].event_frame == 200 and not plan.errors
    plan = _setup([SfxCue(category="tick", at="G9"), SfxCue(category="nope", at="G1")])
    assert len(plan.errors) == 2 and not plan.sfx


def test_off_ignores_list():
    plan = _setup([SfxCue(category="tick", at="G1")], mode="off")
    assert not plan.sfx and "off" in plan.warnings[0]


@pytest.mark.parametrize("style,cat,picked", [("tech", "whoosh", "tick_a"), ("minimal", "tick", "tick_a"), ("bold", "tick", "tick_b")])
def test_design_language(style, cat, picked):
    plan = _setup([SfxCue(category=cat, at="O1")], style=style)
    assert plan.sfx[0].id == picked


def test_design_language_levels():
    assert sfx.default_gain("whoosh", "subtil", "minimal") == -24
    assert sfx.default_gain("tick", "normal", "bold") == -18
    assert sfx.default_gain("tick", "subtil", None) == -20


def test_variants_rotate_without_explicit_intensity():
    plan = _setup([SfxCue(category="tick", at="c01:w0004"), SfxCue(category="tick", at="c01:w0008")])
    assert [s.id for s in plan.sfx] == ["tick_a", "tick_b"]


def test_rules_distance_hook_cta_count():
    plan = _setup([SfxCue(category="tick", at="c01:w0001", intensity=1)])
    assert plan.errors or any("Hook" in w for w in plan.warnings) or plan.sfx == []
    plan = _setup([SfxCue(category="tick", at="c01:w0005"), SfxCue(category="tick", at="c01:w0006")])
    assert any("auseinander" in w for w in plan.warnings)
    plan = _setup([SfxCue(category="tick", at="c01:w0020")])
    assert any("CTA" in w for w in plan.warnings)
    plan = _setup([SfxCue(category="tick", at="c01:w0020", deliberate=True)])
    assert not any("CTA" in w for w in plan.warnings)
    many = [SfxCue(category="tick", at=f"c01:w{n:04d}") for n in range(3, 19, 2)]
    plan = _setup(many)
    assert any("höchstens" in w for w in plan.warnings)
    assert not any("höchstens" in w for w in _setup(many, seconds=400, fmt="youtube").warnings)


def test_tail_into_next_sentence_and_beyond_element():
    plan = _setup([SfxCue(category="impact_soft", at="c01:w0005", note="x")])
    assert any("nächsten Satz" in w for w in plan.warnings) is False  # 600 ms ends before the next word at +2 s
    cues = [{"label": "S1", "event": 100, "start": 98, "end": 130, "target_end": 120, "deliberate": False, "kind": "oneshot"}]
    found = sfx.rules(cues, {"hook_end": 10, "cta": 900, "sentences": [110], "cuts": []}, 25.0, 5)
    assert [h for h, _ in found] == [False, False]


def test_not_on_every_cut():
    cues = [{"label": f"S{k}", "event": f, "start": f, "end": f + 2, "target_end": None, "deliberate": False} for k, f in enumerate((100, 200, 300))]
    found = sfx.rules(cues, {"hook_end": 10, "cta": 900, "sentences": [], "cuts": [100, 200, 300, 400]}, 25.0, 5)
    assert any("Schnitten" in t for _, t in found)


def test_mode_through_the_field_name():
    assert Cutlist(sfx="off").sfx_mode == "off" and Cutlist(sfx="off").sfx == []


def test_passes_keep_and_replace():
    prof = make_profile("reel", "ruhig-dicht", {}, None)
    item = {"clip": "c01", "from_word": "w0001", "to_word": "w0002"}
    base = Cutlist.model_validate({"name": "A", "pass": "broll", "items": [item], "sfx": [{"category": "swish", "at": "O1"}]})
    eff, _ = resolve(Cutlist.model_validate({"pass": "polish", "base_cutlist": "A_V3_BRoll", "audio": {"target_lufs": -14}}), base, prof)
    assert len(eff.sfx) == 1
    eff, notes = resolve(Cutlist.model_validate({"pass": "motion", "base_cutlist": "A_V4_Polish", "sfx": [{"category": "tick", "at": "G1"}]}), base, prof)
    assert [c.category for c in eff.sfx] == ["tick"] and any("ersetzt" in n for n in notes)
    eff, notes = resolve(Cutlist.model_validate({"pass": "fine", "base_cutlist": "A_V1_Rough", "sfx": [{"category": "tick", "at": "G1"}]}), base, prof)
    assert eff.sfx == [] and any("sfx" in n for n in notes)


def test_revise_ops_follow_overlays():
    from schnippo.cutlist import CutItem, Overlay
    base = Cutlist(items=[CutItem(clip="c01", from_word="w0001", to_word="w0002")],
                   overlays=[Overlay(media="i01", from_word="c01:w0001", to_word="c01:w0002"), Overlay(media="i02", from_word="c01:w0001", to_word="c01:w0002")],
                   sfx=[SfxCue(category="swish", at="O1"), SfxCue(category="swish", at="O2"), SfxCue(category="tick", at="c01:w0002")])
    cl, log = apply_ops(base, [{"op": "remove_overlay", "ref": "O1"}, {"op": "remove_sfx", "ref": "S3"}, {"op": "add_sfx", "category": "pop", "at": "G1"}], None)
    assert [(c.category, c.at) for c in cl.sfx] == [("swish", "O1"), ("pop", "G1")]


class _Item:
    def __init__(self, start, dur, tl, path):
        self.s, self.d, self.path, self.vol = start, dur, path, None
    GetStart = lambda self: self.s
    GetDuration = lambda self: self.d
    GetType = lambda self: "audio"
    def SetProperty(self, k, v):
        self.vol = v
        return True
    GetProperty = lambda self, k: self.vol
    def SetProperties(self, d):
        self.vol = d.get("AudioVolume", self.vol)
    GetMediaPoolItem = lambda self: None
    def AddEffect(self, *a):
        self.fx = True


class _Tl:
    def __init__(self, tracks=1):
        self.names = {k: f"Audio {k}" for k in range(1, tracks + 1)}
        self.items = {k: [] for k in self.names}
    def AddTrack(self, kind, sub):
        k = len(self.names) + 1
        self.names[k], self.items[k] = f"Audio {k}", []
        return True
    GetTrackCount = lambda self, kind: len(self.names)
    def SetTrackName(self, kind, k, n):
        self.names[k] = n
        return True
    GetTrackName = lambda self, kind, k: self.names[k]
    GetStartFrame = lambda self: 1000
    GetItemListInTrack = lambda self, kind, k: self.items[k]
    SetTrackEnable = lambda self, *a: True


def test_bridge_places_whole_files_on_own_track(monkeypatch):
    tl = _Tl()
    class Clip:
        GetClipProperty = lambda self, k: "/x/a.wav"
    class Mp:
        GetRootFolder = lambda self: None
        def AppendToTimeline(self, infos):
            i = infos[0]
            assert i["mediaType"] == 2 and "startFrame" not in i
            tl.items[i["trackIndex"]].append(_Item(i["recordFrame"], 6, tl, "/x/a.wav"))
    monkeypatch.setattr("schnippo.resolve_bridge._all_clips", lambda root: [Clip()])
    p = NS(GetMediaPool=lambda: Mp())
    cue = {"index": 1, "id": "a", "file": "/x/a.wav", "tl_start": 50, "frames": 6, "volume_db": -30.0}
    out = place_sfx(NS(), p, tl, [cue])
    assert out[0]["verified"] and sfx_tracks(tl) == [2] and tl.items[2][0].vol == -30.0


def test_overlapping_effects_get_their_own_track():
    c = lambda i, s, f: {"index": i, "tl_start": s, "frames": f}
    got = lanes([c(1, 100, 10), c(2, 590, 25), c(3, 604, 46), c(4, 700, 10)])
    assert [[x["index"] for x in lane] for lane in got] == [[1, 2, 4], [3]]


def test_audio_stage_leaves_the_effects_alone():
    tl = _Tl(2)
    tl.names[2] = "SFX"
    voice, fx = _Item(0, 100, tl, "v"), _Item(10, 5, tl, "s")
    fx.vol = -33.0
    tl.items = {1: [voice], 2: [fx]}
    opts = NS(dialogue_leveler=False, voice_isolation=False, deesser="off", limiter=True, tp_strategy="limiter_only", normalize=True,
              target_lufs=-14.0, post_compressor_offset_db=0.0, max_iterations=1, tolerance_lu=0.5, true_peak_max=-1.0)
    r = NS(GetEffectsList=lambda kind: [{"name": "Limiter", "id": "L"}])
    res = _apply_audio(r, NS(), tl, opts, None, None, lambda *a: None, lambda f: {"lufs": -14.0, "true_peak": -2.0}, True, {}, None)
    assert fx.vol == -33.0 and not hasattr(fx, "fx") and voice.fx and res["lufs_ok"]


def _qc(plan, items):
    from schnippo import qc
    tl = {"v1": [], "frames": 1000, "fps": FPS, "upper": {}, "audio": {}, "sfx": items, "readback": {"timeline_fps": FPS, "timeline_playback_fps": FPS}}
    prof = make_profile("reel", "ruhig-dicht", {}, None)
    plan.sfx_info = {"limit": 5}
    words = [_word(i + 1, i * 2.0, i * 2.0 + 1.5, f"Satz{i}.") for i in range(20)]
    return qc.run(tl, {}, {"c01": NS(entries=words)}, prof, None, plan)["lines"]


def test_qc_reads_the_track_back():
    plan = _setup([SfxCue(category="swish", at="O1"), SfxCue(category="tick", at="G2")])
    good = [{"rec": s.tl_start, "frames": s.frames, "name": s.id, "volume": s.volume_db} for s in plan.sfx]
    lines = _qc(plan, good)
    assert any(x.startswith("✅ SFX-Spur: 2") for x in lines) and any(x.startswith("✅ SFX-Regeln") for x in lines)
    moved = [{**good[0], "rec": 300}, {**good[1], "volume": 0.0}]
    assert any(x.startswith("❌ SFX-Spur") and "S1, S2" in x for x in _qc(plan, moved))
    assert any(x.startswith("❌ SFX-Spur") for x in _qc(plan, []))


def test_qc_flags_rule_breaks():
    plan = _setup([SfxCue(category="swish", at="O1"), SfxCue(category="tick", at="c01:w0009")])
    assert plan.sfx[1].event_frame == 400
    items = [{"rec": s.tl_start, "frames": s.frames, "name": s.id, "volume": s.volume_db} for s in plan.sfx]
    assert any(x.startswith("❌ SFX-Regeln") and "auseinander" in x for x in _qc(plan, items))


def test_riser_ends_on_the_event():
    plan = _setup([SfxCue(category="riser", at="O1")])
    s = plan.sfx[0]
    assert (s.event_frame, s.tl_start, s.tl_start + s.frames) == (400, 400 - 38, 400)  # 1.5 s = 37.5 frames, ends on the picture change


def test_bed_follows_its_overlay_and_lies_deep():
    plan = _setup([SfxCue(category="atmo", at="O1")])
    s = plan.sfx[0]
    assert s.kind == "bed" and s.length_ms == 3000 and s.tl_start == 400 and s.frames == 75 and s.gain_db == -30
    assert not any("Atmo" in w for w in plan.warnings)
    plan = _setup([SfxCue(category="atmo", at="c01:w0005", duration_ms=3000)])
    assert any("Atmo nur" in w for w in plan.warnings)


def test_beds_do_not_count_as_effects():
    plan = _setup([SfxCue(category="atmo", at="O1"), SfxCue(category="swish", at="O1")])
    assert not any("auseinander" in w for w in plan.warnings)


def test_sequence_stays_short_and_takes_duration():
    plan = _setup([SfxCue(category="typing", at="G2")])
    assert plan.sfx[0].length_ms == 2000
    plan = _setup([SfxCue(category="typing", at="c01:w0005", duration_ms=1200)])
    assert plan.sfx[0].length_ms == 1200 and plan.sfx[0].frames == 30


def test_only_one_downer_and_impacts_not_in_a_row():
    plan = _setup([SfxCue(category="downer", at="c01:w0005"), SfxCue(category="downer", at="c01:w0012")])
    assert any("Downer" in w for w in plan.warnings)
    plan = _setup([SfxCue(category="impact_soft", at="c01:w0005"), SfxCue(category="impact_soft", at="c01:w0012")])
    assert any("hintereinander" in w for w in plan.warnings) and any("Impact" in w and "höchstens" in w for w in plan.warnings)


def test_fit_length_loops_and_cuts():
    import numpy as np
    x = np.ones((48000, 2)) * 0.5
    y = sfx.fit_length(x, 2.5, 0.1)
    assert len(y) == 120000 and abs(y[60000, 0] - 0.5) < 1e-6 and y[0, 0] == 0 and abs(y[-1, 0]) < 1e-6
    assert len(sfx.fit_length(x, 0.4, 0.05)) == 19200


def test_build_refuses_unnamed_project():
    from schnippo.resolve_bridge import BuildError, build_timeline
    bridge = NS(resolve=lambda: NS(GetProjectManager=lambda: None), project=lambda: NS(GetName=lambda: "Untitled Project 2026-11-06_141125"))
    with pytest.raises(BuildError, match="kein eigenes Projekt"):
        build_timeline(bridge, None, [], {}, None, "Bin", "c01", 0.0)
