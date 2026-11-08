from pathlib import Path

import pytest

from schnippo.config import Config
from schnippo.formats import content_of, detect, refine
from schnippo.models import Clip
from schnippo.prefs import read_answers
from schnippo.projects import brief_content_type, brief_format
from schnippo.workspace import Workspace


def clip(w, h):
    return Clip(id="c01", path="/x.mov", fingerprint="f", duration_s=223, fps_num=30, fps_den=1, width=w, height=h, rotation=0)


def test_two_speakers_are_an_interview_in_every_format():
    assert content_of("reel", 2) == "interview" and content_of("course", 2) == "interview"
    assert content_of("reel", 1) == "talking_head" and content_of("course", 1) == "course" and content_of("commercial", 0) == "commercial"


def test_refine_reports_the_content_type_for_portrait_and_landscape():
    args = dict(aroll_clips=1, broll_clips=0, longest_take_speech_s=60, aroll_speech_s=60, text="")
    assert refine(detect([clip(1080, 1920)], speech_s=60, raw_s=200), speakers=2, **args).content_type == "interview"
    d = refine(detect([clip(1920, 1080)], speech_s=900, raw_s=1000), speakers=2, **{**args, "longest_take_speech_s": 900, "aroll_speech_s": 900})
    assert d.format == "youtube" and d.content_type == "interview"


def brief(tmp_path: Path, text: str) -> Path:
    (tmp_path / "brief.md").write_text(text, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("text,fmt,ct", [("Format: Reel\nArt des Inhalts: Interview\n", "reel", "interview"), ("Format: Interview\n", "youtube", "interview"),
                                         ("Format: Kurs\n", "course", "course"), ("Art: Talking Head\n", None, "talking_head"), ("Ziel: mehr Kunden\n", None, None)])
def test_brief_names_format_and_content_separately(tmp_path, text, fmt, ct):
    root = brief(tmp_path, text)
    assert brief_format(root) == fmt and brief_content_type(root) == ct


def workspace(tmp_path) -> Workspace:
    ws = Workspace(Config(gladia_api_key="k", cache_dir=tmp_path / "cache"))
    ws.folder = tmp_path
    return ws


def test_precedence_chat_brief_preference(tmp_path):
    ws = workspace(tmp_path)
    assert ws.effective_content_type() == ("talking_head", "Standard")
    ws.cfg.content_type = "course"
    assert ws.effective_content_type() == ("course", "Vorliebe")
    brief(tmp_path, "Art: Interview\n")
    assert ws.effective_content_type() == ("interview", "aus dem Brief")
    ws.content_choice = "commercial"
    assert ws.effective_content_type() == ("commercial", "gewählt")


def test_format_precedence_chat_brief_preference(tmp_path):
    ws = workspace(tmp_path)
    ws.cfg.format = "youtube"
    assert ws.effective_format() == ("youtube", "Konfiguration")
    brief(tmp_path, "Format: Kurs\n")
    assert ws.effective_format() == ("course", "aus dem Brief")
    ws.format_choice = "reel"
    assert ws.effective_format() == ("reel", "gewählt")


def test_set_content_type_takes_friendly_words_and_auto(tmp_path):
    ws = workspace(tmp_path)
    ws._save = lambda: None
    assert ws.set_content_type("interview") == "interview" and ws.content_choice == "interview"
    assert ws.set_content_type("kurs") == "course"
    ws.set_content_type("auto")
    assert ws.content_choice is None
    with pytest.raises(ValueError):
        ws.set_content_type("doku")


def test_onboarding_answer_interview_sets_the_content_type():
    out, bad = read_answers({"format": "Interviews"})
    assert out == {"format": "youtube", "content_type": "interview"} and not bad
