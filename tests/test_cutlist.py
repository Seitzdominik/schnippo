import math

import pytest

from schnippo.analysis import analyze
from schnippo.cutlist import CutOptions, Cutlist, build_plan, plan_item, plan_text
from schnippo.models import Clip
from schnippo.segments import segment

from conftest import make_acoustic, make_raw

FPS = 30.0
CLIP = Clip(id="c01", path="/x/t.mov", fingerprint="f", duration_s=12.0, fps_num=30, fps_den=1, resolve_fps=30.0,
            resolve_frames=360)
SPEC = [
    ("Eins", 1.00, 1.30), ("zwei", 1.35, 1.60), ("drei.", 1.65, 2.00),  # w1-3
    ("Vier", 3.00, 3.30), ("fünf", 4.30, 4.60),  # w4-5: 0.70 s pause inside
    ("sechs", 4.62, 4.90), ("sieben.", 5.20, 5.50),  # w6-7: voiced "äh" 4.95-5.15 between
    ("Acht", 5.52, 5.80),  # w8 directly after w7
]
VOICED = [(1.0, 2.0), (3.0, 3.3), (4.3, 4.9), (4.95, 5.15), (5.2, 5.8)]


@pytest.fixture
def at(cfg):
    return analyze("c01", make_raw(SPEC), cfg, acoustic=make_acoustic(12.0, VOICED, [(2.6, 2.9)]), clip_duration_s=12.0)


def pieces(at, n0, n1, **opt):
    return plan_item(1, CLIP, at, n0, n1, CutOptions(**opt), FPS, 360)


def test_padding_and_frame_rounding(at):
    (p,) = pieces(at, 1, 3)
    assert p.start_s == pytest.approx(0.92) and p.end_s == pytest.approx(2.12)  # 80 ms pre, 120 ms post
    assert (p.start_frame, p.end_frame) == (math.floor(0.92 * 30), math.ceil(2.12 * 30))  # 27, 64 (exclusive)


def test_padding_never_reaches_into_neighbour_word(at):
    (p,) = pieces(at, 8, 8)  # 'Acht' starts 20 ms after 'sieben.' ends
    assert p.start_s == pytest.approx(5.52)  # max(5.50 + 0.02, 5.52 - 0.08)
    (p,) = pieces(at, 7, 7)
    assert p.end_s == pytest.approx(5.50)  # min(5.50 + 0.12, 5.52 - 0.02)


def test_breath_stays_in_preroll_but_preroll_not_extended(at):
    (p,) = pieces(at, 4, 4)  # breath 2.6-2.9 just before 'Vier' (3.00)
    assert p.start_s == pytest.approx(2.92)


def test_long_pause_and_filler_are_tightened(at):
    ps = pieces(at, 4, 7)
    assert len(ps) == 3  # cut at the 1.0 s pause (w4|w5) and around the {?} (w6|w7)
    assert ps[0].end_s == pytest.approx(3.30 + 0.07) and ps[1].start_s == pytest.approx(4.30 - 0.08)
    assert ps[1].end_s <= 4.95 - 0.02 + 1e-9 and ps[2].start_s >= 5.15 + 0.02 - 1e-9  # filler removed
    assert [p.text for p in ps] == ["Vier", "fünf sechs", "sieben."]
    assert len(pieces(at, 4, 7, tighten_gaps_over_ms=2000, cut_fillers=False)) == 1


def test_validation_errors_and_warnings(at, cfg):
    segs = {"c01": segment(at, cfg, 12.0)}
    cl = Cutlist(items=[{"clip": "c01", "from_word": "w0004", "to_word": "w0005"},
                        {"clip": "c01", "from_word": "w0005", "to_word": "w0006"},  # overlaps #1
                        {"clip": "c01", "from_word": "w0001", "to_word": "w0002"},  # jumps back
                        {"clip": "c01", "from_word": "w0009", "to_word": "w0009"},  # unknown
                        {"clip": "c02", "from_word": "w0001", "to_word": "w0001"},
                        {"clip": "c01", "from_word": "w0003", "to_word": "w0002"}],
                 rejected=[{"segment": "c01:s009", "reason": "x"}])
    plan = build_plan(cl, {"c01": CLIP}, {"c01": at}, segs)
    txt = " | ".join(plan.errors)
    assert "#2: überlappt mit #1" in txt and "w0009" in txt and "unbekannter Clip" in txt and "liegt nach" in txt
    assert "unbekanntes Segment c01:s009" in txt
    assert any("springt in der Aufnahme zurück" in w for w in plan.warnings)
    assert not plan.ok


def test_plan_text_shows_spoken_result(at, cfg):
    cl = Cutlist(timeline_name="T", items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0003", "note": "Intro"},
                                           {"clip": "c01", "from_word": "w0004", "to_word": "w0007"}])
    plan = build_plan(cl, {"c01": CLIP}, {"c01": at})
    assert plan.ok
    txt = plan_text(cl, plan, {"c01": CLIP})
    assert "GÜLTIG" in txt and "Eins zwei drei. ‖ Vier | fünf sechs | sieben." in txt
    assert "#01 c01 w0001–w0003" in txt and "Intro" in txt


def test_rejected_segment_format():
    with pytest.raises(ValueError):
        Cutlist(items=[], rejected=[{"segment": "s003"}])


# ---------------- motion-aware cut points
import numpy as np

from schnippo.cutlist import _choose, cut_list


def test_choose_nearest_calm_frame_only_when_restless():
    m = {k: v for k, v in enumerate([1, 1, 1, 5, 9, 9, 9])}
    score = lambda k: m.get(k, 1)
    assert _choose(5, 0, 6, score, quiet=2.5, trigger=4) == 2  # nearest calm frame before the gesture
    assert _choose(1, 0, 6, score, quiet=2.5, trigger=4) == 1  # calm default stays
    assert _choose(5, 4, 6, score, quiet=2.5, trigger=4) == 5  # nothing calm, nothing clearly better → default


def test_motion_moves_start_before_gesture_but_never_into_word(at):
    motion = np.full(361, 1.0, dtype=np.float32)
    motion[86:100] = 20.0  # gesture right before 'Vier' (3.00 s = frame 90); default start 2.92 s = frame 87
    plain = pieces(at, 4, 4)
    moved = plan_item(1, CLIP, at, 4, 4, CutOptions(), FPS, 360, motion)
    assert plain[0].start_frame == 87 and moved[0].start_frame == 84  # calm frames 84/85 before the gesture
    assert moved[0].start_shift == -3 and moved[0].start_motion <= 2.5
    motion2 = np.full(361, 1.0, dtype=np.float32)
    motion2[60:100] = 20.0  # restless across the whole window → nothing clearly better, keep default
    assert plan_item(1, CLIP, at, 4, 4, CutOptions(), FPS, 360, motion2)[0].start_frame == 87
    off = plan_item(1, CLIP, at, 4, 4, CutOptions(motion_aware_cuts=False), FPS, 360, motion)
    assert off[0].start_frame == 87 and off[0].start_motion is None


def test_validate_lists_cuts_with_motion_and_flags(at, cfg):
    motion = np.full(361, 1.0, dtype=np.float32)
    motion[128:132] = 30.0  # restless around the start of 'fünf' (4.30 s = frame 129), an internal cut
    cl = Cutlist(timeline_name="T", items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0003"},
                                           {"clip": "c01", "from_word": "w0004", "to_word": "w0007"}])
    plan = build_plan(cl, {"c01": CLIP}, {"c01": at}, motions={"c01": motion})
    txt = plan_text(cl, plan, {"c01": CLIP})
    assert "Schnitte (Bewegung" in txt and "S00 Anfang" in txt and "S01 #01→#02" in txt
    ids = [c["id"] for c in cut_list(plan)]
    assert ids[0] == "S00" and ids[-1] == f"S{len(plan.pieces):02d}"


# ---------------- Phase 4: explicit start/end frames, tempo cap, no-face frames
from schnippo.frames import cut_motion


def test_explicit_start_end_frames_checked(at, cfg):
    def plan_for(**kw):
        cl = Cutlist(items=[{"clip": "c01", "from_word": "w0004", "to_word": "w0004", **kw}])
        return build_plan(cl, {"c01": CLIP}, {"c01": at})
    ok = plan_for(start_frame="c01:f0088", end_frame="c01:f0100")
    assert ok.ok and (ok.pieces[0].start_frame, ok.pieces[0].end_frame) == (88, 101)  # end_frame is inclusive
    assert "anschneid" not in " ".join(ok.errors)
    cut_word = plan_for(start_frame="c01:f0091")  # 'Vier' starts at 3.00 s = frame 90
    assert any("schneidet das erste Wort an" in e for e in cut_word.errors)
    cut_end = plan_for(end_frame="c01:f0095")  # 'Vier' ends 3.30 s = frame 99
    assert any("schneidet das letzte Wort an" in e for e in cut_end.errors)
    early = plan_for(start_frame="c01:f0050")  # before the window (previous word 'drei.' ends 2.00 s = frame 60)
    assert early.ok and any("vor dem erlaubten Fenster" in w for w in early.warnings)
    assert any("gehört nicht zu" in e for e in plan_for(start_frame="c02:f0088").errors)


def test_motion_shift_capped_for_tempo(at):
    motion = np.full(361, 1.0, dtype=np.float32)
    motion[70:100] = 20.0  # gesture starts 0.6 s before the default start → calm frame only far away
    capped = plan_item(1, CLIP, at, 4, 4, CutOptions(), FPS, 360, motion)  # default cap 200 ms = 6 frames
    assert capped[0].start_frame >= 87 - 6
    wide = plan_item(1, CLIP, at, 4, 4, CutOptions(max_motion_shift_ms=1000, motion_extend_pre_ms=1000), FPS, 360, motion)
    assert wide[0].start_frame == 68  # first two shown frames (68, 69) calm


def test_frames_without_face_count_as_restless():
    boxes = np.array([[10, 10, 20, 20]] * 6 + [[-1, -1, -1, -1]] * 4, dtype=np.int32)
    pa = {"boxes": boxes, "person": np.full(10, 1.0, np.float32), "global": np.full(10, 9.0, np.float32)}
    m = cut_motion(pa)
    assert (m[:6] == 1.0).all() and (m[6:] >= 50).all()
    pa["boxes"][:] = -1  # B-roll without people → global motion
    assert (cut_motion(pa) == 9.0).all()
