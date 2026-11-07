import json

from schnippo import migrate
from schnippo.branding import brand_file
from schnippo.guard import EXPORT_DIRNAME, LEGACY_EXPORT_DIRNAME, media_files


def _old(home):
    c = home / ".config" / "resolve-cut"
    c.mkdir(parents=True)
    (c / "preferences.json").write_text(json.dumps({"onboarding": {"done": True}}))
    (c / "brand.json").write_text("{}")
    k = home / "Library" / "Caches" / "resolve-cut" / "mg"
    k.mkdir(parents=True)
    (k / "grafik.mov").write_bytes(b"x")


def test_moves_settings_and_cache_and_old_paths_keep_working(tmp_path):
    _old(tmp_path)
    done = migrate.run(tmp_path)
    assert len(done) == 2
    assert (tmp_path / ".config" / "schnippo" / "preferences.json").exists() and (tmp_path / ".config" / "schnippo" / "brand.json").exists()
    new = tmp_path / "Library" / "Caches" / "schnippo" / "mg" / "grafik.mov"
    old = tmp_path / "Library" / "Caches" / "resolve-cut" / "mg" / "grafik.mov"
    assert new.exists() and old.exists() and (tmp_path / "Library" / "Caches" / "resolve-cut").is_symlink()


def test_runs_once_and_never_overwrites(tmp_path):
    _old(tmp_path)
    migrate.run(tmp_path)
    (tmp_path / ".config" / "schnippo" / "preferences.json").write_text("{\"neu\": 1}")
    assert migrate.run(tmp_path) == []
    assert "neu" in (tmp_path / ".config" / "schnippo" / "preferences.json").read_text()


def test_fresh_machine_does_nothing(tmp_path):
    assert migrate.run(tmp_path) == []


def test_old_export_folder_stays_in_use_and_out_of_the_scan(tmp_path):
    from schnippo.workspace import Workspace
    ws = Workspace.__new__(Workspace)
    ws.cfg = type("C", (), {"export_folder": None})()
    ws.folder = tmp_path
    assert ws.export_dir().name == EXPORT_DIRNAME
    (tmp_path / LEGACY_EXPORT_DIRNAME).mkdir()
    assert ws.export_dir().name == LEGACY_EXPORT_DIRNAME
    (tmp_path / LEGACY_EXPORT_DIRNAME / "a.mp4").write_bytes(b"x")
    assert media_files(tmp_path, True, {".mp4"})[0] == []


def test_missing_brand_file_falls_back(tmp_path):
    p = tmp_path / "icon.png"
    assert brand_file("gibt-es-nicht.png", p) == p and brand_file("gibt-es-nicht.png") is None
