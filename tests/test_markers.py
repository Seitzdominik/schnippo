"""Retake markers (Phase 8 step 5) – synthetic only, the real material contains none (see NOTES)."""
import numpy as np

from schnippo import markers
from schnippo.config import DEFAULT_RETAKE_WORDS
from schnippo.segments import Segment


def seg(i, text, t0, t1):
    return Segment(id=f"s{i:03d}", clip_id="c01", from_word="w0001", to_word="w0002", start_s=t0, end_s=t1, text=text,
                   plain=text, n_words=len(text.split()), pause_before_s=0.8, pause_after_s=0.8)


def test_spoken_marker_only_as_own_short_utterance():
    segs = [seg(1, "Das sage ich mir seit halben Jahr oder so", 0, 3), seg(2, "Ok nochmal.", 4, 4.6),
            seg(3, "Das Ganze sage ich mir seit einem halben Jahr.", 5.5, 8), seg(4, "Wir haben hier Stopp für Traktor", 9, 11),
            seg(5, "bissel mehr Abenteuer, bissel mehr Action.", 12, 14), seg(6, "Cut!", 15, 15.3)]
    found = markers.mark(segs, DEFAULT_RETAKE_WORDS, [])
    assert [(f["text"], f.get("before")) for f in found] == [("nochmal", "s001"), ("cut", "s005")]
    assert "retake_before:„nochmal“" in segs[0].flags and "marker:nochmal" in segs[1].flags
    assert not any(f.startswith(("marker", "retake")) for f in segs[3].flags)  # "Stopp" inside a sentence


def test_clap_is_short_loud_unvoiced_and_outside_words():
    env = np.full(1000, -65.0)
    voi = np.zeros(1000)
    env[500:503] = [-12, -18, -30]  # clap at 5.00 s: 30 ms
    env[700:715] = -20  # 150 ms thud: too long
    env[850:853] = [-12, -18, -30]  # clap-like, but inside a word
    voi[300:320] = 0.9
    env[300:320] = -15  # voiced vowel onset
    t = markers.claps(env, voi, [(8.4, 8.7)])
    assert t == [5.0]
    segs = [seg(1, "erster Versuch mit Versprecher", 1, 4.5), seg(2, "zweiter Versuch sauber", 5.5, 7)]
    found = markers.mark(segs, DEFAULT_RETAKE_WORDS, t)
    assert found[0]["kind"] == "Klatscher" and found[0]["before"] == "s001" and "retake_before:Klatscher" in segs[0].flags
