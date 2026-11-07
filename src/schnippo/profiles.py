"""Format/style profiles: the configurable defaults of the guides ([S]/[V] values), overridable in config.toml.

config.toml:
    format = "auto"            # auto | reel | youtube | course | commercial
    style = "ruhig-dicht"      # ruhig | ruhig-dicht | dicht
    [profile]                  # applies to every format
    punch_in_scale = 1.15
    [profile.youtube]          # only for youtube
    keep_pause_ms = 350
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace

FORMATS = ("reel", "youtube", "course", "commercial")
LABELS = {"reel": "Reel 9:16", "youtube": "YouTube-Video 16:9", "course": "Kursvideo 16:9", "commercial": "Werbespot"}
STYLES = ("ruhig", "ruhig-dicht", "dicht")


@dataclass(frozen=True)
class Profile:
    format: str = "reel"
    style: str = "ruhig-dicht"
    layout: str = "reel"  # sizes/safe zones of graphics: reel (portrait) | youtube (landscape); commercial follows the picture
    # cut points (02_fine_cut: pre 2–4 frames, post 3–6 frames)
    pre_pad_ms: int = 80
    post_pad_ms: int = 120
    keep_pause_ms: int = 150  # remaining pause between sentences: reel 100–250, youtube/course/interview 250–450
    keep_pause_mid_ms: int = 150  # remaining pause inside a sentence (hesitation cut out)
    deliberate_pause_ms: int = 400  # natural pause kept after a beat "key": reel 300–500, long formats 600–1000
    beat_section_ms: int = 400  # ... after a beat "section": long formats 800–1200
    tighten_gaps_over_ms: int = 350  # gaps longer than this are cut (style)
    keep_breaths: bool = False  # style ruhig: natural breaths at sentence boundaries stay
    decay_max_ms: int = 200  # follow the decay of a last word at most this long: reel 200, long formats 350
    edge_db: float = 12.0  # clean edge: last/first 10 ms below noise floor + this
    rough_max_gap_ms: int = 1500  # rough cut: only holes longer than this are cut …
    rough_keep_gap_ms: int = 400  # … down to this
    # punch-ins (02_fine_cut)
    punch_in_scale: float = 1.20  # main level: 100 % ↔ 120 % (Phase 8.5: 112 % was too subtle on real footage)
    punch_in_variation: tuple[float, float] = (1.12, 1.25)  # now and then instead of the main level, alternating
    punch_variation_every: int = 3  # every n-th punch-in uses a variation level (0 = never)
    accent_scale: float = 1.32  # 130–135 %, only for punchlines
    max_zoom_hd: float = 1.25  # 1080p source: above this it gets soft
    max_zoom_4k: float = 2.0  # 4K source for a 1080p delivery: no loss up to 200 %
    punch_in_rule: str = "sentence_no_repeat"  # sentence | sentence_no_repeat | every (style)
    punch_min_hold_s: float = 0.8  # a zoom level stands at least this long (reel 0.8, youtube/course 1.5, commercial 0.6)
    # tempo (02_fine_cut)
    change_every_s: tuple[float, float] = (2.0, 4.0)  # visual change on average: reel 2–4 s, youtube 3–7 s
    max_unchanged_s: float = 5.0
    # hook / runtime (01_rough_cut)
    hook_s: float = 3.0
    runtime_s: tuple[float, float] = (30.0, 90.0)
    # b-roll (03_broll)
    broll_min_s: float = 1.5  # reel 1.5–3 s, youtube 3–8 s
    broll_max_s: float = 3.0
    broll_every_s: tuple[float, float] = (8.0, 15.0)  # reel; youtube: coverage instead
    broll_coverage: tuple[float, float] = (0.0, 0.0)  # youtube 0.30–0.50
    # edges of stills (V2) and graphics (V3) vs. cuts in V1 (snap.py)
    overlay_snap_s: float = 0.6  # still edge closer than this to a cut → onto the cut
    graphic_snap_s: float = 0.34  # graphics may start mid-clip, but not 1–10 frames next to a cut
    sliver_s: float = 0.5  # no visible A-roll piece shorter than this between an edge and a cut
    cover_margin_frames: int = 4  # an overlay covering a jump cut starts/ends at least this far from it
    # polish (04_polish)
    target_lufs: float = -14.0
    lufs_range: tuple[float, float] = (-16.0, -13.0)
    true_peak_max: float = -1.0
    flash_frames: int = 3
    srt_max_words: int = 4  # reel: word-by-word captions; youtube/course: real subtitles (2 lines × 42 characters)
    srt_line_chars: int = 18
    srt_min_s: float = 0.4
    srt_comma_min_words: int = 1  # break at a comma only once the block has this many words
    chapters: bool = False
    chapter_min: int = 3
    chapter_min_s: float = 10.0

    def as_dict(self) -> dict:
        return asdict(self)


FORMAT_DEFAULTS = {
    "reel": {},
    "youtube": {"decay_max_ms": 350, "keep_pause_ms": 350, "keep_pause_mid_ms": 250, "deliberate_pause_ms": 800, "beat_section_ms": 1000, "change_every_s": (3.0, 7.0), "max_unchanged_s": 10.0,
                "hook_s": 15.0, "runtime_s": (480.0, 900.0), "broll_min_s": 3.0, "broll_max_s": 8.0,
                "broll_every_s": (0.0, 0.0), "broll_coverage": (0.30, 0.50), "chapters": True, "layout": "youtube",
                "punch_min_hold_s": 1.5, "srt_max_words": 12, "srt_line_chars": 42, "srt_min_s": 1.0, "srt_comma_min_words": 5},
    # course: calmer than YouTube – longer pauses, few punch-ins, screen recordings may stand long, chapters per lesson
    "course": {"decay_max_ms": 350, "keep_pause_ms": 400, "keep_pause_mid_ms": 300, "deliberate_pause_ms": 900, "beat_section_ms": 1100, "change_every_s": (5.0, 10.0), "max_unchanged_s": 20.0,
               "hook_s": 20.0, "runtime_s": (120.0, 1800.0), "punch_in_rule": "sentence",
               "broll_min_s": 3.0, "broll_max_s": 8.0, "broll_every_s": (0.0, 0.0), "broll_coverage": (0.10, 0.30),
               "chapters": True, "layout": "youtube", "punch_min_hold_s": 1.5,
               "srt_max_words": 12, "srt_line_chars": 42, "srt_min_s": 1.0, "srt_comma_min_words": 5},
    # commercial: scenic and short – picture carries it, tight pauses, frequent changes, much B-roll
    "commercial": {"keep_pause_ms": 120, "keep_pause_mid_ms": 120, "deliberate_pause_ms": 400, "change_every_s": (1.0, 2.5), "max_unchanged_s": 3.0,
                   "hook_s": 3.0, "runtime_s": (15.0, 60.0), "broll_min_s": 1.0, "broll_max_s": 3.0,
                   "broll_every_s": (3.0, 6.0), "broll_coverage": (0.40, 0.70), "chapters": False, "layout": "youtube",
                   "punch_min_hold_s": 0.6, "srt_max_words": 6, "srt_line_chars": 32, "srt_min_s": 0.7,
                   "srt_comma_min_words": 3},
}
STYLE_DEFAULTS = {
    "ruhig": {"tighten_gaps_over_ms": 450, "keep_breaths": True, "punch_in_rule": "sentence"},
    "ruhig-dicht": {"tighten_gaps_over_ms": 350, "punch_in_rule": "sentence_no_repeat"},
    "dicht": {"tighten_gaps_over_ms": 250, "keep_pause_ms_factor": 0.7, "punch_in_rule": "every"},
}


def max_zoom_for(prof: "Profile", width: int | None, height: int | None) -> float:
    """Highest zoom without visible softness, assuming a 1080p delivery: short side / 1080, at least max_zoom_hd
    (1080p source → 1.25, 1440p → 1.33, 4K → 2.0)."""
    short = min(width or 1080, height or 1920)
    return max(prof.max_zoom_hd, min(prof.max_zoom_4k, short / 1080))


def _coerce(name: str, value, current):
    if isinstance(current, tuple):
        return tuple(float(x) for x in value)
    if isinstance(current, bool):
        return bool(value)
    if isinstance(current, int):
        return int(value)
    if isinstance(current, float):
        return float(value)
    return value


def make_profile(fmt: str = "reel", style: str = "ruhig-dicht", overrides: dict | None = None,
                 layout: str | None = None) -> Profile:
    fmt, style = (fmt or "reel").lower(), (style or "ruhig-dicht").lower()
    if fmt not in FORMATS:
        raise ValueError(f"format muss {' | '.join(FORMATS)} sein, nicht {fmt!r}")
    if style not in STYLES:
        raise ValueError(f"style muss {' | '.join(STYLES)} sein, nicht {style!r}")
    p = replace(Profile(), format=fmt, style=style, **FORMAT_DEFAULTS[fmt])
    if layout in ("reel", "youtube"):
        p = replace(p, layout=layout)
    sd = dict(STYLE_DEFAULTS[style])
    factor = sd.pop("keep_pause_ms_factor", None)
    p = replace(p, **sd)
    if factor:
        p = replace(p, keep_pause_ms=int(round(p.keep_pause_ms * factor)),
                    keep_pause_mid_ms=int(round(p.keep_pause_mid_ms * factor)))
    ov = dict(overrides or {})
    names = {f.name: f for f in fields(Profile)}
    common = {k: v for k, v in ov.items() if not isinstance(v, dict)}
    specific = ov.get(fmt, {}) if isinstance(ov.get(fmt), dict) else {}
    unknown = [k for k in list(common) + list(specific) if k not in names or k in ("format", "style", "layout")]
    if unknown:
        raise ValueError(f"unbekannte Profil-Parameter in config.toml: {', '.join(sorted(set(unknown)))}")
    for src in (common, specific):
        p = replace(p, **{k: _coerce(k, v, getattr(p, k)) for k, v in src.items()})
    return p


def profile_text(p: Profile) -> str:
    rng = lambda t: f"{t[0]:g}–{t[1]:g}"
    return (f"Profil {p.format}/{p.style}: Restpause {p.keep_pause_ms} ms (im Satz {p.keep_pause_mid_ms} ms), Beat key "
            f"{p.deliberate_pause_ms} ms, section {p.beat_section_ms} ms, "
            f"Lücken > {p.tighten_gaps_over_ms} ms kürzen, Atmer {'behalten' if p.keep_breaths else 'raus'}, "
            f"Punch-in {p.punch_in_scale:g} (ab und zu {'/'.join(f'{v:g}' for v in p.punch_in_variation)}, Akzent "
            f"{p.accent_scale:g}, Wechsel: {p.punch_in_rule}), "
            f"Wechsel alle {rng(p.change_every_s)} s, max. {p.max_unchanged_s:g} s ohne Wechsel, Hook {p.hook_s:g} s, "
            f"Laufzeit {rng(p.runtime_s)} s, B-Roll {p.broll_min_s:g}–{p.broll_max_s:g} s, "
            f"Kapitel {'ja' if p.chapters else 'nein'}, Lautheit {p.target_lufs:g} LUFS / TP ≤ {p.true_peak_max:g} dBTP, SRT ≤ {p.srt_max_words} Wörter")
