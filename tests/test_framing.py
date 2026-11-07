import numpy as np
import pytest

from schnippo.cutlist import Cutlist, build_plan
from schnippo.framing import punch_in, px_per_unit

from test_cutlist import CLIP as _CLIP, at  # noqa: F401

CLIP = _CLIP.model_copy(update={"width": 180, "height": 320})


def test_px_per_unit_matches_measurements():
    assert px_per_unit(1080, 1080) == 1.0  # video item at timeline resolution: 1 px per unit (measured)
    assert px_per_unit(1280, 1080) == pytest.approx(1.185, abs=0.01)  # filled 2:3 still: measured 1.2


def test_punch_in_keeps_face_and_never_shows_borders():
    pan, tilt = punch_in(0.5, 0.5, 1.12, 1080, 1920)
    assert (pan, tilt) == (0.0, 0.0)
    pan, tilt = punch_in(0.6, 0.35, 1.12, 1080, 1920)  # face right of centre and high
    assert pan == pytest.approx(-0.1 * 0.12 * 1080) and tilt == pytest.approx(-0.15 * 0.12 * 1920)
    # face at the edge → clamped to the maximum shift (no border)
    pan, tilt = punch_in(1.0, 0.0, 1.12, 1080, 1920)
    assert pan == pytest.approx(-0.06 * 1080) and tilt == pytest.approx(-0.06 * 1920)  # face at top → image down
    assert punch_in(0.9, 0.9, 1.0, 1080, 1920) == (0.0, 0.0)


def faces(n=361, box=(60, 40, 20, 20), size=(180, 320)):
    return {"c01": (np.array([box] * n), size)}


def test_alternating_zooms_at_jump_cuts_and_overrides(at):
    cl = Cutlist(items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0003"},
                        {"clip": "c01", "from_word": "w0004", "to_word": "w0007"},
                        {"clip": "c01", "from_word": "w0008", "to_word": "w0008", "zoom": 1.3}],
                 punch_in={"mode": "alternate", "scale": 1.12})
    plan = build_plan(cl, {"c01": CLIP}, {"c01": at}, faces=faces())
    zs = [p.zoom for p in plan.pieces]
    assert zs[:4] == [1.0, 1.12, 1.0, 1.12] and zs[-1] == 1.3
    p1 = plan.pieces[1]
    assert p1.pan != 0 and p1.tilt != 0  # face at (70/180, 50/320) → off-centre framing
    off = Cutlist(items=cl.items, punch_in={"mode": "off"})
    assert [p.zoom for p in build_plan(off, {"c01": CLIP}, {"c01": at}, faces=faces()).pieces][-1] == 1.3


def test_cut_under_overlay_keeps_zoom_level(at):
    cl = Cutlist(items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0003"},
                        {"clip": "c01", "from_word": "w0004", "to_word": "w0005"}],
                 overlays=[{"media": "i01", "from_word": "c01:w0003", "to_word": "c01:w0004"}],
                 punch_in={"mode": "alternate", "scale": 1.12})
    plan = build_plan(cl, {"c01": CLIP}, {"c01": at}, stills={"i01"}, faces=faces())
    assert plan.ok, plan.errors
    assert plan.pieces[0].zoom == plan.pieces[1].zoom == 1.0  # the #01→#02 cut is covered by the overlay


def test_zoom_levels_vary_never_repeat_and_respect_the_source():
    from schnippo.profiles import make_profile, max_zoom_for
    p = make_profile("youtube")
    assert p.punch_in_scale == 1.2 and p.accent_scale == 1.32
    assert max_zoom_for(p, 1920, 1080) == 1.25 and max_zoom_for(p, 3840, 2160) == 2.0
    assert abs(max_zoom_for(p, 2560, 1440) - 4 / 3) < 1e-6


def test_variation_sequence(at):
    import copy
    from schnippo.cutlist import Plan, Piece, assign_zooms
    from schnippo.profiles import make_profile
    pieces = [Piece(item=1, clip="c01", start_s=k, end_s=k + 1, start_frame=k * 30, end_frame=k * 30 + 30, text="Satz.",
                    word_ids=[]) for k in range(13)]
    cl = Cutlist(items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0008"}],
                 punch_in={"mode": "alternate", "scale": 1.2, "rule": "sentence", "variation": [1.12, 1.25], "variation_every": 3})
    plan = Plan(pieces=copy.deepcopy(pieces))
    assign_zooms(cl, plan, {"c01": CLIP}, {}, make_profile("youtube"))
    zs = [p.zoom for p in plan.pieces]
    assert zs == [1.0, 1.2, 1.0, 1.2, 1.0, 1.12, 1.0, 1.2, 1.0, 1.2, 1.0, 1.25, 1.0]
    assert all(a != b for a, b in zip(zs, zs[1:]))
