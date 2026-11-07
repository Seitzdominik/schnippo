import os
import time

from schnippo.cache_admin import clear, scan


def _f(p, size=1000, age_days=0):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


def test_clear_cache_keeps_transcripts_and_used_renders(tmp_path):
    root = tmp_path / "cache"
    old_wav = _f(root / "media/ab/audio16k.wav", 5000, 40)
    old_frames = _f(root / "media/ab/frames/f000001.jpg", 3000, 40)
    tokens = _f(root / "media/ab/tokens.gladia.de.x.json", 100, 40)
    new_wav = _f(root / "media/cd/audio16k.wav", 5000, 1)
    check = _f(root / "fcpxml/audio/audio_it1_1.mov", 9000, 40)
    used = _f(root / "mg/abc.mov", 7000, 40)
    outside = _f(tmp_path / "material/take.mov", 100, 400)
    info = scan(root, 30)
    assert info["renders_check"]["old_bytes"] == 9000 and info["transcripts"]["old_bytes"] == 100
    text, freed = clear(root, 30)
    assert freed == 0 and "Noch nichts gelöscht" in text and old_wav.exists()
    text, freed = clear(root, 30, confirm=True)
    assert freed == 5000 + 3000 + 9000
    assert not old_wav.exists() and not old_frames.exists() and not check.exists()
    assert tokens.exists() and used.exists() and new_wav.exists() and outside.exists()
    _, freed2 = clear(root, 30, include_transcripts=True, include_renders=True, confirm=True)
    assert freed2 == 100 + 7000 and not tokens.exists() and not used.exists() and outside.exists()


def test_transcription_eta_matches_phase8_measurements():
    from schnippo.workspace import eta_seconds
    assert 20 <= eta_seconds([1060.3]) <= 35  # measured 27.8 s
    assert 4 <= eta_seconds([15.0]) <= 12  # measured 5–12 s
    assert eta_seconds([]) == 0 and eta_seconds([60] * 6) < 6 * eta_seconds([60])  # parallel
