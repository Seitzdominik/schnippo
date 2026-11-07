from pathlib import Path

import pytest

from schnippo.cutlist import Cutlist, build_plan, plan_text
from schnippo.models import AnalyzedTranscript
from schnippo.script import ScriptLine
from schnippo.segments import segment
from schnippo.subtitles import blocks_for_plan, suggest_from_script, write_srt

from test_cutlist import CLIP, FPS, at  # noqa: F401


def plan_for(at, **kw):
    cl = Cutlist(items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0003"},
                        {"clip": "c01", "from_word": "w0004", "to_word": "w0008"}], **kw)
    return cl, build_plan(cl, {"c01": CLIP}, {"c01": at})


def test_blocks_break_at_punctuation_pauses_and_max_words(at):
    cl, plan = plan_for(at, options={"motion_aware_cuts": False})
    blocks = blocks_for_plan(plan.pieces, {"c01": at}, FPS, max_words=4)
    texts = [b.text.replace("\n", " ") for b in blocks]
    assert texts[0] == "Eins zwei drei."  # sentence end breaks
    assert "Vier" in texts[1] and texts[1].split()[0] == "Vier"
    assert all(len(t.split()) <= 4 for t in texts)
    # monotonic, non-overlapping, inside the timeline
    total = sum(p.frames for p in plan.pieces)
    assert all(a.end <= b.start for a, b in zip(blocks, blocks[1:])) and blocks[-1].end <= total
    # first word 'Eins' starts 1.00 s; piece 1 starts at frame 27 → timeline frame 3
    assert blocks[0].start == 30 - plan.pieces[0].start_frame


def test_corrections_apply_to_end_text_and_subtitles_key_is_ignored(at):
    cl, plan = plan_for(at, corrections=[{"word": "c01:w0005", "text": "FÜNF"}], subtitles={"mode": "srt", "max_words": 3})
    assert plan.ok and plan.corrections == {"c01:w0005": "FÜNF"}
    assert any("subtitles" in w and "export_transcript" in w for w in plan.warnings)
    txt = plan_text(cl, plan, {"c01": CLIP})
    assert "c01:w0005 → „FÜNF“" in txt and "FÜNF" in txt.splitlines()[-1]
    _, bad = plan_for(at, corrections=[{"word": "c01:w0099", "text": "x"}])
    assert any("w0099 unbekannt" in e for e in bad.errors)


def test_two_lines_and_srt_format(at, tmp_path):
    cl, plan = plan_for(at, options={"motion_aware_cuts": False})
    blocks = blocks_for_plan(plan.pieces, {"c01": at}, FPS, max_words=4, max_line_chars=8)
    assert any("\n" in b.text for b in blocks)
    f = write_srt(blocks, FPS, tmp_path / "x.srt")
    txt = f.read_text(encoding="utf-8")
    assert txt.startswith("1\n00:00:00,100 --> ") and "\n\n2\n" in txt


def test_script_suggestions_one_to_one(cfg, at):
    segs = segment(at, cfg, 12.0)
    segs[0].script = [("L01", 0.9)]
    lines = [ScriptLine(id="L01", section="", text="Eins zwo drei.")]
    sug = suggest_from_script(segs, at, lines)
    assert sug == [("c01:w0002", "zwei", "zwo", "L01")]


def test_set_word_text_persists(cfg, tmp_path, monkeypatch):
    from test_frames import FakeProvider  # noqa: F401
    import subprocess

    from schnippo import workspace as wsmod
    from schnippo.workspace import Workspace
    folder = tmp_path / "f"
    folder.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=25:d=3", "-f", "lavfi", "-i",
                    "sine=d=3", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-shortest",
                    str(folder / "t.mp4")], check=True)
    monkeypatch.setattr(wsmod, "get_provider", lambda n, c: FakeProvider(c))
    ws = Workspace(cfg)
    ws.ingest(folder)
    ws.transcribe("all")
    assert "„zwei.“ → „Zwei.“" in ws.set_word_text("c01:w0002", "Zwei.")
    assert Workspace(cfg).corrections == {"c01:w0002": "Zwei."}
    with pytest.raises(KeyError):
        ws.set_word_text("c01:w0099", "x")
    cl = Cutlist(items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0004"}], subtitles={"mode": "srt"})
    plan, _, _ = ws.plan(cl)
    assert plan.corrections == {"c01:w0002": "Zwei."}
    cl = Cutlist(items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0004"}])
    res = ws.export_transcript(cl=cl)
    out = folder / "schnippo-export"
    assert Path(res["srt"]).parent == out and Path(res["txt"]).exists()
    assert "Zwei." in Path(res["srt"]).read_text(encoding="utf-8") and "Zwei." in Path(res["txt"]).read_text(encoding="utf-8")
    assert "chapters_file" not in res  # reel profile: no chapters


def test_review_card_and_answers(cfg, tmp_path, monkeypatch):
    from test_frames import FakeProvider  # noqa: F401
    import subprocess

    from schnippo import workspace as wsmod
    from schnippo.workspace import Workspace
    folder = tmp_path / "r"
    folder.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=180x320:r=25:d=3", "-f", "lavfi", "-i",
                    "sine=d=3", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-shortest",
                    str(folder / "t.mp4")], check=True)
    monkeypatch.setattr(wsmod, "get_provider", lambda n, c: FakeProvider(c))
    ws = Workspace(cfg)
    ws.ingest(folder)
    ws.transcribe("all")
    ws.set_word_text("c01:w0002", "Zwei.")
    data = ws.review("T_V1_Rough", [{"kind": "grenzfall", "question": "Satz behalten?", "words": "c01:w0001-w0002",
                                     "recommendation": "Behalten"}, {"kind": "widerspruch", "question": "Welche Zahl?"}])
    assert data["view"] == "review" and len(data["decisions"]) == 2
    d1 = data["decisions"][0]
    assert d1["id"] == "D1" and "Zwei." in d1["text"] and d1["image"].startswith("data:image/jpeg;base64,")
    assert d1["kind_label"] == "Grenzfall" and data["decisions"][1]["kind_label"] == "Inhaltlicher Widerspruch"
    txt = ws.submit_review(data["review_id"], [{"id": "D1", "answer": "drop"}, {"id": "D2", "answer": "any"}])
    assert "D1 (Grenzfall): Satz behalten? → raus" in txt and "D2" in txt and "egal" in txt
    assert Workspace(cfg).reviews[data["review_id"]]["answers"] == {"D1": "drop", "D2": "any"}
