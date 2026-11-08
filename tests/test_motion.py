from schnippo import platforms
import io
import os
from pathlib import Path

import pytest

from schnippo.cutlist import Cutlist, build_plan
from schnippo.mg import templates as T
from schnippo.mg import tokens
from schnippo.profiles import make_profile

from test_cutlist import CLIP, at  # noqa: F401

BROWSERS = platforms.cache_dir() / "playwright"


def tok():
    return tokens.load()


def test_tokens_brand_profiles_and_contrast(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHNIPPO_BRAND", str(tmp_path / "brand.json"))
    t = tokens.load()
    assert t["brand_name"] == "Standard" and t["brand"]["font_family"] == "Inter"
    tokens.save_brand("Kunde A", {"style": "tech", "accent": "#2255FF"})
    t2 = tokens.load()
    assert t2["brand_name"] == "Kunde A" and t2["brand"]["radius_px"] == 0 and t2["brand"]["font_family"] == "Space Grotesk"
    assert t2["brand"]["accent"] == "#2255FF" and t2["style"]["surface_mode"] == "dark"
    with pytest.raises(LookupError):
        tokens.load("Gibt es nicht")
    assert tokens.contrast("#FFFFFF", "#111111") > 15 and tokens.contrast("#FFFFFF", "#FFEE99") < 4.5
    assert "font-family:\"Brand\"" in tokens.font_faces(t2)


def test_templates_follow_motion_rules():
    t = tok()
    html, meta = T.build("callout", {"label": "90 Tage", "text": "2 Phasen", "underline": True}, t, "reel", 1080, 1920, 30, 2500)
    assert meta["out_ms"] < meta["in_ms"] and abs(meta["out_ms"] / meta["in_ms"] - 0.625) < 0.01  # exit shorter
    assert "cubic-bezier(0.05, 0.7, 0.1, 1)" in html and "cubic-bezier(0.3, 0, 0.8, 0.15)" in html  # token curves
    assert meta["text_delay_ms"] == round(4 * 1000 / 30)  # text 4 frames after the box
    assert "linear" not in html and "bounce" not in html.lower()
    assert "window.__seek" in html and "window.__duration_ms=2500" in html and "window.__ready" in html
    assert "http" not in html.split("<script>")[0].replace("http://www.w3.org", "")  # nothing loaded from the net
    with pytest.raises(ValueError):
        T.build("sparkles", {}, t, "reel", 1080, 1920, 30, 2000)


def test_layout_stages_keep_head_clearance():
    t = tok()
    head = (340, 620, 400, 520)  # x y w h (head box, not face)
    above = T.layout("callout", "reel", 1080, 1920, head, t, "above")
    assert above["fit_box"][3] == 620 - 48 and above["fit_box"][1] == 290  # 48 px clearance, safe top
    assert T.layout("callout", "reel", 1080, 1920, head, t, "side") is None  # 340-48-108 = 184 px < 300
    side = T.layout("callout", "reel", 1080, 1920, (560, 620, 300, 400), t, "side")
    assert side["fit_box"] == (108, 300, 560 - 48, 1340)
    below = T.layout("callout", "reel", 1080, 1920, head, t, "below")
    assert below["fit_box"][1] == 620 + 520 + 48 and below["fit_box"][3] == 1340
    assert T.layout("callout", "reel", 1080, 1920, (340, 300, 400, 1000), t, "above") is None  # no room above
    lt = T.layout("lower_third", "youtube", 1920, 1080, (1100, 300, 300, 300), t)
    assert lt["align"] == "left" and lt["left"] == 96
    with pytest.raises(LookupError):
        T.build("callout", {"text": "x"}, t, "reel", 1080, 1920, 30, 2500, face=(340, 300, 400, 1000), stage="above")


def test_graphics_placement_limits(at):
    prof = make_profile("reel")
    t = tok()
    items = [{"clip": "c01", "from_word": "w0001", "to_word": "w0003"}, {"clip": "c01", "from_word": "w0004", "to_word": "w0008"}]
    cl = Cutlist(items=items, options={"motion_aware_cuts": False},
                 graphics=[{"template": "counter", "params": {"to": 90, "suffix": "Tage"}, "from_word": "c01:w0004", "to_word": "c01:w0005"},
                           {"template": "callout", "params": {"text": "x"}, "from_word": "c01:w0001", "to_word": "c01:w0002"},
                           {"template": "nope", "from_word": "c01:w0001"},
                           {"template": "hook_text", "params": {"text": "frei"}, "from_word": "c01:w0001", "html": "<p>x</p>"}])
    plan = build_plan(cl, {"c01": CLIP}, {"c01": at}, prof=prof, tok=t)
    assert any("unbekanntes Template" in e for e in plan.errors) and any("Sandbox" in e for e in plan.errors)
    g1 = plan.graphics[0]
    total = sum(p.frames for p in plan.pieces)
    assert g1.tl_end == total  # extended to the minimum hold, clipped at the (short) timeline end
    assert any("verlängert" in w for w in plan.warnings) and any("Timeline-Ende" in w for w in plan.warnings)
    assert any("im Hook" in w and "callout" in w for w in plan.warnings)  # callout in the first 3 s


@pytest.mark.skipif(not any(BROWSERS.glob("chromium_headless_shell-*")), reason="Chromium nicht installiert")
def test_render_is_deterministic_and_hidden_at_edges(tmp_path):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS)
    from PIL import Image

    from schnippo.mg.render import Renderer, encode_prores4444
    t = tok()
    html, meta = T.build("hook_text", {"text": "Ab morgen früh ins Bett – wirklich?"}, t, "reel", 540, 960, 30, 2200,
                         face=(170, 380, 200, 220))
    with Renderer(tmp_path, 540, 960) as r:
        stills = r.stills(html, [0, 1100, 1100, 2199.9])
        fit = r.last_fit
        frames = r.frames(html, 30, tmp_path / "f")
    alpha = [Image.open(io.BytesIO(png)).getchannel("A").getextrema()[1] for _, png, _ in stills]
    assert alpha[0] == 0 and alpha[1] > 200 and alpha[3] < 40  # hidden at t=0, visible in the middle, gone at the end
    assert stills[1][1] == stills[2][1]  # same t → identical pixels (deterministic seek)
    assert fit["ok"] and fit["lines"] <= 2
    assert frames["frames"] == 66
    mov = encode_prores4444(tmp_path / "f", 30, tmp_path / "g.mov")
    import subprocess
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,pix_fmt,profile", "-of", "csv=p=0", str(mov)],
                           capture_output=True, text=True).stdout
    assert "prores" in probe and "yuva444p" in probe


def test_design_card_preview_and_save(tmp_path, monkeypatch):
    from schnippo import design
    monkeypatch.setenv("SCHNIPPO_BRAND", str(tmp_path / "brand.json"))
    d = design.card_data(None, None)
    assert d["view"] == "design" and [s["id"] for s in d["styles"]] == ["minimal", "bold", "soft", "tech"]
    assert "Inter" in d["fonts"] and d["radii"] == [0, 8, 18, 999] and d["min_contrast"] == 4.5
    html = design.preview_html({"style": "soft", "accent": "#2255FF"}, ["callout", "counter", "unknown"])
    assert set(html) == {"callout", "counter"} and "requestAnimationFrame" in html["callout"] and "#2255FF" in html["callout"]
    path, warn = design.save("Kunde B", {"style": "bold", "accent": "#FFD84D", "evil": "x"})
    assert not warn or "Kontrast" in warn[0]
    data = tokens.load_brands()
    assert data["active"] == "Kunde B" and "evil" not in data["profiles"]["Kunde B"]
    assert any("Kontrast" in w for w in design.save("Gelb", {"style": "bold", "accent": "#FFD84D"})[1])  # white on yellow
    with pytest.raises(FileNotFoundError):
        design.save("X", {"font_family": "/nicht/da.ttf"})


@pytest.mark.skipif(not any(BROWSERS.glob("chromium_headless_shell-*")), reason="Chromium nicht installiert")
@pytest.mark.parametrize("w,h,fmt", [(1920, 1080, "youtube"), (3840, 2160, "youtube"), (1080, 1920, "reel")])
def test_every_template_keeps_its_inner_padding(tmp_path, w, h, fmt):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS)
    from schnippo.mg.place import hold_time, inner_padding
    from schnippo.mg.render import Renderer
    t = tok()
    cases = [("callout", {"text": "90 Tage", "label": "Plan", "underline": True}), ("counter", {"to": 90, "suffix": "Tage"}),
             ("hook_text", {"text": "Wer bist du"}), ("list_steps", {"title": "So geht's", "items": ["Eins", "Zwei"]})]
    if fmt == "youtube":
        cases.append(("lower_third", {"name": "Max", "role": "Neue Leitung Segelwerk"}))
    with Renderer(tmp_path, w, h) as r:
        for name, par in cases:
            html, meta = T.build(name, par, t, fmt, w, h, 25, 3000, stage="lower_third" if name == "lower_third" else "above")
            (_, png, _), = r.stills(html, [hold_time(meta)])
            pad = inner_padding(png, r.last_inner, 0.9, 0.5)
            assert pad and pad["ok"], (name, pad)
    assert T.spacing(t)["pad_x_cap"] >= 0.9 and T.spacing(t)["pad_y_cap"] >= 0.5


def test_padding_measurement_finds_a_text_that_touches_the_edge():
    import numpy as np
    from PIL import Image

    from schnippo.mg.place import inner_padding
    a = np.zeros((100, 300, 4), np.uint8)
    a[10:90, 20:280] = (17, 17, 17, 140)  # box
    a[40:60, 24:200] = (255, 255, 255, 255)  # text 4 px from the left edge
    buf = io.BytesIO()
    Image.fromarray(a, "RGBA").save(buf, "PNG")
    pad = inner_padding(buf.getvalue(), {"rect": [20, 10, 280, 90], "font": 40}, 0.9, 0.5)
    assert pad["left"] == 4 and pad["top"] == 30 and pad["ok"] is False


def test_16_9_graphic_can_stand_beside_the_head():
    t = tok()
    side = T.layout("callout", "youtube", 1920, 1080, (1000, 100, 500, 700), t, "side")
    assert side["stage"] == "side" and side["fit_box"][2] == 1000 - 48  # free room left of the head, 48 px clearance
    assert T.layout("callout", "youtube", 1920, 1080, (300, 100, 1300, 700), t, "side") is None  # no room
    assert T.layout("callout", "youtube", 1920, 1080, (1000, 100, 500, 700), t, "below") is None
