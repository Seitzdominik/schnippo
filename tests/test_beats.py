"""Rest pauses and beats (Phase 8.5 step 2): natural pauses stay, never artificial silence."""
import pytest

from schnippo.cutlist import Cutlist, build_plan
from schnippo.passes import resolve
from schnippo.profiles import make_profile

from test_cutlist import CLIP, at  # noqa: F401  (fixture)

OPT = {"keep_pause_ms": 350, "keep_pause_mid_ms": 250, "tighten_gaps_over_ms": 350, "beat_key_ms": 600, "beat_section_ms": 1000,
       "motion_aware_cuts": False}
ALL = [{"clip": "c01", "from_word": "w0001", "to_word": "w0008"}]


def plan_for(at, items=ALL, beats=()):
    cl = Cutlist(items=items, options=OPT, beats=list(beats))
    return build_plan(cl, {"c01": CLIP}, {"c01": at})


def pause_after_w3(plan):
    """Timeline pause between 'drei.' (ends 2.00 s) and 'Vier' (starts 3.00 s, original gap 1.00 s)."""
    p0, p1 = plan.pieces[0], plan.pieces[1]
    return round((p0.end_frame / 30 - 2.0) + (3.0 - p1.start_frame / 30), 2)


def test_sentence_end_keeps_the_rest_pause_and_a_beat_keeps_more(at):
    assert abs(pause_after_w3(plan_for(at)) - 0.35) <= 0.07
    plan = plan_for(at, beats=[{"after": "c01:w0003", "beat": "key"}])
    assert abs(pause_after_w3(plan) - 0.60) <= 0.07
    (b,) = plan.beats
    assert b["kind"] == "key" and b["target_s"] == 0.6 and abs(b["actual_s"] - 0.6) <= 0.07 and b["orig_s"] == 1.0


def test_original_pause_shorter_than_the_target_stays_uncut(at):
    plan = plan_for(at, beats=[{"after": "c01:w0003", "beat": "section"}, {"after": "c01:w0005"}])
    assert len(plan.pieces) >= 1
    b = {x["word"]: x for x in plan.beats}
    assert b["c01:w0003"]["actual_s"] == pytest.approx(1.0, abs=0.04)  # target 1.0 = the whole original pause, no cut
    assert b["c01:w0005"]["orig_s"] == pytest.approx(0.02, abs=0.01) and b["c01:w0005"]["actual_s"] <= 0.05  # never added


def test_item_end_gets_the_rest_pause_too(at):
    two = [{"clip": "c01", "from_word": "w0001", "to_word": "w0003"}, {"clip": "c01", "from_word": "w0004", "to_word": "w0005"}]
    plan = plan_for(at, two)
    assert plan.pieces[0].end_frame / 30 - 2.0 == pytest.approx(0.27, abs=0.04)  # 350 ms minus 80 ms lead-in
    beat = [{**two[0], "beat": "key"}, two[1]]
    assert plan_for(at, beat).pieces[0].end_frame / 30 - 2.0 == pytest.approx(0.52, abs=0.04)


def test_a_cut_that_saves_little_silence_does_not_happen(at):
    plan = build_plan(Cutlist(items=ALL, options={**OPT, "keep_pause_ms": 800}), {"c01": CLIP}, {"c01": at})
    assert plan.pieces[0].end_frame >= 90  # 1.0 s pause, 0.8 s wanted: 0.2 s saved is no reason for a jump cut


def test_beats_only_from_the_fine_cut_on_and_inherited():
    prof = make_profile("youtube")
    items = [{"clip": "c01", "from_word": "w0001", "to_word": "w0003", "beat": "key"}]
    rough, notes = resolve(Cutlist(**{"pass": "rough", "name": "T", "items": items}), None, prof)
    assert rough.items[0].beat is None and any("beat" in n for n in notes)
    fine, _ = resolve(Cutlist(**{"pass": "fine", "base_cutlist": "x", "beats": [{"after": "c01:w0002"}]}), rough, prof)
    assert fine.beats[0].after == "c01:w0002" and fine.options.beat_key_ms == 800 and fine.options.keep_pause_ms == 350
    br, _ = resolve(Cutlist(**{"pass": "broll", "base_cutlist": "y"}), fine, prof)
    assert br.beats and br.beats[0].beat == "key"


def test_run_out_stops_at_the_next_item_in_the_source(at):
    two = [{"clip": "c01", "from_word": "w0001", "to_word": "w0003", "beat": "section"},
           {"clip": "c01", "from_word": "w0004", "to_word": "w0005"}]
    plan = plan_for(at, two)
    assert plan.ok, plan.errors  # target 1.0 s = the whole original pause; the lead-in of #2 is not used twice
    assert plan.pieces[0].end_frame == plan.pieces[1].start_frame
