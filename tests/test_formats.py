from schnippo.formats import detect
from schnippo.models import Clip


def clip(w, h, rot=0):
    return Clip(id="c01", path="/x.mov", fingerprint="f", duration_s=223, fps_num=30, fps_den=1, width=w, height=h, rotation=rot)


def test_portrait_short_is_reel():
    d = detect([clip(1080, 1920)], speech_s=150, raw_s=223, script_words=120)
    assert d.format == "reel" and d.confidence >= 0.9 and not d.ask and "9:16" in d.text()


def test_rotation_and_landscape_long_is_youtube():
    d = detect([clip(1920, 1080, rot=0)], speech_s=1500, raw_s=1800, script_words=1300)
    assert d.format == "youtube" and not d.ask
    d2 = detect([clip(1920, 1080, rot=90)], speech_s=150, raw_s=223)  # stored landscape, displayed portrait
    assert d2.format == "reel"


def test_conflicts_ask():
    d = detect([clip(1080, 1920)], speech_s=1500, raw_s=1500, script_words=1170)  # portrait but ~9 min script
    assert d.ask and "Hochformat" in d.conflict
    d = detect([clip(1920, 1080)], speech_s=60, raw_s=90, script_words=85)  # landscape but ~40 s
    assert d.ask and "Querformat" in d.conflict


def test_hint_decides_without_conflict():
    d = detect([clip(1080, 1080)], speech_s=400, raw_s=500, hint="youtube")
    assert d.format == "youtube" and not d.ask


# ---------- Phase 8: youtube / course / commercial from content signals ----------
import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from schnippo.config import Config  # noqa: E402
from schnippo.formats import refine  # noqa: E402

GT = json.loads((Path(__file__).parent / "fixtures" / "format_signals.json").read_text())


@pytest.mark.parametrize("name", sorted(GT["projects"]))
def test_refine_matches_the_film_types(name):
    p = GT["projects"][name]
    base = detect([clip(p["w"], p["h"])], speech_s=p["speech_s"], raw_s=p["raw_s"])
    d = refine(base, speakers=p["speakers"], aroll_clips=p["aroll_clips"], broll_clips=p["broll_clips"],
               longest_take_speech_s=p["longest_take_speech_s"], aroll_speech_s=p["speech_s"], text=p["text_hits"])
    assert d.format == p["expect"], d.text()
    assert not d.ask


def test_refine_hint_and_portrait():
    base = detect([clip(1080, 1920)], speech_s=60, raw_s=200)
    assert refine(base, speakers=1, aroll_clips=1, broll_clips=0, longest_take_speech_s=60, aroll_speech_s=60,
                  text="").format == "reel"
    d = refine(base, speakers=1, aroll_clips=5, broll_clips=8, longest_take_speech_s=12, aroll_speech_s=50, text="")
    assert d.format == "commercial"  # portrait commercial
    base = detect([clip(1920, 1080)], speech_s=400, raw_s=600)
    assert refine(base, speakers=1, aroll_clips=1, broll_clips=0, longest_take_speech_s=400, aroll_speech_s=400, text="",
                  hint="course").format == "course"


def test_broll_threshold_separates_the_measured_groups():
    thr = Config().broll_max_confidence
    m = GT["broll_mean_confidence"]
    assert max(m["hallucinated_on_ambience"]) < thr < min(m["noisy_chatter"] + m["speech"])


def test_course_and_commercial_profiles():
    from schnippo.profiles import make_profile
    c, w, y = make_profile("course"), make_profile("commercial", layout="reel"), make_profile("youtube")
    assert c.keep_pause_ms > y.keep_pause_ms and c.chapters and c.layout == "youtube"
    assert w.runtime_s[1] <= 60 and w.layout == "reel" and not w.chapters and w.broll_coverage[0] >= 0.4
