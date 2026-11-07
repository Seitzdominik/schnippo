"""Correction loop (Phase 8 step 2): locate, revise operations, diff, adopting manual Resolve edits."""
import pytest

from schnippo.cutlist import Cutlist, build_plan
from schnippo.revise import (apply_ops, diff, find_quote, next_revision_name, parse_timecode, resolve_ref, spoken_words,
                                timeline_changes)

from test_cutlist import CLIP, at  # noqa: F401  (fixture)

FPS = 30.0


def base_cl():
    return Cutlist(timeline_name="T_V2_Fine", items=[
        {"clip": "c01", "from_word": "w0001", "to_word": "w0003", "note": "eins bis drei"},
        {"clip": "c01", "from_word": "w0004", "to_word": "w0005"},
        {"clip": "c01", "from_word": "w0006", "to_word": "w0008"}])


def ctx(at, cl=None):
    cl = cl or base_cl()
    plan = build_plan(cl, {"c01": CLIP}, {"c01": at})
    assert plan.ok, plan.errors
    return cl, plan, spoken_words(plan, {"c01": at}, FPS)


def test_timecodes():
    assert parse_timecode("0:23", 25) == 575 and parse_timecode("1:02.5", 25) == 1562
    assert parse_timecode("00:00:23:12", 25) == 587 and parse_timecode("23s", 25) == 575 and parse_timecode("f40", 25) == 40
    assert parse_timecode("die Firma", 25) is None


def test_locate_item_time_quote(at):
    cl, plan, words = ctx(at)
    loc = resolve_ref("#02", cl, plan, words, FPS)
    assert loc["item"] == 2 and loc["words"] == ("c01:w0004", "c01:w0005") and loc["text"] == "Vier fünf"
    w = words[4]  # "fünf"
    t = resolve_ref(f"f{w['start'] + 1}", cl, plan, words, FPS)
    assert t["words"] == ("c01:w0005", "c01:w0005") and t["sentence"] == ("c01:w0004", "c01:w0007")
    q = resolve_ref("„sechs sieben“", cl, plan, words, FPS)
    assert q["kind"] == "quote" and q["words"] == ("c01:w0006", "c01:w0007") and q["item"] == 3
    assert find_quote(words, "zwei drei")[0][1:] == (1, 2)
    with pytest.raises(LookupError):
        resolve_ref("gibt es nicht im Text", cl, plan, words, FPS)


def test_ops_remove_split_move_insert_and_diff(at):
    cl, plan, words = ctx(at)
    loc = lambda r: resolve_ref(r, cl, plan, words, FPS)
    new, log = apply_ops(cl, [{"op": "remove", "ref": "zwei"},  # quote → exactly that word, item 1 splits
                              {"op": "move", "ref": "#03", "before": "#02"},
                              {"op": "zoom", "ref": "#02", "zoom": 1.25}], loc)
    assert [(i.from_word, i.to_word) for i in new.items] == [("w0001", "w0001"), ("w0003", "w0003"), ("w0006", "w0008"),
                                                             ("w0004", "w0005")]
    assert new.items[3].zoom == 1.25 and any("geteilt" in x for x in log)
    nplan = build_plan(new, {"c01": CLIP}, {"c01": at})
    d = "\n".join(diff(cl, new, plan.total_seconds({"c01": CLIP}), nplan.total_seconds({"c01": CLIP})))
    assert "geändert: #01" in d and "↕ verschoben: alt #03 → neu #03" in d and "jetzt vor c01 w0004" in d and "Dauer" in d
    ins, _ = apply_ops(cl, [{"op": "remove", "ref": "#02"},
                            {"op": "insert", "after": "#03", "clip": "c01", "from_word": "w0004", "to_word": "w0004"}], loc)
    assert [i.from_word for i in ins.items] == ["w0001", "w0006", "w0004"]
    with pytest.raises(KeyError):
        apply_ops(cl, [{"op": "remove", "ref": "#02"}, {"op": "zoom", "ref": "#02", "zoom": 1.1}], loc)


def test_revision_names():
    assert next_revision_name("X_V2_Fine", set()) == "X_V2_Fine_r2"
    assert next_revision_name("X_V2_Fine_r2", {"X_V2_Fine_r2", "X_V2_Fine_r3"}) == "X_V2_Fine_r4"


def test_manual_changes_are_adopted_frame_exactly(at):
    cl, plan, _ = ctx(at)
    p = plan.pieces
    v1 = []
    rec = 0
    # user: removed the second piece, trimmed the end of the last one by 3 frames, appended a foreign clip
    for k, pc in enumerate(p):
        if k == 1:
            continue
        n = pc.frames - (3 if k == len(p) - 1 else 0)
        v1.append({"clip": "c01", "name": "t.mov", "rec": rec, "frames": n, "src_start": pc.start_frame, "fps": FPS, "zoom": 1.0})
        rec += n
    v1.append({"clip": None, "name": "fremd.mov", "rec": rec, "frames": 50, "src_start": 0, "fps": None, "zoom": 1.0})
    res = timeline_changes(cl, plan, {"name": "T_V2_Fine", "v1": v1, "upper": {}}, {"c01": at}, {"c01": CLIP})
    assert res["changed"] and res["status"].count("getrimmt") == 1 and res["status"].count("unbekannt") == 1
    assert len(res["removed"]) == 1 and any("fremd.mov" in u for u in res["unclear"])
    new = res["cutlist"]
    nplan = build_plan(new, {"c01": CLIP}, {"c01": at})
    assert nplan.ok, nplan.errors
    assert [(x.start_frame, x.frames) for x in nplan.pieces] == [(it["src_start"], it["frames"]) for it in v1 if it["clip"]]
