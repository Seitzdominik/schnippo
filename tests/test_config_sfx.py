from pathlib import Path

from schnippo import sfx
from schnippo.config import load_config


def test_config_section_and_env(tmp_path, monkeypatch):
    f = tmp_path / "c.toml"
    f.write_text('[sfx]\nmode = "normal"\nfolder = "/tmp/meine-sounds"\n')
    monkeypatch.setenv("SCHNIPPO_CONFIG", str(f))
    cfg = load_config()
    assert cfg.sfx_mode == "normal" and cfg.sfx_folder == Path("/tmp/meine-sounds")
    monkeypatch.setenv("SCHNIPPO_SFX_MODE", "OFF")
    assert load_config().sfx_mode == "off"


def test_user_folder_is_measured_and_stays_where_it_is(tmp_path):
    from schnippo.media import _bin
    import subprocess
    d = tmp_path / "Eigene" / "whoosh"
    d.mkdir(parents=True)
    w = d / "laut.wav"
    subprocess.run([_bin("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "sine=f=800:d=0.3", "-af", "afade=in:st=0.1:d=0.05", str(w)], check=True)
    (tmp_path / "Eigene" / "notiz.txt").write_text("x")
    lib = sfx.load(tmp_path / "Eigene", tmp_path / "cache")
    own = [e for e in lib if e["id"] == "user:laut"]
    assert len(own) == 1 and own[0]["category"] == "whoosh" and own[0]["license"] == "Nutzer" and own[0]["file"] == str(w)
    assert 100 <= own[0]["hit_offset_ms"] <= 300
    assert (tmp_path / "cache" / "sfx_user.json").exists()


def test_library_files_move_to_a_stable_place(tmp_path):
    src = sfx.library_dir() / "wav" / "tick_soft.wav"
    class S:
        file, index, length_ms = str(src), 1, None
    out = sfx.stage_files([S()], tmp_path)
    assert Path(out[1]).parent == tmp_path / "sfx" and Path(out[1]).name.startswith("tick_soft_") and Path(out[1]).exists()


def test_beds_get_their_own_copy_at_the_needed_length(tmp_path):
    import wave
    src = sfx.library_dir() / "wav" / "clock_timer.wav"
    class S:
        file, index, length_ms, category, kind = str(src), 2, 7000, "clock", "bed"
    before = src.stat().st_mtime
    out = sfx.stage_files([S()], tmp_path)
    with wave.open(out[2]) as w:
        assert abs(w.getnframes() / 48000 - 7.0) < 0.01 and w.getsampwidth() == 3
    assert src.stat().st_mtime == before
