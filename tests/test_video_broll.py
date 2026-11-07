"""Video B-roll overlays: source-frame mapping at other frame rates, slow motion, shortening (Phase 8)."""
from schnippo.cutlist import build_plan, plan_text
from schnippo.models import Clip

from test_cutlist import CLIP, at  # noqa: F401  (fixture)
from test_overlays import RAW, cl_with

B60 = Clip(id="c05", path="/x/b60.mov", fingerprint="b", duration_s=10.0, fps_num=60, fps_den=1, resolve_fps=60.0,
           resolve_frames=600)
B50 = Clip(id="c06", path="/x/b50.mov", fingerprint="d", duration_s=10.0, fps_num=50, fps_den=1, resolve_fps=50.0,
           resolve_frames=500)
CLIPS = {"c01": CLIP, "c05": B60, "c06": B50}


def plan_for(at, ov, **opts):
    cl = cl_with(ov)
    if opts:
        cl.options = cl.options.model_copy(update=opts)
    return cl, build_plan(cl, CLIPS, {"c01": at}, prof=RAW)


def test_integer_multiple_is_frame_exact(at):
    cl, plan = plan_for(at, {"media": "c05", "from_frame": "c05:f0100", "from_word": "c01:w0002", "to_word": "c01:w0005"})
    assert plan.ok, plan.errors
    (o,) = plan.overlays
    assert o.kind == "video" and o.speed == 1.0 and o.audio == "mute"
    assert o.src_start == 100 and o.src_frames == 2 * o.frames  # 60 fps source in a 30 fps timeline
    assert not [w for w in plan.warnings if "ganzzahlig" in w]
    assert "Video ab c05:f0100" in plan_text(cl, plan, CLIPS)


def test_slowmo_doubles_the_appended_source_and_halves_speed(at):
    _, plan = plan_for(at, {"media": "c05", "from_frame": "c05:f0100", "slowmo": True,
                            "from_word": "c01:w0002", "to_word": "c01:w0005"})
    (o,) = plan.overlays
    assert o.speed == 0.5 and o.src_frames == 2 * o.frames  # appended 2N, shown N source frames at 50 %
    _, auto = plan_for(at, {"media": "c05", "from_frame": "c05:f0100", "from_word": "c01:w0002", "to_word": "c01:w0005"},
                       broll_slowmo="auto")
    assert auto.overlays[0].speed == 0.5


def test_non_integer_rate_warns_and_slowmo_impossible(at):
    _, plan = plan_for(at, {"media": "c06", "from_frame": "c06:f0010", "slowmo": True,
                            "from_word": "c01:w0002", "to_word": "c01:w0005"})
    assert plan.ok, plan.errors
    assert any("nicht ganzzahlig" in w for w in plan.warnings)  # 50 → 30
    (o,) = plan.overlays
    assert o.speed == 1.0 and any("Zeitlupe nur" in w for w in plan.warnings)  # 50/30 < 2


def test_short_material_shortens_the_overlay(at):
    _, plan = plan_for(at, {"media": "c05", "from_frame": "c05:f0560", "from_word": "c01:w0002", "to_word": "c01:w0005"})
    (o,) = plan.overlays
    # 40 source frames left → at most 20 timeline frames; snapping already respects that (ends on cuts, no sliver)
    assert o.src_start + o.src_frames <= 600 and 0 < o.frames <= 20


def test_to_frame_limits_and_errors(at):
    _, plan = plan_for(at, {"media": "c05", "from_frame": "c05:f0100", "to_frame": "c05:f0139",
                            "from_word": "c01:w0002", "to_word": "c01:w0005"})
    assert 0 < plan.overlays[0].frames <= 20  # to_frame leaves 40 source frames
    _, bad = plan_for(at, {"media": "c05", "from_frame": "c05:f0700", "from_word": "c01:w0002", "to_word": "c01:w0005"})
    assert any("hinter dem Clip-Ende" in e for e in bad.errors)
