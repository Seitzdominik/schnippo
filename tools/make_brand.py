"""Files the app expects, made from the originals in assets/brand. The originals stay as they are.

    uv run --group dev python tools/make_brand.py

icon.png (512, transparent, centred on what is really visible) · logo.svg · logo-dark.svg · social-preview.png · preview-sizes.png · favicons in website/assets (the folder is not part of the repository)."""
from __future__ import annotations

import base64
import io
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "assets" / "brand"
ICON_SVG = BRAND / "Schnippo Logo Icon.svg"
LOGO_SVG = BRAND / "Schnippo Logo.svg"
WEB = ROOT / "website" / "assets"
VIOLET, VIOLET_LIGHT, DARK_VIOLET_ON_DARK, ANTHRACITE = "#7C3AED", "#8B47FF", "#A78BFA", "#202020"


def lum(h: str) -> float:
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return round((x + 0.05) / (y + 0.05), 2)


def page_of(browser, w: int, h: int, scale: float = 1.0):
    return browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)


def svg_inline(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = text[text.index("<svg"):]
    return re.sub(r'\bwidth="100%" height="100%"', 'width="100%" height="100%" preserveAspectRatio="xMidYMid meet"', text, count=1)


def render_svg(browser, path: Path, w: int, h: int) -> Image.Image:
    """The drawing on a transparent canvas, w × h."""
    p = page_of(browser, w, h)
    p.set_content(f'<!doctype html><html style="background:transparent"><body style="margin:0;background:transparent"><div style="width:{w}px;height:{h}px">{svg_inline(path)}</div></body></html>')
    data = p.screenshot(omit_background=True)
    p.close()
    return Image.open(io.BytesIO(data)).convert("RGBA")


def fit_square(img: Image.Image, size: int, margin: float) -> Image.Image:
    """Centred on the visible pixels with an even margin: the snout stays whole."""
    box = img.getbbox()
    crop = img.crop(box)
    target = round(size * (1 - 2 * margin))
    k = target / max(crop.size)
    crop = crop.resize((round(crop.width * k), round(crop.height * k)), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(crop, ((size - crop.width) // 2, (size - crop.height) // 2), crop)
    return out


def dark_logo(text: str) -> str:
    """The same drawing, lighter violet: the original has 2.9:1 on anthracite."""
    return text.replace("rgb(124,58,237)", "rgb(167,139,250)").replace("rgb(139,71,255)", "rgb(196,181,253)")


def social(browser, logo: Path, font: str) -> Image.Image:
    p = page_of(browser, 1280, 640)
    p.set_content(f"""<!doctype html><html><body style="margin:0;width:1280px;height:640px;background:{ANTHRACITE};position:relative;overflow:hidden;font-family:{font},-apple-system,'Segoe UI',sans-serif">
<div style="position:absolute;right:-220px;top:-260px;width:760px;height:760px;border-radius:50%;background:radial-gradient(closest-side,{VIOLET}55,{VIOLET}00)"></div>
<div style="position:absolute;left:96px;top:176px;display:flex;align-items:center;gap:40px"><div style="width:232px;height:166px">{svg_inline(logo)}</div>
<div style="color:#fff;font-size:112px;font-weight:800;letter-spacing:-2px">Schnippo</div></div>
<div style="position:absolute;left:100px;top:392px;color:#fff;font-size:44px;font-weight:500">KI-Rohschnitt für DaVinci Resolve</div>
<div style="position:absolute;left:100px;top:470px;width:120px;height:8px;border-radius:4px;background:{VIOLET_LIGHT}"></div>
</body></html>""")
    data = p.screenshot()
    p.close()
    return Image.open(io.BytesIO(data)).convert("RGB")


def contact_sheet(master: Image.Image) -> Image.Image:
    sizes, zoom = (16, 32, 64), 4
    w, h = 1060, 640
    sheet = Image.new("RGB", (w, h), "#FFFFFF")
    d = ImageDraw.Draw(sheet)
    sheet.paste(Image.new("RGB", (w, h // 2), ANTHRACITE), (0, h // 2))
    for row, y0 in enumerate((0, h // 2)):
        x = 20
        ink = "#111111" if row == 0 else "#FFFFFF"
        for s in sizes:
            small = master.resize((s, s), Image.LANCZOS)
            sheet.paste(small, (x, y0 + 20), small)
            big = small.resize((s * zoom, s * zoom), Image.NEAREST)
            sheet.paste(big, (x + s + 16, y0 + 20), big)
            d.text((x, y0 + 26 + max(s, 16)), f"{s} px", fill=ink)
            x += s + 16 + s * zoom + 44
    return sheet


def main() -> None:
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / "Library" / "Caches" / "schnippo" / "playwright"))
    ico_sizes = (16, 32, 48)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        raw = render_svg(browser, ICON_SVG, 1536, 1536)
        icon = fit_square(raw, 512, 0.05)
        icon.save(BRAND / "icon.png", optimize=True)
        logo_txt = LOGO_SVG.read_text(encoding="utf-8")
        (BRAND / "logo.svg").write_text(logo_txt, encoding="utf-8")
        (BRAND / "logo-dark.svg").write_text(dark_logo(logo_txt), encoding="utf-8")
        font = "Inter"
        social(browser, BRAND / "logo-dark.svg", font).save(BRAND / "social-preview.png", optimize=True)
        browser.close()
    contact_sheet(icon).save(BRAND / "preview-sizes.png", optimize=True)
    buf = io.BytesIO()
    icon.resize((56, 56), Image.LANCZOS).save(buf, "PNG", optimize=True)
    (ROOT / "src" / "schnippo" / "ui" / "icon.b64").write_text(base64.b64encode(buf.getvalue()).decode("ascii") + "\n", encoding="ascii")
    if WEB.parent.is_dir():
        WEB.mkdir(exist_ok=True)
        icon.save(WEB / "favicon.ico", sizes=[(s, s) for s in ico_sizes])
        plate = Image.new("RGBA", (180, 180), ANTHRACITE)
        small = fit_square(raw, 180, 0.12)
        plate.paste(small, (0, 0), small)
        plate.convert("RGB").save(WEB / "apple-touch-icon.png", optimize=True)
    print(f"Kontrast Violett auf Weiß {contrast(VIOLET, '#FFFFFF')}:1 · auf Anthrazit {contrast(VIOLET, ANTHRACITE)}:1 · helles Violett auf Anthrazit {contrast(DARK_VIOLET_ON_DARK, ANTHRACITE)}:1 · Weiß auf Violett {contrast('#FFFFFF', VIOLET)}:1")


if __name__ == "__main__":
    sys.exit(main())
