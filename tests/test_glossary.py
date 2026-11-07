from types import SimpleNamespace

from schnippo import glossary as gl

TERMS = gl.parse(["# Projekt", "MOC AG = Moz AG, CU", "Raum Inn-Isar", "support@mondoria.de", "Segelwerk", "www.beispiel.de"])


def words(text):
    return [{"ref": f"c01:w{k:04d}", "text": w} for k, w in enumerate(text.split(), 1)]


def test_parse_and_vocabulary_holds_only_the_names():
    assert [t.value for t in TERMS][:2] == ["MOC AG", "Raum Inn-Isar"] and TERMS[0].aliases == ["Moz AG", "CU"]
    assert gl.vocabulary(TERMS) == ["MOC AG", "Raum Inn-Isar", "mondoria", "Segelwerk", "beispiel"]


def test_proposals_for_names_and_addresses():
    hits = gl.find(words("Hier bei der Moz AG aus dem Raum in Isar. Schreib an support@mandarin.com oder Segelwerft, CU"), TERMS)
    got = {h["value"]: (h["text"], h["sure"]) for h in hits}
    assert got["MOC AG"][1] is True and "Moz AG" in [h["text"] for h in hits]
    assert got["Raum Inn-Isar"] == ("Raum in Isar.", True)
    assert got["support@mondoria.de"][0] == "support@mandarin.com"
    assert gl.find(words("Hier bei der MOC AG im Raum Inn-Isar"), TERMS) == []  # correct stays untouched
    assert gl.find(words("Das ist eine gute Chance für alle Kunden"), TERMS) == []  # no false friends


def test_corrections_keep_the_comma_and_merge_words():
    (h,) = gl.find(words("Moz AG,"), TERMS)
    assert gl.corrections(h, "AG,") == {"c01:w0001": "MOC AG,", "c01:w0002": ""}


def test_text_on_graphics_and_confirmed_names():
    assert gl.check_text("Neue Leitung Segelwerft", TERMS) == ["„Segelwerft“ → „Segelwerk“"]
    assert gl.known("Segelwerk", TERMS) and gl.known("MOC", TERMS) and not gl.known("Max", TERMS)


def test_unsure_names_are_asked_not_guessed():
    t = lambda x, c=0.9: SimpleNamespace(text=x, confidence=c)
    toks = [t("Hier"), t("bei"), t("der"), t("Moz", 0.4), t("AG"), t("und"), t("bei"), t("der"), t("Moc", 0.5), t("AG."), t("Kaffee"), t("schmeckt"),
            t("gut"), t("in"), t("Musterhausen", 0.95), t("und"), t("Isar", 0.3)]
    g = gl.unsure_names(toks, [])
    assert g[0]["varies"] and sorted(g[0]["spellings"]) == ["Moc", "Moz"]
    assert any(x["spellings"] == ["Isar"] for x in g) and not any("Musterhausen" in x["spellings"] for x in g)
    assert gl.unsure_names(toks, gl.parse(["MOC AG = Moz, Moc", "Isar"])) == []
