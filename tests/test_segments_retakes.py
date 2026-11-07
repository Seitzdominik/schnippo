import pytest

from schnippo import retakes
from schnippo.analysis import analyze
from schnippo.script import load_script, match
from schnippo.segments import segment

from conftest import make_acoustic, make_raw
import synthetic_take


def test_segment_boundaries_and_flags(cfg):
    spec = [("Hallo", 0.5, 0.8), ("Welt.", 0.85, 1.2), ("Das", 1.3, 1.5), ("ist", 1.55, 1.7), ("ein", 2.6, 2.8),
            ("Test", 2.85, 3.1), ("und", 3.15, 3.3)]
    raw = make_raw(spec)
    raw.tokens[3].confidence = 0.0
    at = analyze("c01", raw, cfg, acoustic=make_acoustic(6.0, [(0.5, 3.3)]), clip_duration_s=6.0)
    segs = segment(at, cfg, 6.0)
    assert [(s.id, s.from_word, s.to_word) for s in segs] == [
        ("s001", "w0001", "w0002"), ("s002", "w0003", "w0004"), ("s003", "w0005", "w0007")]
    assert "mumbled?" in segs[1].flags
    assert "aborted" in segs[2].flags and "aborted" not in segs[0].flags  # no punctuation + end of clip
    assert segs[2].pause_before_s == pytest.approx(0.9)


def test_take_segmentation_is_stable(cfg):
    segs, _ = synthetic_take.segments(cfg)
    assert len(segs) == 36
    assert segs[0].text.startswith("Heute backen") and segs[-1].text.endswith("geworden ist.")


def test_retake_candidates_against_ground_truth(cfg):
    segs, _ = synthetic_take.segments(cfg)
    edges, groups = retakes.find(segs, window_s=90)
    ids = [f"s{n:03d}" for n in synthetic_take.RETAKES]
    by_id = {s.id: s for s in segs}
    gt = [{"a": [f"w{by_id[ids[0]].word_range()[0]:04d}"] * 2, "b": [f"w{by_id[o].word_range()[0]:04d}"] * 2} for o in ids[1:]]
    m = retakes.evaluate(segs, edges, groups, gt)
    assert m["relations"] == 3 and m["recall_group"] == 1.0 and m["precision_edge"] >= 0.8


def test_script_md_txt_docx_and_matching(tmp_path):
    md = tmp_path / "s.md"
    md.write_text("# Hook\nAb morgen gehe ich früh ins Bett. Definitiv!\n\n## Plan\n- 90 Tage, zwei Phasen.\n", encoding="utf-8")
    lines = load_script(md)
    assert [(l.id, l.section, l.text) for l in lines] == [
        ("L01", "Hook", "Ab morgen gehe ich früh ins Bett."), ("L02", "Hook", "Definitiv!"), ("L03", "Plan", "90 Tage, zwei Phasen.")]
    txt = tmp_path / "s.txt"
    txt.write_text("HOOK\nAb morgen gehe ich früh ins Bett.\nPlan:\nZwei Phasen.\n", encoding="utf-8")
    assert [(l.section, l.text) for l in load_script(txt)] == [("HOOK", "Ab morgen gehe ich früh ins Bett."), ("Plan", "Zwei Phasen.")]
    import docx
    d = docx.Document()
    d.add_heading("Intro", level=1)
    d.add_paragraph("Ab morgen gehe ich früh ins Bett. Das sage ich mir seit einem halben Jahr.")
    d.save(tmp_path / "s.docx")
    dl = load_script(tmp_path / "s.docx")
    assert [(l.id, l.section) for l in dl] == [("L01", "Intro"), ("L02", "Intro")]
    m = match("Das Ganze sage ich mir seit mindestens einem halben Jahr", dl)
    assert m[0][0] == "L02" and m[0][1] > 0.7


def test_script_edges_join_paraphrases(cfg):
    segs, _ = synthetic_take.segments(cfg)
    s = {x.id: x for x in segs}
    s["s031"].script = [("L20", 0.8)]
    s["s033"].script = [("L20", 0.75)]
    edges, groups = retakes.find(segs)
    assert any({e.a, e.b} == {"s031", "s033"} and e.why == "script" for e in edges)
