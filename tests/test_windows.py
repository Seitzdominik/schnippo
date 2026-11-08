"""Windows behaviour: pure rules run everywhere with the platform switched by hand, what needs real Windows behaviour runs on the Windows runner only."""
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from schnippo import guard, platforms
from schnippo.resolve_bridge import PathKeyed

on_windows = pytest.mark.skipif(sys.platform != "win32", reason="nur unter Windows")


@pytest.fixture
def win(monkeypatch):
    monkeypatch.setattr(platforms, "is_windows", lambda: True)


# ---------- pasted paths ----------
@pytest.mark.parametrize("text,want", [
    (r'"C:\Users\Max\Filme\Mein Projekt"', r"C:\Users\Max\Filme\Mein Projekt"),
    ("  „C:\\Projekte\\Bäckerei\\“ ", r"C:\Projekte\Bäckerei"),
    ("C:\\", "C:\\"),
    ("D:", "D:\\"),
    (r"\\server\share\Film", r"\\server\share\Film"),
    ("file:///C:/Daten/Max/Mein%20Film/", r"C:\Daten\Max\Mein Film"),
    ("file://server/share/Film", r"\\server\share\Film"),
    ("file://C:/Daten/Mein%20Film", r"C:\Daten\Mein Film"),
    ("C:/Projekte/Film/", "C:/Projekte/Film"),
])
def test_pasted_windows_paths(text, want):
    assert guard.clean_text(text, windows=True) == want


def test_environment_variables_in_a_windows_path(monkeypatch):
    monkeypatch.setenv("DREHS", r"E:\Drehs")
    assert guard.clean_text(r"%DREHS%\Film", windows=True) == r"E:\Drehs\Film"


def test_shell_escapes_stay_a_mac_thing():
    assert guard.clean_text(r"/Volumes/Name\ Film/", windows=False) == "/Volumes/Name Film"
    assert guard.clean_text(r"C:\Mein Film", windows=True) == r"C:\Mein Film"


# ---------- long paths and names ----------
def test_extended_prefix_for_drives_and_shares():
    assert platforms.extended(r"C:\a\b") in (r"\\?\C:\a\b", "\\\\?\\" + os.path.normpath(r"C:\a\b"))
    assert platforms.plain(r"\\?\C:\a\b") == r"C:\a\b"
    assert platforms.plain(r"\\?\UNC\server\share\a") == r"\\server\share\a"
    assert platforms.plain("/Volumes/X") == "/Volumes/X"


@pytest.mark.parametrize("name,want", [('Reel: "Titel"?', "Reel- -Titel--"), ("ok_name", "ok_name"), ("CON", "_CON"), ("punkt.", "punkt"), ("a/b\\c", "a-b-c")])
def test_safe_filename(name, want):
    assert platforms.safe_filename(name) == want


def test_processes_get_no_console_utf8_and_long_paths(win, monkeypatch):
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    long_path = "C:\\" + "x" * 250 + "\\take.mov"
    cmd, kw = platforms._prepare(["ffmpeg", "-i", long_path, "-vf", "scale=1:1"], {"text": True})
    assert kw["creationflags"] == 0x08000000 and kw["encoding"] == "utf-8"
    assert cmd[2].startswith("\\\\?\\C:\\") and cmd[0] == "ffmpeg" and cmd[4] == "scale=1:1"


def test_mac_processes_are_left_alone(monkeypatch):
    monkeypatch.setattr(platforms, "is_windows", lambda: False)
    cmd, kw = platforms._prepare(["ffmpeg", "/x"], {})
    assert cmd == ["ffmpeg", "/x"] and kw == {}


# ---------- folders ----------
def test_config_and_cache_folders(win, monkeypatch):
    monkeypatch.setenv("APPDATA", str(Path("/w/Roaming")))
    monkeypatch.setenv("LOCALAPPDATA", str(Path("/w/Local")))
    assert platforms.config_dir() == Path("/w/Roaming") / "schnippo"
    assert platforms.cache_dir() == Path("/w/Local") / "schnippo" / "Cache"


def test_migration_is_off_on_windows(win, tmp_path):
    from schnippo import migrate
    (tmp_path / ".config" / "resolve-cut").mkdir(parents=True)
    assert migrate.run(tmp_path) == []


# ---------- Resolve ----------
def test_resolve_paths_follow_the_environment(monkeypatch):
    monkeypatch.setenv("RESOLVE_SCRIPT_API", str(Path("/a")))
    monkeypatch.setenv("RESOLVE_SCRIPT_LIB", str(Path("/b/fusionscript.dll")))
    assert platforms.resolve_paths() == (str(Path("/a") / "Modules"), str(Path("/b/fusionscript.dll")))


def test_windows_default_paths(win, monkeypatch):
    monkeypatch.delenv("RESOLVE_SCRIPT_API", raising=False)
    monkeypatch.delenv("RESOLVE_SCRIPT_LIB", raising=False)
    monkeypatch.setenv("PROGRAMDATA", str(Path("/pd")))
    monkeypatch.setenv("ProgramFiles", str(Path("/pf")))
    monkeypatch.delenv("ProgramW6432", raising=False)
    monkeypatch.setattr(platforms, "_registry_install_dirs", lambda: [])
    mod, lib = platforms.resolve_paths()
    assert mod == str(Path("/pd/Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting/Modules"))
    assert lib == str(Path("/pf/Blackmagic Design/DaVinci Resolve/fusionscript.dll"))


def test_an_install_elsewhere_is_found_through_the_registry(win, monkeypatch, tmp_path):
    (tmp_path / "fusionscript.dll").write_text("x")
    monkeypatch.delenv("RESOLVE_SCRIPT_LIB", raising=False)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "leer"))
    monkeypatch.delenv("ProgramW6432", raising=False)
    monkeypatch.setattr(platforms, "_registry_install_dirs", lambda: [tmp_path])
    assert platforms._windows_lib() == str(tmp_path / "fusionscript.dll")


def test_registry_reading(monkeypatch, tmp_path):
    class Key:
        def __init__(self, name):
            self.name = name

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    values = {"a": {"DisplayName": "Anderes", "InstallLocation": "/x"}, "b": {"DisplayName": "DaVinci Resolve Studio", "InstallLocation": str(tmp_path)}}
    fake = NS(HKEY_LOCAL_MACHINE=1, OpenKey=lambda root, name: Key(name.rsplit("\\", 1)[-1]), QueryInfoKey=lambda k: (2,), EnumKey=lambda k, i: "ab"[i],
              QueryValueEx=lambda k, v: (values[k.name][v], 1))
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert platforms._registry_install_dirs() == [tmp_path]


@pytest.mark.parametrize("windows,names,want", [(True, ["explorer.exe", "Resolve.exe"], True), (True, ["python.exe"], False), (False, ["Finder", "Resolve"], True), (False, ["Resolve.exe"], False)])
def test_resolve_process_by_name(monkeypatch, windows, names, want):
    import psutil
    monkeypatch.setattr(platforms, "is_windows", lambda: windows)
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [NS(info={"name": n}) for n in names])
    assert platforms.resolve_running() is want


def test_media_pool_lookup_is_case_insensitive_where_the_system_is():
    d = PathKeyed([("/Film/Take.mov", 1)])
    assert d.get("/Film/Take.mov") == 1 and "/Film/Take.mov" in d
    if sys.platform == "win32":
        assert PathKeyed([(r"C:\Film\Take.mov", 1)]).get(r"c:\film\TAKE.MOV") == 1


# ---------- locked files ----------
def test_a_locked_file_is_retried(win):
    calls, sleeps = [], []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(13, "offen")
        return "ok"
    assert platforms.retry_locked(fn, "Datei", sleep=sleeps.append) == "ok"
    assert len(calls) == 3 and sleeps == [0.5, 1.0]


def test_a_file_that_stays_locked_gets_a_plain_message(win):
    def fn():
        raise PermissionError(13, "offen")
    with pytest.raises(platforms.FileLocked, match="noch geöffnet.*Resolve oder im Player"):
        platforms.retry_locked(fn, "„x.mov“", tries=2, sleep=lambda s: None)


def test_sharing_violation_counts_as_locked(win):
    e = OSError("belegt")
    e.winerror = 32
    assert platforms._locked(e)
    other = OSError("voll")
    other.winerror = 112
    assert not platforms._locked(other)


def test_on_the_mac_a_denied_file_is_not_waited_for(monkeypatch):
    monkeypatch.setattr(platforms, "is_windows", lambda: False)

    def fn():
        raise PermissionError(13, "nein")
    with pytest.raises(PermissionError):
        platforms.retry_locked(fn, "x", sleep=lambda s: pytest.fail("kein Warten"))


def test_texts_from_old_editors_still_read(tmp_path):
    f = tmp_path / "brief.md"
    f.write_bytes("Format: Prüfung".encode("cp1252"))
    assert platforms.read_text(f) == "Format: Prüfung"
    f.write_bytes(b"\xef\xbb\xbf" + "Format: Prüfung".encode())
    assert platforms.read_text(f) == "Format: Prüfung"


def test_cloud_placeholder_attribute():
    class P:
        def __init__(self, attrs):
            self.attrs = attrs

        def stat(self):
            return NS(st_file_attributes=self.attrs)
    assert platforms.cloud_placeholder(P(0x400000)) and platforms.cloud_placeholder(P(0x1000)) and not platforms.cloud_placeholder(P(0x20))


def test_no_attribute_means_a_normal_file(tmp_path):
    f = tmp_path / "a"
    f.write_text("x")
    assert not platforms.cloud_placeholder(f)


def test_placeholders_are_skipped_with_a_note(tmp_path, monkeypatch):
    (tmp_path / "a.mov").write_text("x")
    monkeypatch.setattr(guard.platforms, "cloud_placeholder", lambda p: True)
    files, notes = guard.media_files(tmp_path, False, {".mov"})
    assert files == [] and "Cloud" in notes[0]


# ---------- real Windows ----------
@on_windows
@pytest.mark.parametrize("folder", ["C:\\", r"C:\Windows", r"C:\Program Files", r"C:\Users"])
def test_too_general_places_are_refused(folder):
    with pytest.raises(guard.PathNotAllowed):
        guard.material_root(folder)


@on_windows
def test_profile_root_and_onedrive_are_refused(monkeypatch, tmp_path):
    with pytest.raises(guard.PathNotAllowed):
        guard.material_root(Path.home())
    monkeypatch.setenv("OneDrive", str(tmp_path))
    with pytest.raises(guard.PathNotAllowed):
        guard.material_root(tmp_path)


@on_windows
def test_project_folder_with_umlauts_and_spaces(tmp_path):
    p = tmp_path / "Mein Bäcker Film"
    p.mkdir()
    assert guard.material_root(f'"{p}"') == guard.real(p)


@on_windows
def test_case_does_not_matter(tmp_path):
    p = tmp_path / "Film"
    p.mkdir()
    (p / "a.txt").write_text("x")
    assert guard.inside(str(p / "a.txt").upper(), str(p).lower())


@on_windows
def test_a_junction_out_of_the_folder_is_skipped(tmp_path):
    material, outside = tmp_path / "m", tmp_path / "o"
    material.mkdir()
    outside.mkdir()
    (outside / "b.mov").write_text("x")
    (material / "a.mov").write_text("x")
    subprocess.run(["cmd", "/c", "mklink", "/J", str(material / "link"), str(outside)], check=True, capture_output=True)
    files, notes = guard.media_files(material, True, {".mov"})
    assert [f.name for f in files] == ["a.mov"] and any("außerhalb" in n for n in notes)


@on_windows
def test_paths_beyond_260_characters(tmp_path):
    deep = Path(platforms.extended(tmp_path / ("x" * 120) / ("y" * 120) / ("z" * 40)))
    deep.mkdir(parents=True)
    (deep / "a.mov").write_text("x")
    root = Path(platforms.plain(deep))
    assert len(str(root)) > 260 and guard.material_root(root) == root
    files, notes = guard.media_files(root, False, {".mov"})
    assert [f.name for f in files] == ["a.mov"] and "260" in notes[0]


@on_windows
def test_a_really_locked_file_gives_up_with_the_message(tmp_path):
    import msvcrt
    f, dst = tmp_path / "a", tmp_path / "b"
    f.write_text("x")
    dst.write_text("y")
    h = open(dst, "r+")
    msvcrt.locking(h.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        with pytest.raises(platforms.FileLocked):
            platforms.retry_locked(lambda: os.replace(f, dst), "„b“", tries=2, sleep=lambda s: None)
    finally:
        msvcrt.locking(h.fileno(), msvcrt.LK_UNLCK, 1)
        h.close()


@on_windows
def test_fcpxml_url_of_a_windows_path(tmp_path):
    f = tmp_path / "Mein Take.mov"
    f.write_text("x")
    assert f.resolve().as_uri().startswith("file:///") and "%20" in f.resolve().as_uri()


@on_windows
def test_bundled_ffmpeg_has_both_programs():
    from schnippo import ffmpeg_dist
    assert Path(ffmpeg_dist.path("ffmpeg")).name.lower() == "ffmpeg.exe" and Path(ffmpeg_dist.path("ffprobe")).name.lower() == "ffprobe.exe"
    assert Path(ffmpeg_dist.path("ffmpeg")).exists()


@on_windows
def test_windows_setup_check_names_python():
    from schnippo import setup_check
    from schnippo.config import Config
    checks = setup_check.run(Config(gladia_api_key="k"), gladia=lambda k: (True, "ok"), running=lambda: False, which=lambda t: ("x", "System"))
    py = next(c for c in checks if c.id == "python")
    assert py.ok and "64 bit" in py.detail
