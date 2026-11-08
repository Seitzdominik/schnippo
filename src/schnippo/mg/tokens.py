"""Design tokens (guides/design_tokens.json) + brand profiles from the user config (never in the repo).

Brand profiles live in ~/.config/schnippo/brand.json: {"active": "Standard", "profiles": {"Standard": {...brand...}}}.
A profile may set: font_family (one of FONTS or a path to a TTF/OTF/WOFF2), font_weights (max 2), accent, text, text_dark,
surface, surface_light, radius_px, style (minimal | bold | soft | tech: token overrides, never new rules).
"""

from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path

from ..platforms import config_dir

ROOT = Path(__file__).resolve().parents[1] / "data"
FONT_DIR = Path(__file__).parent / "fonts"
# bundled OFL fonts: family → (file stem, weights available)
FONTS = {
    "Inter": ("inter", (600, 800)),
    "Manrope": ("manrope", (600, 800)),
    "DM Sans": ("dm-sans", (600, 800)),
    "Space Grotesk": ("space-grotesk", (600, 700)),
    "Instrument Sans": ("instrument-sans", (600, 700)),
}
# design languages = token overrides (05_motion_graphics rules always apply)
STYLES = {
    "minimal": {"label": "Minimal Editorial", "brand": {"radius_px": 8, "font_weights": [600, 800]},
                "surface_mode": "line", "stagger_scale": 1.2, "expressive": False},
    "bold": {"label": "Bold Creator", "brand": {"radius_px": 18, "font_weights": [600, 800]},
             "surface_mode": "accent", "stagger_scale": 0.8, "expressive": True},
    "soft": {"label": "Soft Premium", "brand": {"radius_px": 28, "font_weights": [600, 800]},
             "surface_mode": "light", "stagger_scale": 1.3, "expressive": False},
    "tech": {"label": "Clean Tech", "brand": {"radius_px": 0, "font_family": "Space Grotesk", "font_weights": [600, 700]},
             "surface_mode": "dark", "stagger_scale": 0.9, "expressive": False},
}


def tokens_path() -> Path:
    return ROOT / "guides" / "design_tokens.json"


def brand_path() -> Path:
    return Path(os.environ.get("SCHNIPPO_BRAND", config_dir() / "brand.json"))


def load_brands() -> dict:
    p = brand_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"active": None, "profiles": {}}


def save_brand(name: str, profile: dict, activate: bool = True) -> Path:
    data = load_brands()
    data.setdefault("profiles", {})[name] = profile
    if activate:
        data["active"] = name
    p = brand_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load(brand: str | None = None) -> dict:
    """Tokens with the brand profile applied (named, else the active one, else the defaults)."""
    tok = json.loads(tokens_path().read_text(encoding="utf-8"))
    data = load_brands()
    name = brand or data.get("active")
    prof = (data.get("profiles") or {}).get(name) if name else None
    if brand and prof is None:
        raise LookupError(f"Marke „{brand}“ unbekannt – gespeichert: {', '.join(data.get('profiles') or {}) or 'keine'}")
    tok = apply_profile(tok, prof or {})
    tok["brand_name"] = name if prof else "Standard"
    return tok


def apply_profile(tok: dict, prof: dict) -> dict:
    tok = copy.deepcopy(tok)
    style = STYLES.get(prof.get("style") or "")
    if style:
        tok["brand"].update(style["brand"])
        tok["style"] = {k: v for k, v in style.items() if k != "brand"} | {"id": prof["style"]}
    else:
        tok["style"] = {"id": "standard", "label": "Standard", "surface_mode": "dark", "stagger_scale": 1.0, "expressive": False}
    for k, v in prof.items():
        if k in tok["brand"]:
            tok["brand"][k] = v
    tok["brand"]["font_weights"] = list(tok["brand"]["font_weights"])[:2]
    return tok


def font_faces(tok: dict) -> str:
    """@font-face rules with the font embedded as data URI (rendering never touches the network)."""
    fam = tok["brand"]["font_family"]
    out = []
    if fam in FONTS:
        stem, have = FONTS[fam]
        for w in tok["brand"]["font_weights"]:
            use = min(have, key=lambda x: abs(x - w))
            data = base64.b64encode((FONT_DIR / f"{stem}-{use}.woff2").read_bytes()).decode()
            out.append(f'@font-face{{font-family:"Brand";src:url(data:font/woff2;base64,{data}) format("woff2");font-weight:{w}}}')
    else:  # own file (licence with the user)
        from ..guard import check_font
        p = check_font(fam, Path(os.environ["SCHNIPPO_MATERIAL"]) if os.environ.get("SCHNIPPO_MATERIAL") else None)
        fmt = {".woff2": "woff2", ".woff": "woff", ".otf": "opentype", ".ttf": "truetype"}.get(p.suffix.lower(), "truetype")
        data = base64.b64encode(p.read_bytes()).decode()
        for w in tok["brand"]["font_weights"]:
            out.append(f'@font-face{{font-family:"Brand";src:url(data:font/{fmt};base64,{data}) format("{fmt}");font-weight:{w}}}')
    return "\n".join(out)


def contrast(fg: str, bg: str) -> float:
    """WCAG contrast ratio of two colours (#rgb, #rrggbb or rgba() – alpha ignored, scrim assumed opaque enough)."""
    def rgb(c: str) -> tuple[float, float, float]:
        c = c.strip()
        if c.startswith("rgba") or c.startswith("rgb"):
            vals = [float(x) for x in c[c.index("(") + 1:c.index(")")].split(",")[:3]]
        else:
            c = c.lstrip("#")
            c = "".join(ch * 2 for ch in c) if len(c) == 3 else c
            vals = [int(c[i:i + 2], 16) for i in (0, 2, 4)]
        return tuple(v / 255 for v in vals)

    def lum(c):
        lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb(c)]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return round((a + 0.05) / (b + 0.05), 2)
