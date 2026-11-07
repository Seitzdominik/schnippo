import struct

import pytest

from schnippo import delivery
from schnippo.cutlist import Cutlist, Piece, build_plan
from schnippo.export import Chapter, export, paragraphs, pieces_from_timeline, suggest_chapters, timeline_words
from schnippo.models import AnalyzedTranscript, Word

FPS = 30.0


def long_at(n_sent=40, words_per=5, gap=0.6):
    """n_sent sentences of words_per words (0.3 s each), gap seconds between sentences."""
    entries, t, k = [], 0.5, 1
    for s in range(n_sent):
        for j in range(words_per):
            txt = f"s{s}w{j}" + ("." if j == words_per - 1 else "")
            entries.append(Word(id=f"w{k:04d}", text=txt, start_s=round(t, 3), end_s=round(t + 0.3, 3), kind="word"))
            t += 0.32
            k += 1
        t += gap
    return AnalyzedTranscript(clip_id="c01", provider="fake", language="de", entries=entries)


def pieces_for(at, items):
    from test_cutlist import CLIP
    clip = CLIP.model_copy(update={"duration_s": 200.0, "nb_frames": 6000, "resolve_frames": 6000})
    cl = Cutlist(items=[{"clip": "c01", "from_word": a, "to_word": b} for a, b in items], options={"motion_aware_cuts": False})
    plan = build_plan(cl, {"c01": clip}, {"c01": at})
    assert plan.ok, plan.errors
    return plan.pieces


def test_paragraphs_break_at_item_boundaries_after_three_sentences():
    at = long_at(8)
    ps = pieces_for(at, [("w0001", "w0015"), ("w0016", "w0040")])  # items: 3 + 5 sentences
    words = timeline_words(ps, {"c01": at}, FPS, {})
    paras = paragraphs(words)
    assert len(paras) == 2 and paras[0].endswith("s2w4.") and paras[1].startswith("s3w0")


def test_youtube_chapters_rules(tmp_path):
    at = long_at(40)  # ~ 40 × 2.2 s ≈ 88 s
    items = [(f"w{1 + 25 * i:04d}", f"w{25 * (i + 1):04d}") for i in range(8)]  # 8 items of 5 sentences
    ps = pieces_for(at, items)
    res = export("YT", ps, {"c01": at}, FPS, {"c01:w0001": "Hallo."}, tmp_path, fmt="youtube")
    ch = res["chapters"]
    assert ch[0]["at"] == "0:00.00" or ch[0]["at"].startswith("0:00")
    assert len(ch) >= 3 and not res["chapter_warnings"]
    lines = (tmp_path / "YT_kapitel.txt").read_text().splitlines()
    assert lines[0].startswith("0:00 Hallo.") and all(ln.split(" ", 1)[0].count(":") == 1 for ln in lines)
    # given chapters: first one is moved to 0:00, too-short chapters are warned
    res2 = export("YT2", ps, {"c01": at}, FPS, {}, tmp_path, fmt="youtube",
                  chapters=[Chapter(word="c01:w0006", title="Intro"), Chapter(word="c01:w0011", title="Zu kurz")])
    assert res2["chapters"][0]["at"].startswith("0:00") and any("nur 2 Kapitel" in w for w in res2["chapter_warnings"])
    assert any("Zu kurz" in w for w in res2["chapter_warnings"]) or any("Intro" in w for w in res2["chapter_warnings"])


def test_reel_has_no_chapters_and_srt_blocks_max_words(tmp_path):
    at = long_at(6, words_per=7)
    ps = pieces_for(at, [("w0001", "w0042")])
    res = export("R", ps, {"c01": at}, FPS, {}, tmp_path, max_words=4)
    assert "chapters_file" not in res
    srt = (tmp_path / "R.srt").read_text().split("\n\n")
    texts = [b.split("\n", 2)[2].replace("\n", " ") for b in srt if b.strip()]
    assert all(len(t.split()) <= 4 for t in texts) and texts[1].endswith("s0w6.")  # 4 + 3, break at sentence end


def test_pieces_from_timeline_maps_words_and_gaps():
    at = long_at(4)
    items = [{"clip": "c01", "rec": 0, "frames": 60, "src_start": 0, "fps": FPS},
             {"clip": "c01", "rec": 70, "frames": 90, "src_start": 120, "fps": FPS}]  # 10-frame gap on the timeline
    ps, recs = pieces_from_timeline(items, {"c01": at})
    assert recs == [0, 70] and ps[0].word_ids[0] == "w0001"
    words = timeline_words(ps, {"c01": at}, FPS, {}, recs)
    assert words[len(ps[0].word_ids)]["start"] >= 70


def test_delivery_blob_fields_roundtrip():
    def qstr(s):
        e = s.encode("utf-16-be")
        return struct.pack(">I", len(e)) + e
    blob = struct.pack(">II", 1, 1) + qstr("UseTimelineFrameRate") + struct.pack(">I", 1) + b"\x00\x01"
    xml = f"<SyRecordInfo>\n <FieldsBlob>{blob.hex()}</FieldsBlob>\n</SyRecordInfo>"
    out = delivery.add_blob_fields(xml, delivery.normalization_fields(-14.0))
    b = bytes.fromhex(out.split("<FieldsBlob>")[1].split("<")[0])
    assert struct.unpack(">I", b[4:8])[0] == 5
    assert "RecordAudioNormalizationTargetLoudness".encode("utf-16-be") in b
    i = b.index("RecordAudioNormalizationTargetLoudness".encode("utf-16-be")) + len("RecordAudioNormalizationTargetLoudness") * 2
    assert struct.unpack(">I", b[i:i + 4])[0] == 6 and struct.unpack(">d", b[i + 5:i + 13])[0] == -14.0
    assert delivery.NORM_FIELDS["RecordAudioNormalizationMethod"] == 0  # values > 2 crashed Resolve
    assert delivery.add_blob_fields(out, delivery.normalization_fields(-14.0)) == out  # idempotent
    off = delivery.set_blob_fields(out, {"RecordNormalizeAudio": False})  # replaces, does not duplicate
    ver, entries = delivery.parse_blob(bytes.fromhex(off.split("<FieldsBlob>")[1].split("<")[0]))
    assert [k for k, _ in entries].count("RecordNormalizeAudio") == 1 and dict(entries)["RecordNormalizeAudio"][-1] == 0
    with pytest.raises(delivery.PresetError):
        delivery.add_blob_fields("<x/>", {})
