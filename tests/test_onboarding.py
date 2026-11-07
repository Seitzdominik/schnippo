import datetime

import pytest

from schnippo import onboarding as onb
from schnippo import prefs, projects


def state(done=False, later=0, version=0):
    return {"onboarding": {"done": done, "version": version, "later": later}, "preferences": {}}


def test_first_call_offers_once_per_session():
    s = state()
    assert "Erster Start" in onb.hint(s, "list_clips", True)[0]
    assert onb.hint(s, "list_clips", False)[0] is None
    assert onb.hint(s, "onboarding", True)[0] is None
    assert "Erster Start" in onb.instruction(s)


def test_later_reminds_once_at_the_next_job():
    s = state()
    onb.later(s)
    assert onb.instruction(s) == ""
    assert onb.hint(s, "list_clips", True)[0] is None
    note, changed = onb.hint(s, "ingest_folder", False)
    assert "einmal" in note and changed
    assert onb.hint(s, "ingest_folder", True)[0] is None


def test_done_says_nothing_until_there_is_news(monkeypatch):
    s = state(done=True, version=prefs.VERSION)
    assert onb.hint(s, "list_clips", True) == (None, False)
    monkeypatch.setattr(prefs, "VERSION", 2)
    monkeypatch.setattr(prefs, "NEWS", {2: "Reels aus dem langen Video."})
    note, changed = onb.hint(s, "list_clips", True)
    assert "Reels" in note and changed and s["onboarding"]["version"] == 2
    assert onb.hint(s, "list_clips", True) == (None, False)


def test_finish_and_repeat():
    s = state()
    assert "Spickzettel" in onb.finish(s) and s["onboarding"]["done"]
    assert "Hallo" in onb.repeat(s) and s["onboarding"]["done"]
    t = state(later=2)
    onb.repeat(t)
    assert t["onboarding"]["later"] == 0


@pytest.mark.parametrize("text", [onb.welcome(), onb.questions({}), onb.tips(), onb.later(state()), onb.setup([]), onb.test_question()])
def test_messages_stay_short(text):
    visible = text.split("[Für Claude")[0].strip()
    assert len(visible.splitlines()) <= 7


def test_cheat_sheet_uses_the_name_with_a_projects_folder():
    assert "der Name reicht" in onb.cheat_sheet("/x") and "den Ordner" in onb.cheat_sheet() and "⌥" in onb.cheat_sheet()


@pytest.mark.parametrize("name,role", [("A-Roll", "aroll"), ("ARoll", "aroll"), ("a_roll", "aroll"), ("Interview", "aroll"), ("B-Roll", "broll"), ("BRoll", "broll"), ("Footage", "broll"),
                                       ("Bilder", "images"), ("Images", "images"), ("Skript", "script"), ("Script", "script"), ("Urlaub", None)])
def test_folder_names(name, role):
    assert projects.role_of_folder(name) == role


def test_create_project(tmp_path):
    p, existed = projects.create("Kunde Thema", tmp_path, datetime.date(2026, 11, 6))
    assert p.name == "2026-11-06_Kunde_Thema" and not existed
    assert {d.name for d in p.iterdir()} == {"A-Roll", "B-Roll", "Bilder", "Skript", "glossar.txt", "brief.md"}
    (p / "glossar.txt").write_text("MOC AG\n")
    _, again = projects.create("Kunde Thema", tmp_path, datetime.date(2026, 11, 6))
    assert again and (p / "glossar.txt").read_text() == "MOC AG\n"
    assert projects.has_structure(p)


def test_project_name_cannot_leave_the_folder(tmp_path):
    p, _ = projects.create("../../böse", tmp_path, datetime.date(2026, 11, 6))
    assert p.parent == tmp_path


def test_empty_brief_says_nothing_filled_brief_speaks(tmp_path):
    p, _ = projects.create("X", tmp_path)
    assert projects.brief_text(p) is None
    (p / "brief.md").write_text(projects.BRIEF.replace("Gewünschte Länge:", "Gewünschte Länge: 45 s"))
    assert projects.brief_text(p) == "Gewünschte Länge: 45 s"


def test_find_by_name(tmp_path):
    for n in ("2026-11-06_Segelwerk_Interview", "2026-10-01_Bergwerk_Kurs", "2026-09-02_Kunde_A", "2026-09-03_Kunde_B"):
        (tmp_path / n).mkdir()
    assert projects.find("segelwerk", tmp_path).name.endswith("Segelwerk_Interview")
    assert projects.find("Bergwerg", tmp_path).name.endswith("Bergwerk_Kurs")
    with pytest.raises(LookupError, match="Mehrere"):
        projects.find("Kunde", tmp_path)
    with pytest.raises(FileNotFoundError):
        projects.find("Hochzeit", tmp_path)


def test_scripts_are_found_only_in_their_folder(tmp_path):
    p, _ = projects.create("X", tmp_path)
    (p / "Skript" / "text.docx").write_bytes(b"x")
    (p / "Skript" / "~$text.docx").write_bytes(b"x")
    (p / "notiz.txt").write_text("x")
    assert [f.name for f in projects.script_files(p)] == ["text.docx"]


def test_role_of_file(tmp_path):
    assert projects.role_of_file(tmp_path / "B-Roll" / "a.mp4", tmp_path) == "broll"
    assert projects.role_of_file(tmp_path / "A-Roll" / "Anna" / "a.mp4", tmp_path) == "aroll"
    assert projects.role_of_file(tmp_path / "a.mp4", tmp_path) is None


def test_contradictions_between_folder_and_content(tmp_path):
    from types import SimpleNamespace as NS

    import numpy as np

    from schnippo.workspace import Workspace
    ws = Workspace.__new__(Workspace)
    ws.folder, ws.roles = tmp_path, {}
    ws.clips = {"c01": NS(id="c01", path=str(tmp_path / "B-Roll" / "a.mp4"), audio_channels=2), "c02": NS(id="c02", path=str(tmp_path / "A-Roll" / "b.mp4"), audio_channels=0),
                "c03": NS(id="c03", path=str(tmp_path / "B-Roll" / "c.mp4"), audio_channels=2)}
    ws.acoustic = lambda c: NS(voicing=np.ones(10) if c.id == "c01" else np.zeros(10))
    notes = ws.role_notes()
    assert len(notes) == 2 and "c01 liegt in B-Roll" in notes[1] + notes[0] and any("c02" in n and "keinen Ton" in n for n in notes)
    assert ws.transcribe_ids() == ["c02"]
    ws.roles["c01"] = "aroll"
    assert ws.transcribe_ids() == ["c01", "c02"]


def test_brief_names_the_format(tmp_path):
    p, _ = projects.create("X", tmp_path)
    assert projects.brief_format(p) is None
    (p / "brief.md").write_text(projects.BRIEF.replace("Format (Reel, YouTube, Kurs, Interview, Werbung):", "Format (Reel, YouTube, Kurs, Interview, Werbung): Reel"))
    assert projects.brief_format(p) == "reel"
    (p / "brief.md").write_text("Format: Hochzeit\n")
    assert projects.brief_format(p) is None
