"""Sense check (Phase 8.5 step 4): seam comparison and the per-piece cache, without Gladia."""
from types import SimpleNamespace

from schnippo import sense


def P(clip, a, b):
    return SimpleNamespace(clip=clip, start_frame=a, end_frame=b, frames=b - a)


def words(text, step=0.5, t0=0.0):
    return [{"text": w, "s": t0 + k * step, "e": t0 + k * step + 0.4, "ref": f"c01:w{k:04d}", "item": 1}
            for k, w in enumerate(text.split())]


def test_clean_cut_has_no_seam_problems_spelling_is_tolerated():
    exp = words("Hier bei der MOC AG findest du alles was du suchst")
    heard = words("hier bei der Moc-AG findest du alles, was du suchst.")
    found, st = sense.seams(exp, heard, [2.0])
    assert found == [] and st["cuts"] == 1


def test_swallowed_doubled_and_mangled_words_at_a_seam():
    exp = words("eins zwei drei vier fünf sechs sieben acht neun zehn")
    swallowed = sense.seams(exp, words("eins zwei drei fünf sechs sieben acht neun zehn"), [1.5])[0]
    assert [f["kind"] for f in swallowed] == ["verschluckt"] and swallowed[0]["expected"] == "vier"
    doubled = sense.seams(exp, words("eins zwei drei vier vier fünf sechs sieben acht neun zehn"), [1.5])[0]
    assert [f["kind"] for f in doubled] == ["verdoppelt"]
    mangled = sense.seams(exp, words("eins zwei blub vier fünf sechs sieben acht neun zehn"), [1.5])[0]
    assert [f["kind"] for f in mangled] == ["verstümmelt"]
    far, st = sense.seams(exp, words("eins zwei drei vier fünf sechs sieben blub neun zehn"), [1.0])
    assert far == [] and st["elsewhere"] == 1  # away from the cut: recognition noise, no seam problem


def test_only_changed_pieces_are_heard_again():
    a, b, c = P("c01", 0, 100), P("c01", 200, 300), P("c01", 400, 500)
    heard = [{"text": "eins", "s": 1.0, "e": 1.4}, {"text": "zwei", "s": 5.0, "e": 5.4}, {"text": "drei", "s": 9.0, "e": 9.4}]
    cache = sense.split_by_piece(heard, [a, b, c], 25)
    assert cache["c01:200-300"] == [{"text": "zwei", "s": 1.0, "e": 1.4, "c": None}]
    assert sense.missing_regions(cache, [a, b, c], 25) == []
    d = P("c01", 600, 650)  # replaces b; c moves up in the timeline
    assert sense.missing_regions(cache, [a, d, c], 25) == [(3.4, 6.6)]
    again = sense.join_pieces(cache, [a, c], 25)
    assert [(w["text"], w["s"]) for w in again] == [("eins", 1.0), ("drei", 5.0)]  # times follow the new position


def test_sections_break_at_sentence_ends():
    txt = sense.sections([{"text": "Satz.", "s": 0, "e": 1}, {"text": "Noch", "s": 61, "e": 62}, {"text": "einer.", "s": 62, "e": 63},
                          {"text": "Ende", "s": 70, "e": 71}], every_s=60)
    assert txt == ["[0:00] Satz. Noch einer.", "[1:10] Ende"]
