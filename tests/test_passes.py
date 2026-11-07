import pytest

from schnippo import qc
from schnippo.cutlist import Cutlist, build_plan, plan_item, CutOptions
from schnippo.passes import resolve, timeline_name
from schnippo.profiles import make_profile

from test_cutlist import CLIP, FPS, at  # noqa: F401

PROF = make_profile("reel", "ruhig-dicht")
ITEMS = [{"clip": "c01", "from_word": "w0001", "to_word": "w0003", "note": "Hook"},
         {"clip": "c01", "from_word": "w0004", "to_word": "w0008"}]


def rough(**kw):
    return Cutlist(**{"name": "Test", "pass": "rough", "items": ITEMS, **kw})


def test_rough_ignores_zoom_overlays_audio_and_names_timeline():
    cl = rough(punch_in={"mode": "alternate"}, audio={"target_lufs": -14},
               overlays=[{"media": "i01", "from_word": "c01:w0004", "to_word": "c01:w0005"}],
               items=[{**ITEMS[0], "zoom": 1.3}, ITEMS[1]], options={"cut_fillers": True})
    eff, notes = resolve(cl, None, PROF)
    assert eff.timeline_name == "Test_V1_Rough" and eff.punch_in is None and eff.audio is None and not eff.overlays
    assert eff.items[0].zoom is None
    assert not eff.options.cut_fillers and not eff.options.motion_aware_cuts  # hard cuts, pauses/fillers stay
    assert eff.options.tighten_gaps_over_ms == PROF.rough_max_gap_ms
    joined = " ".join(notes)
    for f in ("punch_in", "audio", "overlays", "options", "zoom"):
        assert f in joined


def test_fine_starts_from_base_and_uses_profile_defaults():
    base, _ = resolve(rough(), None, PROF)
    fine = Cutlist(**{"pass": "fine", "base_cutlist": "Test_V1_Rough", "punch_in": {"mode": "alternate"},
                      "item_changes": [{"index": 2, "zoom": 1.3, "pause_after_ms": 500}],
                      "overlays": [{"media": "i01", "from_word": "c01:w0004", "to_word": "c01:w0005"}]})
    eff, notes = resolve(fine, base, PROF)
    assert eff.timeline_name == "Test_V2_Fine" and eff.name == "Test" and [i.from_word for i in eff.items] == ["w0001", "w0004"]
    assert eff.options.cut_fillers and eff.options.motion_aware_cuts  # not the rough options
    assert eff.options.keep_pause_ms == PROF.keep_pause_ms and eff.options.tighten_gaps_over_ms == PROF.tighten_gaps_over_ms
    assert eff.punch_in.scale == PROF.punch_in_scale and eff.punch_in.rule == "sentence_no_repeat"
    assert eff.items[1].zoom == 1.3 and eff.items[1].pause_after_ms == 500 and eff.items[0].note == "Hook"
    assert not eff.overlays and any("overlays" in n for n in notes)
    # explicit options win over the profile
    eff2, _ = resolve(Cutlist(**{"pass": "fine", "base_cutlist": "x", "options": {"keep_pause_ms": 222}}), base, PROF)
    assert eff2.options.keep_pause_ms == 222 and eff2.options.tighten_gaps_over_ms == PROF.tighten_gaps_over_ms


def test_fine_reports_take_changes_and_needs_base():
    base, _ = resolve(rough(), None, PROF)
    changed = Cutlist(**{"pass": "fine", "base_cutlist": "x", "items": [ITEMS[0], {**ITEMS[1], "to_word": "w0007"}]})
    eff, notes = resolve(changed, base, PROF)
    assert any("Take-/Inhaltsänderung" in n and "w0007" in n for n in notes)
    with pytest.raises(ValueError, match="base_cutlist"):
        resolve(Cutlist(**{"pass": "fine"}), None, PROF)


def test_broll_keeps_cut_and_polish_only_audio():
    base, _ = resolve(rough(), None, PROF)
    fine, _ = resolve(Cutlist(**{"pass": "fine", "base_cutlist": "x", "punch_in": {"mode": "alternate"}}), base, PROF)
    br, notes = resolve(Cutlist(**{"pass": "broll", "base_cutlist": "Test_V2_Fine",
                                   "overlays": [{"media": "i01", "from_word": "c01:w0004", "to_word": "c01:w0005"}],
                                   "punch_in": {"mode": "off"}, "options": {"keep_pause_ms": 999}}), fine, PROF)
    assert br.timeline_name == "Test_V3_BRoll" and len(br.overlays) == 1 and br.punch_in.mode == "alternate"
    assert br.options.keep_pause_ms == fine.options.keep_pause_ms and any("punch_in" in n for n in notes)
    po, notes = resolve(Cutlist(**{"pass": "polish", "base_cutlist": "Test_V3_BRoll", "audio": {"target_lufs": -14},
                                   "overlays": []}), br, PROF)
    assert po.timeline_name == "Test_V4_Polish" and po.audio is not None and len(po.overlays) == 1
    assert any("overlays" in n for n in notes)


def test_legacy_cutlist_without_pass_is_unchanged():
    cl = Cutlist(items=ITEMS, timeline_name="RC_v9", punch_in={"mode": "alternate", "scale": 1.12})
    eff, notes = resolve(cl, None, PROF)
    assert eff.timeline_name == "RC_v9" and not notes and timeline_name(cl) == "RC_v9"


def test_profiles_formats_styles_and_overrides():
    yt = make_profile("youtube", "ruhig")
    assert yt.keep_pause_ms == 350 and yt.keep_pause_mid_ms == 250 and yt.keep_breaths and yt.punch_in_rule == "sentence" and yt.chapters
    d = make_profile("reel", "dicht")
    assert d.tighten_gaps_over_ms == 250 and d.keep_pause_ms == 105 and d.punch_in_rule == "every"
    o = make_profile("reel", "ruhig-dicht", {"punch_in_scale": 1.18, "youtube": {"keep_pause_ms": 350}})
    assert o.punch_in_scale == 1.18 and o.keep_pause_ms == 150
    assert make_profile("youtube", "ruhig-dicht", {"youtube": {"keep_pause_ms": 350}}).keep_pause_ms == 350
    with pytest.raises(ValueError, match="unbekannte"):
        make_profile("reel", "ruhig", {"foo": 1})
    with pytest.raises(ValueError, match="format"):
        make_profile("tiktok")


def test_pause_after_and_punch_in_rule(at):
    opt = CutOptions(motion_aware_cuts=False)
    (p0,) = plan_item(1, CLIP, at, 1, 3, opt, FPS, 360)
    (p1,) = plan_item(1, CLIP, at, 1, 3, opt, FPS, 360, pause_after_ms=500)
    assert p1.end_s == pytest.approx(2.50) and p0.end_s == pytest.approx(2.12)  # 'drei.' ends 2.00
    # rule: sentence → only at sentence starts; every → at every jump cut
    items = [{"clip": "c01", "from_word": "w0004", "to_word": "w0007"}, {"clip": "c01", "from_word": "w0008", "to_word": "w0008"}]
    for rule, want in (("every", [1.0, 1.2, 1.0, 1.2]), ("sentence", [1.0, 1.0, 1.0, 1.2])):
        cl = Cutlist(items=items, options={"motion_aware_cuts": False}, punch_in={"mode": "alternate", "scale": 1.2, "rule": rule})
        plan = build_plan(cl, {"c01": CLIP}, {"c01": at})
        assert [p.zoom for p in plan.pieces] == want, rule


def test_plan_checks_flash_tempo_overlays(at):
    cl = Cutlist(items=ITEMS, options={"motion_aware_cuts": False}, punch_in={"mode": "alternate", "scale": 1.2, "rule": "every"})
    plan = build_plan(cl, {"c01": CLIP}, {"c01": at})
    out = "\n".join(qc.plan_checks(cl, plan, {"c01": CLIP}, PROF, {"c01": at}))
    assert "Laufzeit" in out and "außerhalb" in out  # a few seconds is not a reel
    assert "Hook: erstes Wort ab Frame 3" in out and "Tempo:" in out and "Jump-Cuts mit Zoomwechsel" in out


class FakeTL(dict):
    pass


def tl_data(v1, audio_items=None, rate=30.0, total=None):
    total = total if total is not None else sum(x["frames"] for x in v1)
    return {"name": "T", "frames": total, "fps": rate, "v1": v1, "upper": {},
            "audio": {1: {"enabled": True, "items": audio_items if audio_items is not None else [(x["rec"], x["frames"]) for x in v1]}},
            "readback": {"timeline_fps": rate, "timeline_playback_fps": rate}, "markers": 0}


def item(rec, frames, src, zoom=1.0, clip="c01"):
    return {"clip": clip, "name": "t.mov", "rec": rec, "frames": frames, "src_start": src, "fps": 30.0, "zoom": zoom,
            "linked_audio": [(rec, frames)]}


def test_run_qc_finds_errors(at, monkeypatch):
    monkeypatch.setattr(qc, "watermark_hints", lambda paths: [])
    good = tl_data([item(0, 37, 27), item(37, 40, 88, 1.12)])
    res = qc.run(good, {"c01": CLIP}, {"c01": at}, PROF, "c01")
    assert res["ok"], res["lines"]
    # 2-frame piece, a hole, audio missing over the hole, a cut inside 'zwei' (1.35–1.60 s = f40.5–48)
    bad = tl_data([item(0, 44, 0), item(50, 2, 120), item(52, 30, 150)], audio_items=[(0, 44), (52, 30)], total=82)
    res = qc.run(bad, {"c01": CLIP}, {"c01": at}, PROF, "c01")
    text = "\n".join(res["lines"])
    assert not res["ok"] and "❌ Keine Flash-Frames" in text and "❌ Keine Lücken im Bild" in text
    assert "❌ Keine Lücken ohne Ton" in text and "w0002" in text
    # zoom on every jump cut
    z = tl_data([item(k * 30, 30, 30 * k, 1.12 if k % 2 else 1.0) for k in range(6)])
    assert any("❌ Nicht auf jedem Schnitt ein Zoom" in ln for ln in qc.run(z, {"c01": CLIP}, {}, PROF, "c01")["lines"])
    # wrong rate
    r = qc.run(tl_data([item(0, 30, 0)], rate=24.0), {"c01": CLIP}, {}, PROF, "c01")
    assert any(ln.startswith("❌ Framerate") for ln in r["lines"])
    # audio measurement
    r = qc.run(good, {"c01": CLIP}, {}, PROF, "c01", audio={"lufs": -14.5, "true_peak": -2.8})
    assert any(ln.startswith("✅ Lautheit") for ln in r["lines"])
    r = qc.run(good, {"c01": CLIP}, {}, PROF, "c01", audio={"lufs": -14.4, "true_peak": -0.2})
    assert any(ln.startswith("❌ Lautheit") for ln in r["lines"])


def test_watermark_hint_from_metadata(tmp_path):
    import subprocess
    f = tmp_path / "w.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=64x64:d=0.2", "-metadata",
                    "comment=Made with CapCut", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(f)], check=True)
    hits = qc.watermark_hints([str(f)])
    assert hits and "CapCut" in hits[0]


def test_alternates_only_in_rough():
    base, _ = resolve(rough(alternates=True), None, PROF)
    assert base.alternates
    fine, notes = resolve(Cutlist(**{"pass": "fine", "base_cutlist": "x", "alternates": True}), base, PROF)
    assert not fine.alternates and any("alternates" in n for n in notes)
    br, _ = resolve(Cutlist(**{"pass": "broll", "base_cutlist": "x"}), fine, PROF)
    assert not br.alternates


def test_run_qc_overlay_edges_and_graphics(at, monkeypatch):
    monkeypatch.setattr(qc, "watermark_hints", lambda paths: [])
    data = tl_data([item(0, 37, 27), item(37, 40, 88)])
    data["upper"] = {2: [("i01", 3, 30)]}  # starts 3 F after the timeline start cut
    r = qc.run(data, {"c01": CLIP}, {"c01": at}, PROF, "c01")
    assert any(ln.startswith("❌ Overlay-/Grafik-Kanten") and "3 F" in ln for ln in r["lines"])
    data["upper"] = {2: [("i01", 0, 37)]}
    g = [{"index": 1, "tl_start": 0, "frames": 30, "bbox": [300, 400, 700, 560], "min_gap": 52, "clearance": 48, "safe_ok": True},
         {"index": 2, "tl_start": 20, "frames": 30, "bbox": [320, 500, 680, 600], "min_gap": 30, "clearance": 48, "safe_ok": False}]
    r = qc.run(data, {"c01": CLIP}, {"c01": at}, PROF, "c01", graphics=g)
    txt = "\n".join(r["lines"])
    assert "✅ Overlay-/Grafik-Kanten" in txt and "❌ Grafiken: Abstand zum Kopf" in txt and "G2 30 px" in txt
    assert "❌ Grafiken: sichtbare Pixel" in txt and "❌ Grafiken überlappen sich nicht: G1/G2" in txt
