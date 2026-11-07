from schnippo.analysis import analyze
from schnippo.formatting import format_transcript, parse_word_ref
from schnippo.models import Clip

from conftest import make_acoustic, make_raw

SPEC = [
    ("Hallo", 0.50, 0.80), ("und", 0.85, 1.00), ("willkommen.", 1.05, 1.60),       # 1-3, then 0.9 s pause
    ("Heute", 2.50, 2.75), ("zeige", 2.80, 3.05), ("ich", 3.10, 3.20), ("euch,", 3.25, 3.45),  # 4-7
    ("äh,", 3.60, 3.90),                                                          # 8 filler
    ("heute", 4.00, 4.25), ("zeige", 4.30, 4.55), ("ich", 4.60, 4.70), ("euch", 4.75, 4.95),  # 9-12 restart
    ("drei", 5.00, 5.20), ("Tipps.", 5.25, 5.70),                                 # 13-14, then gap w/ speech
    ("Der", 7.00, 7.10), ("Ton,", 7.15, 7.40), ("also", 7.45, 7.70), ("der", 7.75, 7.85), ("Ton", 7.90, 8.10),  # 15-19
    ("schneidet", 8.20, 8.60), ("schneidet", 8.65, 9.05), ("raus.", 9.10, 9.40),   # 20-22
]
# activity where the words are + a voiced "äh" without word at 6.0-6.4 s + a breath at 6.6-6.9 s
VOICED = [(0.48, 1.62), (2.48, 5.72), (6.0, 6.4), (6.98, 9.42)]
BREATH = [(6.6, 6.9)]
CLIP = Clip(id="c01", path="/x/take1.mp4", fingerprint="f", duration_s=10.0, fps_num=30000, fps_den=1001)


def run(cfg, spec=SPEC, voiced=VOICED, breath=BREATH):
    return analyze("c01", make_raw(spec), cfg, acoustic=make_acoustic(10.0, voiced, breath), clip_duration_s=10.0)


def test_fillers_soft_and_hard(cfg):
    at = run(cfg)
    by = {e.id: e for e in at.entries}
    assert by["w0008"].kind == "filler"
    assert "soft_filler" in by["w0017"].flags and by["w0017"].kind == "word"  # "also" is only a soft candidate
    assert at.stats["fillers_asr"] == 1 and at.stats["soft_fillers"] == 1


def test_pauses_have_stable_ids(cfg):
    at = run(cfg)
    pauses = {e.id: e for e in at.entries if e.kind == "pause"}
    assert "p0003" in pauses and abs(pauses["p0003"].end_s - pauses["p0003"].start_s - 0.9) < 0.01
    assert "p0000" in pauses and "leading" in pauses["p0000"].flags
    cfg.pause_threshold_s = 2.0
    at2 = run(cfg)
    assert [e.id for e in at.entries if e.id[0] == "w"] == [e.id for e in at2.entries if e.id[0] == "w"]
    assert not [e for e in at2.entries if e.kind == "pause"]


def test_gap_fallback_flags_unrecognised_speech(cfg):
    at = run(cfg)
    inferred = [e for e in at.entries if "inferred" in e.flags and e.kind == "filler"]
    assert len(inferred) == 1 and inferred[0].id == "u0014"
    assert abs(inferred[0].start_s - 6.0) < 0.01 and abs(inferred[0].end_s - 6.4) < 0.01
    assert any(f.type == "unrecognized_speech" for f in at.findings)
    # without silence info there is no fallback, but pauses still come from word gaps
    at2 = analyze("c01", make_raw(SPEC), cfg, acoustic=None, clip_duration_s=10.0)
    assert not [e for e in at2.entries if "inferred" in e.flags]


def test_breath_is_own_class_not_filler(cfg):
    at = run(cfg)
    br = [e for e in at.entries if e.kind == "breath"]
    assert [(e.id, e.start_s, e.end_s) for e in br] == [("b0014", 6.6, 6.9)]
    assert at.stats["breaths"] == 1 and at.stats["fillers_inferred"] == 1


def test_word_end_stretched_over_silence_is_clamped(cfg):
    spec = [("Thema", 0.5, 0.9), ("ist.", 1.0, 3.2), ("Ich", 3.2, 3.4)]  # 'ist.' really ends at 1.2 s
    at = run(cfg, spec=spec, voiced=[(0.5, 1.2), (3.2, 3.4)], breath=[])
    ist = next(e for e in at.entries if e.id == "w0002")
    assert ist.end_s == 1.2 and any(f.startswith("end_clamped") for f in ist.flags)
    assert any(e.kind == "pause" and e.id == "p0002" and e.end_s - e.start_s > 1.9 for e in at.entries)


def test_restart_and_repeat(cfg):
    at = run(cfg)
    rs = [f for f in at.findings if f.type == "restart_candidate"]
    rp = [f for f in at.findings if f.type == "repeat"]
    assert ("w0004", "w0007") in [f.first for f in rs]
    assert dict((f.first, f.second) for f in rs)[("w0004", "w0007")] == ("w0009", "w0012")  # filler ignored
    assert ("w0015", "w0016") in [f.first for f in rs]  # "Der Ton, also der Ton"
    assert [f.first for f in rp] == [("w0020", "w0020")]
    by = {e.id: e for e in at.entries}
    assert "restart_candidate" in by["w0005"].flags and "restart_candidate" not in by["w0010"].flags


def test_format_compact(cfg):
    at = run(cfg)
    txt = format_transcript(CLIP, at)
    lines = txt.splitlines()
    assert lines[0].startswith("c01 take1.mp4 | 0:00.00–0:10.00 | 29.97fps | fake/de | 21 Wörter")
    assert "@0:00.50 1 Hallo 2 und 3 willkommen. <0.9s>" in txt
    assert "8 {äh,}" in txt and "{?0.4s}" in txt and "17 also~" in txt and "20 schneidet*" in txt
    assert "^ w0004–w0007 → w0009–w0012" in txt
    part = format_transcript(CLIP, at, 9, 14)
    assert "4 Heute" not in part and "9 heute" in part and "14 Tipps." in part and "{?0.4s}" not in part
    assert part.count("\n") < txt.count("\n")


def test_parse_word_ref():
    assert parse_word_ref("w0017") == 17 and parse_word_ref("17") == 17 and parse_word_ref("c03:w120") == 120
    assert parse_word_ref(None) is None


def test_clamp_when_next_word_onset_bleeds_into_stretched_word(cfg):
    spec = [("ist.", 1.0, 3.25), ("Ich", 3.25, 3.4)]  # next word's onset starts at 3.17, inside 'ist.'
    at = run(cfg, spec=spec, voiced=[(1.0, 1.2), (3.17, 3.4)], breath=[])
    assert next(e for e in at.entries if e.id == "w0001").end_s == 1.2


def test_german_um_is_a_word_english_um_a_filler(cfg):
    spec = [("Kredit", 0.0, 0.4), ("um", 0.5, 0.6), ("das", 0.7, 0.8), ("zu", 0.9, 1.0), ("ähm", 1.1, 1.3)]
    de = analyze("c01", make_raw(spec), cfg)
    kinds = {e.text: e.kind for e in de.entries if e.id[0] == "w"}
    assert kinds["um"] == "word" and kinds["ähm"] == "filler"
    raw = make_raw([("credit", 0.0, 0.4), ("um", 0.5, 0.6), ("so", 0.7, 0.8)])
    raw.language = "en"
    en = analyze("c01", raw, cfg)
    assert {e.text: e.kind for e in en.entries if e.id[0] == "w"}["um"] == "filler"
