import json
import wave
from pathlib import Path

import numpy as np
import pytest

from schnippo import sfx
from schnippo.guides import default_dir, guide


def _effects():
    return json.loads((sfx.library_dir() / "library.json").read_text(encoding="utf-8"))["effects"]


def test_library_is_complete_and_small():
    ef = _effects()
    assert 30 <= len(ef) <= 45
    for cat in set(sfx.CATEGORIES) - {"atmo", "applause", "impact_soft", "impact", "alarm"}:  # atmo and applause only from the user's folder
        assert sum(e["category"] == cat for e in ef) >= 2
    assert not {e["category"] for e in ef} & {"atmo", "applause"}
    size = sum((sfx.library_dir() / e["file"]).stat().st_size for e in ef)
    assert size < 18e6
    assert all(e["type"] in ("oneshot", "bed", "sequence") and e["event_align"] in ("start", "transient", "end") for e in ef)
    text = (sfx.library_dir() / "LICENSES.md").read_text(encoding="utf-8")
    assert all(e["file"] in text for e in ef)
    cc0 = [e for e in ef if e["license"] == "CC0"]
    assert {e["category"] for e in cc0} == {"click", "typing", "clock", "downer", "ding", "alarm"}
    assert all(e["url"].startswith("https://freesound.org/") and e["url"] in text and e["author"] for e in cc0)
    assert all(e["license"] in ("CC0", "MIT (selbst erzeugt)") for e in ef)


@pytest.mark.parametrize("e", _effects(), ids=lambda e: e["id"])
def test_every_file_is_clean(e):
    with wave.open(str(sfx.library_dir() / e["file"])) as w:
        assert (w.getframerate(), w.getsampwidth(), w.getnchannels()) == (48000, 3, 2)
        assert abs(w.getnframes() / 48 - e["duration_ms"]) < 2
    assert e["true_peak_db"] < -1.5
    assert 0 <= e["hit_offset_ms"] <= e["duration_ms"]
    assert e["event_align"] != "end" or e["hit_offset_ms"] == e["duration_ms"]


def test_measure_finds_transient_and_late_peak():
    n = sfx.SR
    x = np.zeros(n)
    x[12000:12480] = np.hanning(480)
    assert abs(sfx.measure(x)["hit_offset_ms"] - 255) < 15
    rise = np.linspace(0, 1, n) ** 2 * np.sin(np.arange(n) * 0.1)
    assert sfx.measure(rise)["hit_offset_ms"] > 900


def test_category_from_name():
    assert sfx.guess_category(Path("Transitions/Air Whoosh 03.wav")) == "whoosh"
    assert sfx.guess_category(Path("bells/notification.wav")) == "ding"
    assert sfx.guess_category(Path("ui/Click_02.aif")) == "click"
    assert sfx.guess_category(Path("freesound_community-alarm-clock-90867.mp3")) == "alarm"
    assert sfx.guess_category(Path("dragon-studio-swoosh-riser-reverb-390309.mp3")) == "riser"
    assert sfx.guess_category(Path("soundreality-birds-576540.mp3")) == "atmo"
    assert sfx.guess_category(Path("freesound_community-023521_aplause-72935.mp3")) == "applause"
    assert sfx.guess_category(Path("dragon-studio-typing-keyboard-asmr-356116.mp3")) == "typing"
    assert sfx.guess_category(Path("kram/aufnahme1.wav")) is None


def test_sound_guide_in_the_passes_that_place_effects():
    assert "Sound" in guide(default_dir(), "broll") and "Sound" in guide(default_dir(), "motion")
    assert "hit_offset_ms" not in guide(default_dir(), "rough")


def test_clock_loops_in_step():
    """Whole seconds: looping keeps the ticks on their grid."""
    x = sfx.decode(sfx.library_dir() / "wav" / "clock_timer.wav")
    assert abs(len(x) / 48000 - round(len(x) / 48000)) < 0.002


def test_old_names_still_work():
    from types import SimpleNamespace as NS
    lib = [{"id": "clock_timer", "file": "/l/clock_timer.wav", "category": "clock", "intensity": 2}]
    assert sfx._pick(lib, NS(file="clock_tension"), None, 1, True, {})["id"] == "clock_timer"


def test_vinyl_only_on_request_or_in_bold():
    from types import SimpleNamespace as NS
    lib = [e for e in _effects() if e["category"] == "downer"]
    cue = NS(file=None)
    assert sfx._pick(lib, cue, "downer", 2, True, {}, None)["id"] == "downer_tape"
    assert sfx._pick(lib, cue, "downer", 2, True, {}, "minimal")["id"] == "downer_tape"
    assert "downer_vinyl" in {e["id"] for e in lib} and lib[[e["id"] for e in lib].index("downer_vinyl")]["auto_styles"] == ["bold"]
    assert sfx._pick(lib, NS(file="downer_vinyl"), "downer", 2, True, {}, None)["id"] == "downer_vinyl"


def test_real_bell_is_in_the_library():
    ids = {e["id"]: e for e in _effects()}
    assert ids["ding_real"]["category"] == "ding" and ids["alarm_real"]["category"] == "alarm"
    assert ids["ding_real"]["hit_offset_ms"] < 100 and ids["alarm_real"]["duration_ms"] > 3000
