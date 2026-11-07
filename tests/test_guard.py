import os
from pathlib import Path

import pytest

from schnippo import guard
from schnippo.guard import PathNotAllowed


def test_material_root_rejects_broad_folders(tmp_path):
    assert guard.material_root(tmp_path) == guard.real(tmp_path)
    for p in ("/", str(Path.home()), str(Path.home() / "Documents")):
        with pytest.raises(PathNotAllowed):
            guard.material_root(p)
    with pytest.raises(FileNotFoundError):
        guard.material_root(tmp_path / "fehlt")


def test_links_out_of_the_folder_and_own_exports_are_skipped(tmp_path):
    mat, outside = tmp_path / "mat", tmp_path / "secret"
    (mat / "schnippo-export").mkdir(parents=True)
    outside.mkdir()
    (mat / "take1.mov").write_bytes(b"x")
    (mat / "schnippo-export" / "final.mp4").write_bytes(b"x")
    (outside / "private.mov").write_bytes(b"x")
    os.symlink(outside / "private.mov", mat / "link.mov")
    (mat / "sub").mkdir()
    (mat / "sub" / "take2.mov").write_bytes(b"x")
    os.symlink(outside, mat / "sub" / "escape")
    files, notes = guard.media_files(mat, True, {".mov", ".mp4"})
    names = sorted(p.name for p in files)
    assert names == ["take1.mov", "take2.mov"]
    assert any("link.mov" in n for n in notes)
    with pytest.raises(PathNotAllowed):
        guard.check_read(mat / "sub" / "escape" / "private.mov", [mat], "Das Skript")
    with pytest.raises(PathNotAllowed):
        guard.check_read(mat / ".." / "secret" / "private.mov", [mat], "Das Skript")
    (mat / "skript.docx").write_bytes(b"x")
    assert guard.check_read(mat / "skript.docx", [mat], "Das Skript").name == "skript.docx"


def test_font_must_be_a_font_file_in_a_font_folder(tmp_path):
    (tmp_path / "x.ttf").write_bytes(b"x")
    (tmp_path / "x.txt").write_bytes(b"x")
    assert guard.check_font(tmp_path / "x.ttf", tmp_path).name == "x.ttf"  # inside the material folder
    with pytest.raises(PathNotAllowed):
        guard.check_font(tmp_path / "x.txt", tmp_path)
    with pytest.raises(PathNotAllowed):
        guard.check_font(tmp_path / "x.ttf", None)  # tmp is no font folder
