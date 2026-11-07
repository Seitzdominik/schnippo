from schnippo import context as ctx
from schnippo import retakes
from schnippo.cutlist import Cutlist, merge_cutlists

import synthetic_take


def blocks(cfg):
    segs, duration = synthetic_take.segments(cfg)
    edges, groups = retakes.find(segs)
    return [(synthetic_take.clip(duration), segs, edges, groups)]


def test_pages_cover_all_segments_once(cfg):
    b = blocks(cfg)
    pages = ctx.paginate(b, 12)
    assert [len(p) for p in pages] == [12, 12, 12]
    assert sorted(k for p in pages for _, k in p) == list(range(36))


def test_overview_has_pages_groups_and_no_segment_texts(cfg):
    b = blocks(cfg)
    pages = ctx.paginate(b, 12)
    ov = ctx.render_overview(b, None, ["i01 …"], "/f", None, pages)
    assert "3 Seite(n)" in ov and "Seite 2: c01:s013–c01:s024" in ov
    assert "s021, s022, s026, s028" in ov and "Seiten 2, 3" in ov
    assert "Bauernbrot" not in ov and len(ov) < 2000


def test_page_shows_only_its_segments_and_cross_page_groups(cfg):
    b = blocks(cfg)
    pages = ctx.paginate(b, 12)
    p2 = ctx.render_page(b, pages, 2, None)
    assert "c01:s013" in p2 and "c01:s024" in p2 and "c01:s012 " not in p2 and "c01:s025 " not in p2
    assert "weitere Versuche auf Seite 3" in p2


def test_merge_cutlists_in_page_order():
    a = Cutlist(timeline_name="A", items=[{"clip": "c01", "from_word": "w0001", "to_word": "w0008"}],
                rejected=[{"segment": "c01:s002", "reason": "x"}])
    b = Cutlist(timeline_name="B", items=[{"clip": "c01", "from_word": "w0238", "to_word": "w0266"}],
                overlays=[{"media": "i03", "from_word": "c01:w0250", "to_word": "c01:w0255"}])
    m = merge_cutlists([a, b], "RC")
    assert m.timeline_name == "RC" and [i.from_word for i in m.items] == ["w0001", "w0238"]
    assert len(m.rejected) == 1 and m.overlays[0].media == "i03" and a.items[0].from_word == "w0001"
