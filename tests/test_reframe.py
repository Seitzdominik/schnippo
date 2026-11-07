from types import SimpleNamespace as NS

import numpy as np

from schnippo import reframe as rf
from schnippo import reels
from schnippo.cutlist import CutItem, Cutlist, Piece, Plan, PlacedOverlay, Reframe

UHD = NS(width=3840, height=2160, rotation=0, resolve_fps=25.0, fps=25.0)
HD = NS(width=1920, height=1080, rotation=0, resolve_fps=25.0, fps=25.0)
W, H = 1080, 1920


def test_measured_units():
    assert abs(rf.scale(UHD, W, H) - 0.889) < 0.001 and abs(rf.scale(HD, W, H) - 1.778) < 0.001
    assert abs(rf.pan_unit(UHD, W, H) - 3.16) < 0.01 and abs(rf.pan_unit(HD, W, H) - 3.16) < 0.01


def test_to_out_matches_the_spike():
    """Measured: cross at the centre, Pan 100 → +316 px, Tilt 100 at zoom 1.5 → −100 px."""
    pc = NS(zoom=1.0, pan=0.0, tilt=0.0)
    assert rf.to_out(1920, 1080, UHD, pc, W, H) == (540, 960)
    x, _ = rf.to_out(1920, 1080, UHD, NS(zoom=1.5, pan=100.0, tilt=0.0), W, H)
    assert abs(x - 856) < 1
    _, y = rf.to_out(1920, 1080, UHD, NS(zoom=1.5, pan=0.0, tilt=100.0), W, H)
    assert y == 860


def _plan(boxes, frames=250, zoom=1.0, words=None):
    """faces: boxes per frame, analysis 270×152."""
    words = words or [NS(id=f"w{k:04d}", start_s=k * 1.0, end_s=k * 1.0 + 0.7, text=f"Wort{k}.", kind="word") for k in range(1, 10)]
    pc = Piece(item=1, clip="c01", start_s=0, end_s=frames / 25, start_frame=0, end_frame=frames, text="x", word_ids=[w.id for w in words], zoom=zoom)
    plan = Plan(pieces=[pc])
    cl = Cutlist(reframe=Reframe(), items=[CutItem(clip="c01", from_word="w0001", to_word="w0009")])
    return cl, plan, {"c01": UHD}, {"c01": NS(entries=words)}, {"c01": (boxes, (270, 152))}


def test_head_is_centred_and_inside():
    box = (150, 20, 40, 40)
    cl, plan, clips, an, faces = _plan([box] * 250)
    rf.apply(cl, plan, clips, an, faces)
    pc = plan.pieces[0]
    assert pc.fill and len(plan.pieces) == 1
    head = rf.head_box(box, (270, 152), UHD)
    ax, _ = rf.to_out(head[0], head[1], UHD, pc, W, H)
    bx, _ = rf.to_out(head[0] + head[2], head[1] + head[3], UHD, pc, W, H)
    assert abs((ax + bx) / 2 - 540) < 2 and plan.reframe["report"]["out"] == 0


def test_head_at_the_edge_of_the_picture_is_clamped_no_black():
    box = (250, 20, 18, 18)
    cl, plan, clips, an, faces = _plan([box] * 250)
    rf.apply(cl, plan, clips, an, faces)
    room = (3840 * rf.scale(UHD, W, H) - W) / 2
    assert abs(plan.pieces[0].pan) * rf.pan_unit(UHD, W, H) <= room + 0.1


def test_moving_head_splits_at_a_word_gap():
    boxes = [(30, 20, 40, 40)] * 96 + [(200, 20, 40, 40)] * 154
    cl, plan, clips, an, faces = _plan(boxes)
    rf.apply(cl, plan, clips, an, faces)
    assert len(plan.pieces) == 2 and plan.reframe["splits"] == 1
    a, b = plan.pieces
    assert a.end_frame == b.start_frame and a.pan != b.pan and plan.reframe["report"]["out"] == 0
    assert sum(p.frames for p in plan.pieces) == 250 and set(a.word_ids) | set(b.word_ids) == {f"w{k:04d}" for k in range(1, 10)}


def test_punch_in_brings_eyes_to_the_upper_third():
    box = (120, 70, 40, 40)  # low in the picture
    cl, plan, clips, an, faces = _plan([box] * 250, zoom=1.2)
    rf.apply(cl, plan, clips, an, faces)
    pc = plan.pieces[0]
    assert pc.tilt > 0 and abs(pc.tilt) <= 0.2 * H / 2 + 0.1


def test_hd_warns_with_effective_resolution():
    cl, plan, clips, an, faces = _plan([(120, 20, 40, 40)] * 250)
    clips["c01"] = HD
    rf.apply(cl, plan, clips, an, faces)
    assert any("hochskaliert" in w and "608×1080" in w for w in plan.warnings) or any("608" in w for w in plan.warnings)


def test_uhd_punch_is_limited_by_source():
    assert abs(rf.punch_limit(UHD, W, H) - 1.406) < 0.01 and rf.punch_limit(HD, W, H) == 1.12


def test_overlay_crop_follows_focus_or_picture():
    cl = Cutlist(reframe=Reframe(), overlays=[{"media": "c02", "from_word": "c01:w0001", "to_word": "c01:w0002", "focus_x": 0.8}])
    plan = Plan(overlays=[PlacedOverlay(index=1, media="c02", track=2, tl_start=0, tl_end=50, words=("a", "b"), fit="fill", focus="center", motion="none", kind="video", src_start=0, src_frames=50)])
    rf.place_overlays(cl, plan, {"c02": UHD})
    o = plan.overlays[0]
    assert o.fill_video and o.pan < 0 and o.focus_x == 0.8


def test_busiest_x_finds_motion_and_detail():
    a = np.zeros((90, 320), np.uint8)
    b = a.copy()
    b[:, 240:280] = 200
    assert 0.65 < rf.busiest_x([a, b, a]) < 0.95
    c = np.zeros((90, 320), np.uint8)
    c[:, 40:90:4] = 255
    assert rf.busiest_x([c, c, c]) < 0.35


def _long():
    return Cutlist(items=[CutItem(clip="c01", from_word="w0010", to_word="w0020", note="a"), CutItem(clip="c01", from_word="w0030", to_word="w0040", note="b"),
                          CutItem(clip="c01", from_word="w0050", to_word="w0060", note="c")])


def test_passage_with_small_cut_and_cold_open():
    spans, notes = reels.spans_between(_long(), "c01:w0015", "c01:w0055", ["c01:w0033-w0035"], {"from_word": "c01:w0052", "to_word": "c01:w0054"})
    assert spans[0] == ("c01", 52, 54, "Cold Open")
    assert ("c01", 15, 20, "a") in spans and ("c01", 30, 32, "b") in spans and ("c01", 36, 40, "b") in spans and ("c01", 50, 51, "c") in spans and ("c01", 55, 55, "c") in spans
    assert notes


def test_one_recording_keeps_its_order_when_the_long_version_moved_a_sentence():
    cl = Cutlist(items=[CutItem(clip="c01", from_word="w0050", to_word="w0060", note="Cold Open"), CutItem(clip="c01", from_word="w0010", to_word="w0049", note="Geschichte")])
    spans, _ = reels.spans_between(cl, "c01:w0020", "c01:w0055", [], None)
    assert spans == [("c01", 20, 49, "Geschichte"), ("c01", 50, 55, "Cold Open")]


def test_cold_open_from_elsewhere_is_refused():
    import pytest
    with pytest.raises(ValueError, match="dieselben|derselben"):
        reels.spans_between(_long(), "c01:w0015", "c01:w0035", [], {"from_word": "c01:w0055", "to_word": "c01:w0056"})


def test_word_outside_the_long_version_is_refused():
    import pytest
    with pytest.raises(ValueError, match="nicht in der langen Fassung"):
        reels.spans_between(_long(), "c01:w0025", "c01:w0035", [], None)


def _words():
    out = []
    for k, (t, s) in enumerate((("Das", 0), ("ist", 0), ("gut.", 0), ("Wie", 1), ("war", 1), ("es?", 1), ("Drei", 0), ("Tipps", 0), ("habe", 0), ("ich.", 0)), 1):
        out.append({"ref": f"c01:w{k:04d}", "text": t, "start": k * 10, "end": k * 10 + 8, "item": 1, "s": s})
    return out


def test_sentences_carry_signals_and_blocks_skip_the_question():
    w = _words()
    spk = {x["ref"]: x["s"] for x in w}
    sents = reels.sentences(w, spk, {}, {}, 25.0, [{"word": "c01:w0010", "kind": "section"}])
    assert [s["speaker"] for s in sents] == [0, 1, 0]
    assert "Bezug?" in sents[0]["tags"] and "Frage" in sents[1]["tags"] and "Zahl" in sents[2]["tags"] and "Liste" in sents[2]["tags"] and sents[2]["beat"] == "section"
    b = reels.blocks(sents, 0.1, 60)
    assert len(b) == 2 and b[1]["first"].startswith("Drei")


def test_slug():
    assert reels.slug("Mut zur Lücke: Über Größe!") == "mut-zur-luecke-ueber-groesse"
