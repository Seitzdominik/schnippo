"""Motion-graphics templates as self-contained HTML (transparent page = timeline resolution), animated with the Web
Animations API only (no third-party JS). Seek contract for every template and free graphic:
  window.__ready (Promise, fonts loaded + animations built) · window.__duration_ms · window.__seek(t_ms)
Rules (guides/05_motion_graphics.md), all values from design_tokens.json:
  enter decelerates (enter curve, in_ms), exit accelerates and is shorter (exit curve, out_ms ≈ 62 % of in_ms);
  mask reveal (text slides up behind an invisible edge), the box opens first and the text follows
  text_after_box_frames later; words staggered word_ms, lines line_ms; no bounce; underline/arrow drawn last;
  one font family, max 2 weights, one accent colour, one radius, one box style.
"""

from __future__ import annotations

import html as _html
import json

from .tokens import font_faces

TEMPLATES = {
    "hook_text": "eine Zeile über dem Kopf (≤ 8 Wörter, Reel ab Frame 1)",
    "callout": "Schlüsselbegriff/Zahl neben dem Kopf; Box öffnet sich, Text folgt; optional underline",
    "counter": "Zahl zählt hoch (from → to) mit Einheit, z. B. 0 → 90 Tage",
    "list_steps": "2–4 Punkte, zeilenweise gestaffelt",
    "lower_third": "Bauchbinde Name + Rolle (16:9)",
    "underline_arrow": "Pfeil/Unterstreichung, wird zuletzt gezeichnet (from/to in 0–1 Bildkoordinaten)",
}
PARAMS = {
    "hook_text": {"text": "str (≤ 8 Wörter)"},
    "callout": {"text": "str (1–4 Wörter)", "label": "str optional (kleine Zeile darüber)", "underline": "bool"},
    "counter": {"from": "int (Default 0)", "to": "int", "suffix": "str (z. B. Tage)", "label": "str optional"},
    "list_steps": {"title": "str optional", "items": "list[str] 2–4"},
    "lower_third": {"name": "str", "role": "str"},
    "underline_arrow": {"from": "[x, y] 0–1", "to": "[x, y] 0–1", "kind": "arrow | underline"},
}
CAP_RATIO = 0.72  # cap height / em of the bundled grotesques


def esc(s) -> str:
    return _html.escape(str(s), quote=True)


def _words(text: str, cls: str = "w") -> str:
    return " ".join(f'<span class="mask"><span class="{cls}">{esc(w)}</span></span>' for w in str(text).split())


SPACING = {"pad_x_cap": 1.05, "pad_y_cap": 0.6, "min_pad_x_cap": 0.9, "min_pad_y_cap": 0.5, "name_role_gap": 0.3,
           "accent_gap_cap": 1.05, "accent_width_cap": 0.12, "underline_gap_cap": 0.3, "lower_third_min_width_em": 6.0}


def spacing(tok: dict) -> dict:
    return {**SPACING, **{k: v for k, v in (tok.get("spacing") or {}).items() if not k.startswith("$")}}


def _surface(tok: dict, s: float = 1.0) -> tuple[str, str, str]:
    """(box background, text colour, extra css) by style surface mode."""
    b, mode = tok["brand"], tok["style"]["surface_mode"]
    if mode == "light":
        return b["surface_light"], b["text_dark"], ""
    if mode == "accent":
        return b["accent"], b["text"], ""
    if mode == "line":
        return b["surface"], b["text"], f"border-left:{max(4, round(6 * s))}px solid {b['accent']};"
    return b["surface"], b["text"], ""


STAGES = ("above", "side", "below")
# placement attempts in order (stage, drop the extra line, allow scaling): full size → without extra line → scaled → beside
# → below → not placed
ATTEMPTS = (("above", False, False), ("above", True, False), ("above", True, True), ("side", False, True), ("side", True, True),
            ("below", False, True), ("below", True, True))
STAGE_LABEL = {"above": "über dem Kopf", "side": "neben dem Kopf", "below": "unter dem Kinn"}


def layout(template: str, fmt: str, w: int, h: int, head: tuple[float, float, float, float] | None, tok: dict,
           stage: str = "above") -> dict | None:
    """Anchor region + fit box in px for one placement stage, or None if the stage has no room.
    head = worst-case head box (x, y, w, h) over the graphic's duration; clearance = layout.head_clearance_px."""
    if fmt == "youtube":
        m = tok["layout"]["youtube_1920x1080"]["title_safe"]
        sx = w / 1920
        xm, ym = m["x_margin"] * sx, m["y_margin"] * sx
        safe = (xm, ym, w - xm, h - ym)
        if template == "lower_third":
            left_side = head is None or head[0] + head[2] / 2 >= w / 2
            return {"left": xm, "right": w / 2 if left_side else xm, "bottom": ym + 0.06 * h, "align": "left" if left_side else "right",
                    "side": "links" if left_side else "rechts", "safe": safe, "fit_box": safe, "stage": "lower_third"}
        if stage == "side" and head is not None:  # beside the head: on the free side of the 16:9 frame
            clr = tok["layout"].get("head_clearance_px", 48) * sx
            left_room, right_room = head[0] - clr - xm, (w - xm) - (head[0] + head[2] + clr)
            if max(left_room, right_room) < 400 * sx:
                return None
            top = ym + 0.08 * h
            if left_room >= right_room:
                return {"left": xm, "right": w - (head[0] - clr), "top": top, "align": "left", "side": "links " + STAGE_LABEL["side"],
                        "safe": safe, "fit_box": (xm, top, head[0] - clr, h - ym), "stage": "side"}
            return {"left": head[0] + head[2] + clr, "right": xm, "top": top, "align": "left", "side": "rechts " + STAGE_LABEL["side"],
                    "safe": safe, "fit_box": (head[0] + head[2] + clr, top, w - xm, h - ym), "stage": "side"}
        if stage != "above":
            return None
        return {"left": xm, "right": xm, "top": ym + 0.08 * h, "align": "center", "side": "oben", "safe": safe, "fit_box": safe,
                "stage": "above"}
    L = tok["layout"]["reel_1080x1920"]
    s = w / 1080
    x0, x1 = L["safe_box"]["x"][0] * s, L["safe_box"]["x"][1] * s
    y0, y1 = L["safe_box"]["y"][0] * s, L["safe_box"]["y"][1] * s
    cy0 = L["callout_y"][0] * s
    clr = tok["layout"].get("head_clearance_px", 48) * s
    safe = (x0, y0, x1, y1)
    hx, hy, hw, hh = head if head else (w * 0.27, h * 0.25, w * 0.46, h * 0.35)
    if template == "underline_arrow":
        return {"left": x0, "right": w - x1, "top": y0, "align": "left", "side": "frei", "safe": safe, "fit_box": safe, "stage": "free"}
    if stage == "above":
        bottom = min(y1, hy - clr)
        if bottom - y0 < 90 * s:
            return None
        return {"left": x0, "right": w - x1, "bottom": h - bottom, "align": "center", "side": STAGE_LABEL["above"], "safe": safe,
                "fit_box": (x0, y0, x1, bottom), "stage": "above"}
    if stage == "side":
        left_room, right_room = hx - clr - x0, x1 - (hx + hw + clr)
        if max(left_room, right_room) < 300 * s:
            return None
        top = max(cy0, y0)
        if left_room >= right_room:
            col = (x0, top, hx - clr, y1)
            return {"left": x0, "right": w - (hx - clr), "top": top, "align": "left", "side": "links " + STAGE_LABEL["side"],
                    "safe": safe, "fit_box": col, "stage": "side"}
        col = (hx + hw + clr, top, x1, y1)
        return {"left": hx + hw + clr, "right": w - x1, "top": top, "align": "left", "side": "rechts " + STAGE_LABEL["side"],
                "safe": safe, "fit_box": col, "stage": "side"}
    if stage == "below":
        top = max(y0, hy + hh + clr)
        if y1 - top < 90 * s:
            return None
        return {"left": x0, "right": w - x1, "top": top, "align": "center", "side": STAGE_LABEL["below"], "safe": safe,
                "fit_box": (x0, top, x1, y1), "stage": "below"}
    return None


def build(template: str, params: dict, tok: dict, fmt: str, w: int, h: int, fps: float, duration_ms: int,
          face: tuple | None = None, expressive: bool = False, stage: str = "above", drop_label: bool = False,
          allow_scale: bool = True) -> tuple[str, dict]:
    """face = worst-case head box (x, y, w, h). Raises LookupError if the stage has no room."""
    if template not in TEMPLATES:
        raise ValueError(f"unbekanntes Template {template!r} – verfügbar: {', '.join(TEMPLATES)}")
    m, b = tok["motion"], tok["brand"]
    ty = tok["type"]["reel" if fmt == "reel" else "youtube"]
    s = w / (1080 if fmt == "reel" else 1920)
    if drop_label:  # fallback before scaling: the small extra line goes first (reels prefer one line)
        params = {k: v for k, v in params.items() if k not in ("label", "title")}
    lay = layout(template, fmt, w, h, face, tok, stage)
    if lay is None:
        raise LookupError(f"kein Platz {STAGE_LABEL.get(stage, stage)}")
    bg, fg, extra = _surface(tok, s)
    sp = spacing(tok)
    scale = tok["style"].get("stagger_scale", 1.0)
    enter = m["easing"]["enter_expressive" if expressive else "enter"]
    exit_ = m["easing"]["exit_expressive" if expressive else "exit"]
    t_in = m["dur"]["emph_ms"] if expressive else m["dur"]["in_ms"]
    t_out = m["dur"]["out_ms"]
    text_delay = round(m["stagger"]["text_after_box_frames"] * 1000 / fps)
    word_st, line_st = m["stagger"]["word_ms"] * scale, m["stagger"]["line_ms"] * scale
    D = int(duration_ms)
    ex0 = D - t_out
    wf = b["font_weights"]
    hi, lo = max(wf), min(wf)
    pos = "".join(f"{k}:{lay[k]:.0f}px;" for k in ("left", "right", "top", "bottom") if k in lay)
    just = {"left": "flex-start", "right": "flex-end", "center": "center"}[lay["align"]]
    anim: list[dict] = []
    js_extra = ""
    rad = round(b["radius_px"] * s)  # token at 1080/1920 px width, scaled like everything else
    # inner padding in em of the box (the box always has a font size, so it scales with the text and the resolution)
    pad_y, pad_x = sp["pad_y_cap"] * CAP_RATIO, sp["pad_x_cap"] * CAP_RATIO

    def box_anim(sel=".box", delay=0):
        anim.append({"sel": sel, "kf": [{"clipPath": f"inset(0 100% 0 0 round {rad}px)"},
                                        {"clipPath": f"inset(0 0% 0 0 round {rad}px)"}],
                     "delay": delay, "duration": t_in, "easing": enter})
        anim.append({"sel": sel, "kf": [{"clipPath": f"inset(0 0 0 0% round {rad}px)", "opacity": 1, "offset": 0},
                                        {"clipPath": f"inset(0 0 0 85% round {rad}px)", "opacity": 1, "offset": 0.75},
                                        {"clipPath": f"inset(0 0 0 100% round {rad}px)", "opacity": 0, "offset": 1}],
                     "delay": ex0 + t_out * 0.3, "duration": t_out * 0.7, "easing": exit_, "fill": "forwards"})

    def text_anim(sel, delay, stagger):
        anim.append({"sel": sel, "kf": [{"transform": "translateY(110%)"}, {"transform": "translateY(0)"}],
                     "delay": delay, "duration": t_in, "easing": enter, "stagger": stagger})
        anim.append({"sel": sel, "kf": [{"transform": "translateY(0)"}, {"transform": "translateY(-110%)"}],
                     "delay": ex0, "duration": t_out * 0.7, "easing": exit_, "fill": "forwards"})

    if template == "hook_text":
        words = str(params.get("text", "")).split()
        fs = ty["hook_cap_height_px"] * s / CAP_RATIO if fmt == "reel" else ty.get("callout_px", 64) * s
        body = f'<div class="box" style="font-size:{fs:.0f}px;font-weight:{hi}">{_words(" ".join(words))}</div>'
        box_anim()
        text_anim(".w", text_delay, word_st)
    elif template in ("callout", "counter"):
        fs = (ty["callout_cap_height_px"] * s / CAP_RATIO) if fmt == "reel" else ty["callout_px"] * s
        label = params.get("label")
        lab = f'<div class="lab" style="font-size:{fs * 0.42:.0f}px;font-weight:{lo}">{_words(label, "lw")}</div>' if label else ""
        if template == "callout":
            main = _words(params.get("text", ""))
        else:
            to, fr = int(params.get("to", 0)), int(params.get("from", 0))
            suf = params.get("suffix", "")
            main = (f'<span class="mask"><span class="w num" data-from="{fr}" data-to="{to}">{fr}</span></span>'
                    + (f' <span class="mask"><span class="w suf" style="font-weight:{lo}">{esc(suf)}</span></span>' if suf else ""))
        ul = ""
        if params.get("underline") and template == "callout":
            ul = (f'<div class="ul" style="height:{max(4, fs * 0.08):.0f}px;margin-top:{sp["underline_gap_cap"] * CAP_RATIO:.3f}em;background:{b["accent"]};'
                  f'border-radius:{fs * 0.04:.0f}px;transform:scaleX(0);transform-origin:left center"></div>')
        body = (f'<div class="box" style="font-size:{fs:.0f}px;font-weight:{hi}">{lab}<div class="main">{main}</div>{ul}</div>')
        box_anim()
        if label:
            text_anim(".lw", text_delay, word_st)
        n_words = len(str(params.get("text", "x")).split()) if template == "callout" else 2
        text_anim(".main .w", text_delay + (line_st if label else 0), word_st)
        if ul:  # drawn last: after the text has arrived
            t_ul = text_delay + (line_st if label else 0) + n_words * word_st + t_in * 0.6
            anim.append({"sel": ".ul", "kf": [{"transform": "scaleX(0)"}, {"transform": "scaleX(1)"}],
                         "delay": t_ul, "duration": m["dur"]["small_ms"], "easing": m["easing"]["move"]})
            anim.append({"sel": ".ul", "kf": [{"transform": "scaleX(1)", "transformOrigin": "right center"},
                                              {"transform": "scaleX(0)", "transformOrigin": "right center"}],
                         "delay": ex0, "duration": t_out * 0.6, "easing": exit_, "fill": "forwards"})
        if template == "counter":  # number follows the enter curve over emph_ms, starting with the text
            js_extra = (f"const C0={text_delay + (line_st if label else 0)},CD={m['dur']['emph_ms']};"
                        f"const EZ=bez({json.dumps([float(x) for x in m['easing']['enter'][13:-1].split(',')])});"
                        "window.__onseek=t=>{document.querySelectorAll('.num').forEach(el=>{const a=+el.dataset.from,b=+el.dataset.to;"
                        "const p=Math.min(1,Math.max(0,(t-C0)/CD));el.textContent=Math.round(a+(b-a)*EZ(p)).toLocaleString('de-DE');});};")
    elif template == "list_steps":
        items = list(params.get("items") or [])[:4]
        fs = (ty["callout_cap_height_px"] * s / CAP_RATIO * 0.72) if fmt == "reel" else ty["callout_px"] * s * 0.8
        title = params.get("title")
        rows = "".join(f'<div class="row"><span class="mask"><span class="li"><span class="dot" style="background:{b["accent"]}">'
                       f'{k}</span>{esc(t)}</span></span></div>' for k, t in enumerate(items, 1))
        tt = f'<div class="lab" style="font-size:{fs * 0.62:.0f}px;font-weight:{lo}">{_words(title, "lw")}</div>' if title else ""
        body = f'<div class="box" style="font-size:{fs:.0f}px;font-weight:{hi}">{tt}{rows}</div>'
        box_anim()
        if title:
            text_anim(".lw", text_delay, word_st)
        text_anim(".li", text_delay + (line_st if title else 0), line_st)
    elif template == "lower_third":
        nf, rf = ty.get("lower_third_name_px", 52) * s, ty.get("lower_third_role_px", 34) * s
        rel = rf / nf  # the role in em of the name; everything scales with the box
        edge = "right" if lay["align"] == "right" else "left"
        aw = max(3, round(sp["accent_width_cap"] * nf * CAP_RATIO))
        body = (f'<div class="box lt" style="font-size:{nf:.0f}px;border-{edge}:{aw}px solid {b["accent"]};'
                f'padding-{edge}:{sp["accent_gap_cap"] * CAP_RATIO:.3f}em;min-width:{sp["lower_third_min_width_em"]:g}em">'
                f'<div style="font-weight:{hi}">{_words(params.get("name", ""))}</div>'
                f'<div style="font-size:{rel:.3f}em;font-weight:{lo};opacity:.85;margin-top:{sp["name_role_gap"] / rel:.3f}em">'
                f'{_words(params.get("role", ""), "lw")}</div></div>')
        box_anim()
        text_anim(".w", text_delay, word_st)
        text_anim(".lw", text_delay + line_st, word_st)
    else:  # underline_arrow
        (x1, y1), (x2, y2) = params.get("from", [0.3, 0.4]), params.get("to", [0.6, 0.4])
        arrow = params.get("kind", "arrow") == "arrow"
        head = (f'<path d="M {x2 * w:.0f} {y2 * h:.0f} l {-28 * s:.0f} {-16 * s:.0f} M {x2 * w:.0f} {y2 * h:.0f} l {-28 * s:.0f} {16 * s:.0f}" '
                f'pathLength="100" stroke-dasharray="100" stroke-dashoffset="100" class="hd"/>' if arrow else "")
        body = (f'<svg class="arr" width="{w}" height="{h}" style="position:absolute;left:0;top:0;overflow:visible" fill="none" '
                f'stroke="{b["accent"]}" stroke-width="{8 * s:.0f}" stroke-linecap="round" stroke-linejoin="round">'
                f'<path d="M {x1 * w:.0f} {y1 * h:.0f} L {x2 * w:.0f} {y2 * h:.0f}" pathLength="100" stroke-dasharray="100" '
                f'stroke-dashoffset="100" class="ln"/>{head}</svg>')
        anim.append({"sel": ".ln", "kf": [{"strokeDashoffset": 100}, {"strokeDashoffset": 0}], "delay": 0,
                     "duration": m["dur"]["large_ms"], "easing": m["easing"]["move"]})
        if arrow:
            anim.append({"sel": ".hd", "kf": [{"strokeDashoffset": 100}, {"strokeDashoffset": 0}],
                         "delay": m["dur"]["large_ms"] * 0.8, "duration": m["dur"]["small_ms"], "easing": m["easing"]["move"]})
        anim.append({"sel": ".arr", "kf": [{"opacity": 1}, {"opacity": 0}], "delay": ex0, "duration": t_out, "easing": exit_,
                     "fill": "forwards"})
        pos, just = "left:0;top:0;", "flex-start"

    tracking = ty.get("tracking_em", -0.01)
    fx0, fy0, fx1, fy1 = lay.get("fit_box", lay.get("safe", (0, 0, w, h)))
    cap = {"hook_text": ty.get("hook_cap_height_px", 84), "callout": ty.get("callout_cap_height_px", 64),
           "counter": ty.get("callout_cap_height_px", 64), "list_steps": ty.get("callout_cap_height_px", 64) * 0.72}.get(template, 64)
    min_scale = min(1.0, ty.get("min_cap_height_px", 48) / cap) if fmt == "reel" else 0.6
    fit = {"top": fy0, "bottom": fy1, "left": fx0, "right": fx1,
           "maxLines": int(ty.get("max_lines", 2)) if template in ("hook_text", "callout") else 99,
           "min": round(min_scale, 3) if allow_scale else 1.0}
    css = f"""{font_faces(tok)}
html,body{{margin:0;width:{w}px;height:{h}px;background:transparent;overflow:hidden}}
.g{{position:absolute;{pos}display:flex;justify-content:{just};font-family:"Brand",sans-serif;color:{fg};
  letter-spacing:{tracking}em;line-height:1.08;-webkit-font-smoothing:antialiased;text-rendering:geometricPrecision}}
.box{{background:{bg};border-radius:{rad}px;padding:{pad_y}em {pad_x}em;{extra}max-width:100%;
  text-align:{lay['align'] if lay['align'] != 'right' else 'right'};clip-path:inset(0 100% 0 0)}}
.mask{{display:inline-block;overflow:hidden;vertical-align:bottom;padding:0.06em 0 0.1em;margin:-0.06em 0 -0.1em}}
.mask>span{{display:inline-block;transform:translateY(110%)}}
.lab{{opacity:.8;margin-bottom:.25em}}
.num{{font-variant-numeric:tabular-nums}}
.row{{margin:.18em 0}}.li{{display:inline-flex;align-items:center;gap:.45em}}
.dot{{display:inline-grid;place-items:center;width:1.25em;height:1.25em;border-radius:{rad}px;
  font-size:.7em;color:{b['text']}}}"""
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<div class="g" id="g">{body}</div>
<script>
const A={json.dumps(anim)};
window.__duration_ms={D};
function bez(p){{const[x1,y1,x2,y2]=p;const cx=3*x1,bx=3*(x2-x1)-cx,ax=1-cx-bx,cy=3*y1,by=3*(y2-y1)-cy,ay=1-cy-by;
 const X=t=>((ax*t+bx)*t+cx)*t,Y=t=>((ay*t+by)*t+cy)*t,dX=t=>(3*ax*t+2*bx)*t+cx;
 return x=>{{if(x<=0)return 0;if(x>=1)return 1;let t=x;for(let i=0;i<8;i++){{const d=dX(t);if(Math.abs(d)<1e-6)break;t-=(X(t)-x)/d;}}
 t=Math.min(1,Math.max(0,t));return Y(t);}};}}
{js_extra}
function buildAnims(){{for(const a of A){{document.querySelectorAll(a.sel).forEach((el,i)=>{{
  el.animate(a.kf,{{delay:a.delay+(a.stagger||0)*i,duration:a.duration,easing:a.easing,fill:a.fill||"both"}});}});}}
  document.getAnimations().forEach(x=>x.pause());}}
const FIT={json.dumps(fit) if template != "underline_arrow" else "null"};
function fitBox(){{if(!FIT)return {{scale:1,lines:0,ok:true}};const box=document.querySelector(".box");if(!box)return {{scale:1,ok:true}};
 const base=parseFloat(box.style.fontSize);let sc=1;const words=()=>[...box.querySelectorAll(".mask")];
 const lines=()=>new Set(words().filter(m=>!m.closest(".lab")).map(m=>Math.round(m.getBoundingClientRect().top))).size;
 const ok=()=>{{const r=box.getBoundingClientRect();return r.top>=FIT.top-0.5&&r.bottom<=FIT.bottom+0.5&&r.left>=FIT.left-0.5&&
   r.right<=FIT.right+0.5&&lines()<=FIT.maxLines;}};
 while(!ok()&&sc>FIT.min){{sc*=0.95;box.style.fontSize=(base*sc)+"px";}}
 return {{scale:+sc.toFixed(3),lines:lines(),ok:ok()}};}}
window.__ready=(async()=>{{await document.fonts.ready;window.__fit=fitBox();buildAnims();window.__seek(0);return true;}})();
window.__seek=t=>{{document.getAnimations().forEach(a=>{{a.currentTime=t;}});if(window.__onseek)window.__onseek(t);}};
window.__bbox=()=>{{const r=document.getElementById("g").firstElementChild.getBoundingClientRect();return [r.left,r.top,r.right,r.bottom];}};
window.__inner=()=>{{const x=document.querySelector(".box");if(!x)return null;const r=x.getBoundingClientRect(),c=getComputedStyle(x);
 const bl=parseFloat(c.borderLeftWidth)||0,br=parseFloat(c.borderRightWidth)||0;
 const rad=parseFloat(c.borderTopLeftRadius)||0;
 return {{rect:[r.left+bl,r.top,r.right-br,r.bottom],font:parseFloat(c.fontSize),skip_left:bl?rad+2:0,skip_right:br?rad+2:0}};}};
</script></body></html>"""
    meta = {"layout": {k: v for k, v in lay.items() if k != "safe"}, "safe": lay.get("safe"), "stage": lay.get("stage"),
            "min_scale": fit["min"], "label_dropped": drop_label,
            "in_ms": t_in, "out_ms": t_out,
            "text_delay_ms": text_delay, "expressive": expressive, "duration_ms": D}
    return page, meta


def min_duration(template: str, tok: dict, params: dict) -> int:
    """in + hold + out; complex graphics (lists, counters) hold longer."""
    m = tok["motion"]
    hold = m["hold_complex_min_ms"] if template in ("list_steps",) or len(params.get("items") or []) > 2 else m["hold_min_ms"]
    return m["dur"]["in_ms"] + hold + m["dur"]["out_ms"]
