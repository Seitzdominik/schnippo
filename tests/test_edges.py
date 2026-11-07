"""Natural word edges (Phase 8.5 step 3) on a synthetic 10-ms level envelope."""
from types import SimpleNamespace

import numpy as np

from schnippo import edges as ed
from schnippo.cutlist import CutOptions, plan_item
from schnippo.models import AnalyzedTranscript, Word

from test_cutlist import CLIP, FPS


def acoustic(spans, floor=-70.0, n=1200):
    """spans: (t0, t1, level_db); between them the noise floor."""
    env = np.full(n, floor)
    for a, b, lv in spans:
        env[int(a * 100):int(b * 100)] = lv
    return SimpleNamespace(env_db=env, floor_db=floor)


def w(i, text, a, b, kind="word", flags=()):
    return Word(id=i, text=text, start_s=a, end_s=b, kind=kind, flags=list(flags))


def test_decay_and_onset_follow_the_signal():
    ac = acoustic([(1.0, 2.0, -20), (2.0, 2.25, -50), (0.92, 1.0, -48)])  # quiet tail 250 ms, fricative 80 ms before the word
    assert abs(ed.decay_end(ac, 2.0, 2.35) - 2.25) < 0.02
    assert abs(ed.decay_end(ac, 2.0, 2.10) - 2.10) < 0.02  # capped
    assert abs(ed.onset_start(ac, 1.0, 0.88) - 0.91) < 0.03
    assert ed.is_quiet(ac, 75, 25, "end", 12) and not ed.is_quiet(ac, 40, 25, "end", 12)


def test_attached_short_sound_is_a_stretched_word_long_one_stays_a_filler():
    ents = [w("w0001", "Rezepte", 1.0, 1.5), w("u0001", "?", 1.5, 1.7, "filler", ["inferred"]), w("w0002", "dich", 2.2, 2.5),
            w("u0002", "?", 2.5, 2.9, "filler", ["inferred"]), w("w0003", "auf", 3.5, 3.7),
            w("u0003", "?", 4.0, 4.2, "filler", ["inferred"]), w("w0004", "erschöpft", 4.2, 4.6),
            w("u0004", "?", 5.0, 5.3, "filler", ["inferred"]), w("w0005", "frei", 6.0, 6.3)]
    m = {e.id: e for e in ed.merge_stretches(ents)}
    assert "u0001" not in m and m["w0001"].end_s == 1.7  # end of the word
    assert "u0002" in m and m["w0002"].end_s == 2.6 and m["u0002"].start_s == 2.6  # 0.4 s: filler, word keeps 100 ms
    assert "u0003" not in m and m["w0004"].start_s == 4.0  # attached to the next word
    assert "u0004" in m  # free-standing sound stays


def at_of(entries):
    return AnalyzedTranscript(clip_id="c01", provider="x", language="de", entries=entries)


def test_plan_extends_the_end_to_the_decay_and_keeps_edges_quiet():
    words = [w("w0001", "Eins", 1.0, 1.5), w("w0002", "zwei.", 1.6, 2.0), w("w0003", "Drei", 4.0, 4.4)]
    ac = acoustic([(1.0, 2.0, -20), (2.0, 2.3, -45), (4.0, 4.4, -20)])
    opt = CutOptions(keep_pause_ms=150, decay_max_ms=350, motion_aware_cuts=False)
    (p0, p1) = plan_item(1, CLIP, at_of(words), 1, 3, opt, FPS, 360, ac=ac)
    assert p0.end_frame / FPS >= 2.3 - 0.04 and p0.decay_ms > 100  # default end (2.07) would cut the tail at -45 dB
    old = plan_item(1, CLIP, at_of(words), 1, 3, opt.model_copy(update={"plan_version": 1}), FPS, 360, ac=ac)
    assert old[0].end_frame / FPS < 2.2  # older cutlists plan as before


def test_expressive_sound_after_a_sentence_stays_hesitation_goes():
    from schnippo.cutlist import _expressive
    a = w("w0001", "Satz.", 1.0, 1.5)
    hm = w("u0001", "?", 1.6, 1.9, "filler", ["inferred"])
    assert _expressive(a, hm, 3.0) is hm
    assert _expressive(a, hm, 2.0) is None  # leads straight into the next words
    assert _expressive(a, w("w0002", "ähm", 1.6, 1.9, "filler"), 3.0) is None
    assert _expressive(w("w0001", "mitten", 1.0, 1.5), hm, 3.0) is None  # no sentence end


def test_soft_syllables_shortened_by_the_analysis_come_back():
    # "kurzfristige": the analysis kept 120 ms (end_clamped), the voice runs on at low level until 2.0 s, Gladia said 2.2 s
    ac = acoustic([(1.0, 1.12, -30), (1.12, 2.0, -50)])
    word = w("w0001", "kurzfristige", 1.0, 1.12)
    word.flags.append("end_clamped:2.20")
    (u,) = ed.unclamp([word], ac)
    assert abs(u.end_s - 2.0) < 0.03  # not 1.12, and not the stretched 2.2 either
    start = w("w0002", "hochzutauchen", 5.0, 5.4)
    start.flags.append("start_clamped:4.60")
    ac2 = acoustic([(4.8, 5.4, -40)])
    assert abs(ed.unclamp([start], ac2)[0].start_s - 4.79) < 0.03
