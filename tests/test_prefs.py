import json
import unicodedata

import pytest

from schnippo import prefs
from schnippo.config import load_config
from schnippo.guard import clean_path, material_root


@pytest.fixture
def conf(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHNIPPO_CONFIG", str(tmp_path / "config.toml"))
    for k in ("SCHNIPPO_FORMAT", "SCHNIPPO_STYLE", "SCHNIPPO_LANGUAGE", "SCHNIPPO_SFX_MODE", "SCHNIPPO_PROJECTS_FOLDER"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


def test_fresh_state(conf):
    d = prefs.load()
    assert d["onboarding"] == {"done": False, "version": 0, "later": 0} and d["preferences"] == {}


def test_answers_become_defaults(conf):
    d = prefs.load()
    got, bad = prefs.read_answers({"format": "Interviews", "style": "ausgewogen", "language": "Deutsch", "sfx": "aus", "graphics": "an", "projects_folder": f'"{conf}/"'})
    assert not bad and got == {"format": "youtube", "content_type": "interview", "style": "ruhig-dicht", "language": "de", "sfx": "off", "graphics": True, "projects_folder": str(conf)}
    d["preferences"].update(got)
    prefs.save(d)
    cfg = load_config()
    assert (cfg.format, cfg.style, cfg.sfx_mode, cfg.graphics, cfg.projects_folder) == ("youtube", "ruhig-dicht", "off", True, conf)


def test_unknown_answers_are_reported_not_stored():
    got, bad = prefs.read_answers({"format": "Hochzeiten", "projects_folder": "/gibt/es/nicht"})
    assert got == {} and len(bad) == 2


def test_extension_default_does_not_beat_the_answer_but_a_real_setting_does(conf, monkeypatch):
    d = prefs.load()
    d["preferences"].update({"format": "course", "sfx": "normal"})
    prefs.save(d)
    monkeypatch.setenv("SCHNIPPO_FORMAT", "auto")
    monkeypatch.setenv("SCHNIPPO_SFX_MODE", "off")
    cfg = load_config()
    assert cfg.format == "course" and cfg.sfx_mode == "off"


def test_save_leaves_no_temp_file(conf):
    prefs.save(prefs.load())
    assert [p.name for p in conf.iterdir()] == ["preferences.json"]
    assert json.loads((conf / "preferences.json").read_text())["onboarding"]["done"] is False


@pytest.mark.parametrize("text", ['"{p}"', "'{p}'", "  {p}  ", "{p}/", "file://{u}", "file://{u}/", "„{p}“"])
def test_pasted_paths(tmp_path, text):
    d = tmp_path / "Mein Projekt"
    d.mkdir()
    assert clean_path(text.format(p=d, u=str(d).replace(" ", "%20"))) == d


def test_home_and_shell_escapes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    d = tmp_path / "Mein Projekt"
    d.mkdir()
    assert clean_path("~/Mein Projekt") == d
    assert clean_path(str(d).replace(" ", "\\ ")) == d


def test_either_unicode_form(tmp_path):
    nfd = unicodedata.normalize("NFD", "Küstenprojekt")
    (tmp_path / nfd).mkdir()
    got = clean_path(tmp_path / unicodedata.normalize("NFC", "Küstenprojekt"))
    assert got.is_dir()


def test_material_root_takes_pasted_paths(tmp_path):
    d = tmp_path / "Dreh"
    d.mkdir()
    assert material_root(f'"{d}/"') == d.resolve()
