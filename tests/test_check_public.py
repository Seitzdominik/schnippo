import importlib.util
from pathlib import Path

import cv2
import numpy as np

spec = importlib.util.spec_from_file_location("check_public", Path(__file__).parents[1] / "tools" / "check_public.py")
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

SALT = "s"
DENY = {"salt": SALT, "names": [cp.fingerprint("Geheime Firma", SALT), cp.fingerprint("wortname", SALT)], "files": []}


def run(path, rel, deny=DENY):
    return cp.check_file(path, rel, deny)


def test_clean_text_passes(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("Alles gut, /Users/me/Filme und ein Beispiel.\n", encoding="utf-8")
    assert run(f, "a.md") == []


def test_names_are_found_from_hashes_only(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("Dreh bei GEHEIME firma im Mai\nund Wortname.\n", encoding="utf-8")
    assert len(run(f, "a.md")) == 2
    assert run(tmp_path / "a.md", "docs/wortname_take.md")[0].startswith("docs/wortname_take.md: Dateiname")


def test_keys_and_paths(tmp_path):
    f = tmp_path / "a.py"
    f.write_text('t = "ghp_' + "a" * 36 + '"\nk = "/Users/jemand/Filme"\nv = "/Volumes/Platte/x"\n', encoding="utf-8")
    assert [x.split(": ")[1].split()[0] for x in run(f, "a.py")] == ["GitHub-Token", "persönlicher", "persönlicher"]


def test_media_only_in_allowed_places(tmp_path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"x")
    assert "außerhalb" in run(f, "docs/x.mp4")[0]
    g = tmp_path / "y.m4a"
    g.write_bytes(b"x")
    assert run(g, "docs/hoerbeispiele/y.m4a") == []


def test_reference_audio_by_content(tmp_path):
    import hashlib
    f = tmp_path / "ok.wav"
    f.write_bytes(b"pixel")
    deny = {**DENY, "files": [hashlib.sha256(b"pixel").hexdigest()[:32]]}
    assert any("Referenzdatei" in p for p in run(f, "src/schnippo/data/sfx/wav/ok.wav", deny))


def test_plain_image_has_no_face(tmp_path):
    f = tmp_path / "icon.png"
    cv2.imwrite(str(f), np.full((256, 256, 3), 200, np.uint8))
    assert cp.faces(f) == 0
