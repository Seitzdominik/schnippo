"""Design setup for motion graphics (brand profiles, optional): data for the design card, live previews built with the
same HTML templates as the renderer (autoplay instead of seek), saving to the user config (never the repo)."""

from __future__ import annotations

from pathlib import Path

from .mg import templates as T
from .mg import tokens

PREVIEW = (540, 960)
SAMPLE = {
    "hook_text": {"text": "Ab morgen früh ins Bett?"},
    "callout": {"label": "90 Tage", "text": "2 Phasen", "underline": True},
    "counter": {"from": 0, "to": 90, "suffix": "Tage", "label": "Fahrplan"},
}
RADII = [0, 8, 18, 999]


def inject_design(html: str) -> str:
    js = (Path(__file__).parent / "ui" / "design.js").read_text(encoding="utf-8")
    return html.replace("<!--DESIGN-->", f"<script>\n{js}\n</script>")


def card_data(brand: str | None, frame_uri: str | None) -> dict:
    data = tokens.load_brands()
    cur_name = brand or data.get("active")
    cur = dict((data.get("profiles") or {}).get(cur_name) or {})
    base = tokens.load(cur_name if cur else None)["brand"]
    return {"view": "design", "profile_name": cur_name or "Standard",
            "current": {**{k: base[k] for k in ("font_family", "accent", "text", "text_dark", "surface", "surface_light",
                                                "radius_px")}, "style": cur.get("style", "minimal")},
            "styles": [{"id": k, "label": v["label"], "brand": v["brand"], "surface_mode": v["surface_mode"]}
                       for k, v in tokens.STYLES.items()],
            "fonts": list(tokens.FONTS), "radii": RADII, "profiles": list((data.get("profiles") or {}).keys()),
            "frame": frame_uri, "min_contrast": tokens.load()["contrast"]["min_ratio"]}


def preview_html(profile: dict, templates: list[str], fmt: str = "reel", face=None) -> dict[str, str]:
    """Template HTML with the profile applied, autoplaying (loop) at preview size."""
    w, h = PREVIEW
    tok = tokens.apply_profile(tokens.load(), _clean(profile))
    out = {}
    for name in templates:
        if name not in SAMPLE:
            continue
        D = T.min_duration(name, tok, SAMPLE[name]) + 600
        html, _ = T.build(name, SAMPLE[name], tok, fmt, w, h, 30, D, face=face or (170, 400, 200, 230))
        loop = ("<script>window.__ready.then(()=>{const D=window.__duration_ms,P=900,t0=performance.now();"
                "(function f(){const t=(performance.now()-t0)%(D+P);window.__seek(Math.min(t,D-1));requestAnimationFrame(f);})();});</script>")
        out[name] = html.replace("</body>", loop + "</body>")
    return out


def _clean(profile: dict) -> dict:
    allowed = {"style", "font_family", "accent", "text", "text_dark", "surface", "surface_light", "radius_px", "font_weights"}
    p = {k: v for k, v in (profile or {}).items() if k in allowed and v not in (None, "")}
    if "radius_px" in p:
        p["radius_px"] = int(p["radius_px"])
    return p


def save(name: str, profile: dict) -> tuple[Path, list[str]]:
    p = _clean(profile)
    warn = []
    tok = tokens.apply_profile(tokens.load(), p)
    b = tok["brand"]
    mode = tok["style"]["surface_mode"]
    bg = {"light": b["surface_light"], "accent": b["accent"]}.get(mode, b["surface"])
    fg = b["text_dark"] if mode == "light" else b["text"]
    solid = bg if not bg.startswith("rgba") else "#" + "".join(f"{int(float(v)):02x}" for v in bg[5:-1].split(",")[:3])
    c = tokens.contrast(fg, solid)
    if c < tok["contrast"]["min_ratio"]:
        warn.append(f"Kontrast Text/Fläche {c}:1 < {tok['contrast']['min_ratio']}:1")
    fam = p.get("font_family")
    if fam and fam not in tokens.FONTS and not Path(fam).expanduser().exists():
        raise FileNotFoundError(f"Schriftdatei {fam} nicht gefunden")
    return tokens.save_brand(name or "Standard", p), warn
