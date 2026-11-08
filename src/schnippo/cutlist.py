"""Cutlist (Claude references word IDs only) → cut plan in source frames.

Cut-point rules (all times from the analysed transcript, i.e. clamped word edges):
  start = max(end of previous sound + 20 ms, first word start − pre_pad)
  end   = min(last word end + post_pad, start of next sound − 20 ms)
  "sound" = any ASR token or voiced gap event ({?}); breaths are no boundary, so a breath right before a
  sentence may stay inside the pre-roll, but the pre-roll is never extended to include it.
Inside an item, gaps > tighten_gaps_over_ms – and with cut_fillers every gap holding a {?} or ASR filler –
are cut out; keep_pause_ms of the pause remains (head part capped at pre_pad). The item becomes several pieces.
Frames: start floored, end ceiled, endFrame exclusive (Phase-0 finding). Grid = Resolve's clip FPS if known.
"""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .formatting import parse_word_ref, ts
from .models import AnalyzedTranscript, Clip, Word

EPS = 0.02
SENTENCE_END = re.compile(r"[.!?…]$")


class CutOptions(BaseModel):
    pre_pad_ms: int = 80
    post_pad_ms: int = 120
    tighten_gaps_over_ms: int = 350
    keep_pause_ms: int = 150  # remaining pause at a sentence end (also at item ends, if the original pause is that long)
    keep_pause_mid_ms: int | None = None  # remaining pause inside a sentence; None = keep_pause_ms
    beat_key_ms: int = 400  # natural pause kept after a beat "key" (never more than the original pause)
    beat_section_ms: int = 400  # ... after a beat "section"
    plan_version: int = 2  # 1 = cut points as before Phase 8.5 (cutlists of older timelines keep planning identically)
    decay_max_ms: int = 200  # follow the decay of a last word at most this long (reel 200, long formats 350)
    edge_db: float = 12.0  # an edge is clean when the level in its last/first 10 ms is below noise floor + this
    cut_fillers: bool = True
    # motion-aware cut points: inside the allowed window pick the nearest calm frame instead of a mid-gesture one
    motion_aware_cuts: bool = True
    motion_extend_pre_ms: int = 500  # window: a piece may start at most this much earlier than the padded default
    motion_extend_post_ms: int = 300  # ... and end at most this much later
    max_motion_shift_ms: int = 200  # tempo guard: the motion rule moves a cut by at most this much
    motion_min_pre_ms: int = 40  # never closer than this to the voiced start of the first word
    motion_min_post_ms: int = 40
    motion_trigger_factor: float = 4.0  # only move a cut whose default frames are above factor x clip median
    motion_quiet_factor: float = 2.5  # target: nearest frame with motion <= factor x clip median
    motion_flag_factor: float = 6.0  # validate_cutlist flags cuts above factor x clip median
    keep_breaths: bool = False  # style ruhig: a breath right before a new sentence stays when the gap is cut
    broll_slowmo: str = Field("off", pattern="^(off|auto)$")  # auto: video B-roll with ≥ 2× timeline fps plays at 50 % (item retime only)


class CutItem(BaseModel):
    clip: str
    from_word: str
    to_word: str
    note: str = ""
    zoom: float | None = None  # optional punch-in override for all pieces of this item (e.g. 1.25 on a punchline)
    start_frame: str | None = None  # optional explicit first frame, e.g. "c01:f0114" (chosen from a contact sheet)
    end_frame: str | None = None  # optional explicit last shown frame (inclusive), e.g. "c01:f0190"
    pause_after_ms: int | None = None  # deliberate pause kept after the last word (key statement / before a punchline)
    beat: str | None = None  # key | section: the last word of this item ends a key statement / a section (see Beat)
    pan: float | None = None  # as set by hand in Resolve (with zoom); None = from the face position
    tilt: float | None = None

    @field_validator("beat")
    @classmethod
    def _beat(cls, v):
        if v is not None and v not in ("key", "section"):
            raise ValueError("beat: key | section")
        return v


class ManualItem(BaseModel):
    """A clip the user put on the timeline by hand: no words behind it (B-roll without speech, foreign clips, own graphics).
    Put back exactly at every rebuild and left alone otherwise, unless the user asks for a change."""
    kind: Literal["manual"] = "manual"
    media: str  # file path in the Media Pool
    name: str = ""
    source_in_frame: int
    source_out_frame: int  # exclusive, source frames
    track: int = 1
    track_type: Literal["video", "audio"] = "video"
    record_frame: int  # timeline frame (from timeline start) when it was adopted
    frames: int  # length on the timeline
    fps: float | None = None  # of the media, when it differs from the timeline
    with_audio: bool = False  # video with its linked sound
    audio_track: int | None = None
    anchor: tuple[str, int] | None = None  # (clip, source frame) on V1 it belongs to: under its start, on V1 the last frame before it
    properties: dict = Field(default_factory=dict)  # ZoomX, Pan, AudioVolume ... as read from Resolve
    note: str = ""


class Beat(BaseModel):
    """Key statement, punchline (key) or end of a section (section) after word `after`: the natural pause stays."""
    after: str  # "c01:w0330"
    beat: str = "key"
    note: str = ""

    @field_validator("beat")
    @classmethod
    def _beat(cls, v):
        if v not in ("key", "section"):
            raise ValueError("beat: key | section")
        return v


class ItemChange(BaseModel):
    """Change single items of the base cutlist (1-based index) without repeating the whole list."""
    index: int
    beat: str | None = None
    start_frame: str | None = None
    end_frame: str | None = None
    zoom: float | None = None
    pause_after_ms: int | None = None
    note: str | None = None


class Rejected(BaseModel):
    segment: str  # "c01:s003"
    reason: str = ""

    @field_validator("segment")
    @classmethod
    def _seg(cls, v: str) -> str:
        if not re.fullmatch(r"c\d+:s\d{3}", v.strip()):
            raise ValueError(f"segment must look like c01:s003, got {v!r}")
        return v.strip()


class Overlay(BaseModel):
    """B-roll on an upper track over a word range of the finished cut (positions computed by the server)."""
    media: str  # i03 (still) or c05 (video B-roll clip, from_frame required)
    from_word: str  # "c01:w0082"
    to_word: str
    track: int = 2
    slowmo: bool | None = None  # video B-roll ≥ 2× timeline fps: 50 % speed (item retime, frame-exact 50 → 25)
    audio: str = "mute"  # video B-roll: mute (default) | atmo (own track, −20 dB)
    fit: str = "fill"  # fill | fit
    focus: str = "center"  # center | left | right | top | bottom
    focus_x: float | None = None  # reel: horizontal centre of the crop, 0–1 (default: where the picture has the most going on)
    motion: str = "none"  # none | slow_zoom_in | slow_zoom_out | pan_left | pan_right
    from_frame: str | None = None
    to_frame: str | None = None
    tail: bool = False  # covers the silent run-out of the item after to_word (item end_frame) – e.g. a closing scene
    note: str = ""

    @field_validator("fit")
    @classmethod
    def _fit(cls, v):
        if v not in ("fill", "fit"):
            raise ValueError("fit: fill | fit")
        return v

    @field_validator("focus")
    @classmethod
    def _focus(cls, v):
        if v not in ("center", "left", "right", "top", "bottom"):
            raise ValueError("focus: center | left | right | top | bottom")
        return v

    @field_validator("motion")
    @classmethod
    def _motion(cls, v):
        if v not in ("none", "slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right"):
            raise ValueError("motion: none | slow_zoom_in | slow_zoom_out | pan_left | pan_right")
        return v


class Reframe(BaseModel):
    """Reel from the long version (Phase 10): 16:9 material in a 9:16 timeline, the crop follows the face."""
    width: int = 1080
    height: int = 1920
    source_timeline: str | None = None
    number: int = 1
    title: str = ""
    layout: Literal["full", "framed"] = "full"  # full: fills 9:16 | framed: video as 1:1 or 4:5 in the middle on a calm plate, never scaled above 1.0
    aspect: Literal["1:1", "4:5"] = "1:1"  # framed only
    two_speaker_layout: str = "follow"  # follow | stacked (stacked is not implemented, see NOTES)
    speaker_x: dict[str, float] = Field(default_factory=dict)  # two people in one picture: speaker → horizontal position 0–1
    min_s: float = 10.0
    max_s: float = 60.0


class Graphic(BaseModel):
    """Motion graphic (pass 5) over a word range of the finished cut (or duration_ms from from_word)."""
    template: str | None = None  # hook_text | callout | counter | list_steps | lower_third | underline_arrow
    params: dict = Field(default_factory=dict)
    from_word: str
    to_word: str | None = None
    duration_ms: int | None = None
    track: int = 3
    expressive: bool = False  # expressive curves/lengths: max 2 per video
    html: str | None = None  # sandbox mode only (free HTML with the seek contract)
    note: str = ""


class PlacedGraphic(BaseModel):
    index: int
    template: str
    params: dict
    track: int
    tl_start: int
    tl_end: int
    words: tuple[str, str]
    expressive: bool = False
    face: tuple[float, float, float, float] | None = None  # worst-case HEAD box (union over the span), timeline px x, y, w, h
    heads: list = Field(default_factory=list)  # head boxes every few frames (timeline px), punch-in applied
    html: str | None = None
    note: str = ""
    snap: dict = Field(default_factory=dict)

    @property
    def frames(self) -> int:
        return self.tl_end - self.tl_start


class PlacedOverlay(BaseModel):
    index: int
    media: str
    track: int
    tail: bool = False  # sits on the silent run-out after the last word
    tl_start: int  # timeline frame offset from timeline start
    tl_end: int  # exclusive
    words: tuple[str, str]
    fit: str
    focus: str
    motion: str
    note: str = ""
    snap: dict = Field(default_factory=dict)  # orig span, frames moved, gaps to the cuts (snap.py)
    kind: str = "still"  # still | video
    src_start: int | None = None  # video: first source frame (clip fps)
    src_frames: int | None = None  # video: source frames to append (duration = frames × tl_fps / clip fps)
    speed: float = 1.0  # video: 0.5 = slow motion (SetSpeed on the timeline item, clip attributes untouched)
    audio: str = "mute"
    fill_video: bool = False  # reel: Scaling = Fill, the crop at pan
    pan: float = 0.0
    focus_x: float | None = None

    @property
    def frames(self) -> int:
        return self.tl_end - self.tl_start


class SfxCue(BaseModel):
    """Sound effect on an event (guides/06_sound_design.md): at = G1 (graphic), O2 (overlay) or c01:w0123 (word)."""
    category: str | None = None  # whoosh | swish | pop | tick | ding | impact_soft | riser
    file: str | None = None  # id or file name from list_sfx instead of a category
    at: str
    event: str | None = None  # in | end (graphic: box opens | counter reaches its value); default end for tick/ding on a graphic
    intensity: int | None = None  # 1–3; default from sfx mode and design language
    gain_db: float | None = None  # below the voice; default from category, mode and design language
    duration_ms: int | None = None  # beds and sequences (atmo, ticking, typing): length; default = the element at "at"
    deliberate: bool = False  # on purpose over the hook sentence or the CTA
    note: str = ""


class PlacedSfx(BaseModel):
    index: int
    id: str
    category: str
    file: str
    at: str
    event: str
    what: str = ""
    event_frame: int  # timeline frame the transient is aligned to
    tl_start: int
    frames: int
    hit_ms: int
    audible_ms: int
    gain_db: float  # below the voice
    volume_db: float  # AudioVolume on the clip
    note: str = ""
    deliberate: bool = False
    target_end: int | None = None  # end of the graphic / overlay
    license: str = ""
    credit: str = ""  # attribution the licence asks for
    kind: str = "oneshot"  # oneshot | bed | sequence
    align: str = "transient"  # start | transient | end: what lies on the event
    length_ms: int | None = None  # beds and sequences: cut or looped to this length
    under_overlay: bool = False


class PunchIn(BaseModel):
    mode: str = "alternate"  # alternate | off
    scale: float | None = None  # None → profile (112–120 %)
    rule: str | None = None  # sentence | sentence_no_repeat | every; None → profile (style)
    min_hold_s: float | None = None  # a zoom level stands at least this long before it may change again; None → profile
    variation: list[float] | None = None  # occasional levels instead of `scale`; None → profile, [] = none
    variation_every: int | None = None  # every n-th punch-in takes a variation level; None → profile

    @field_validator("mode")
    @classmethod
    def _mode(cls, v):
        if v not in ("alternate", "off"):
            raise ValueError("punch_in.mode: alternate | off")
        return v

    @field_validator("rule")
    @classmethod
    def _rule(cls, v):
        if v is not None and v not in ("sentence", "sentence_no_repeat", "every"):
            raise ValueError("punch_in.rule: sentence | sentence_no_repeat | every")
        return v


class Correction(BaseModel):
    word: str  # "c01:w0113"
    text: str


class AudioOptions(BaseModel):
    """Non-destructive audio finishing in Resolve (clip volume + Fairlight FX), verified by a check render."""
    normalize: bool = True
    target_lufs: float = -14.0
    tolerance_lu: float = 0.5
    true_peak_max: float = -1.0
    limiter: bool = True
    deesser: str = "auto"  # auto (only if sibilance measured > +4 dB) | on | off
    dialogue_leveler: bool = False
    voice_isolation: bool = False
    max_iterations: int = 3
    tp_strategy: str = "post_compressor"  # post_compressor (Limiter → Multiband Compressor, TP ≈ −2.8) | limiter_only
    post_compressor_offset_db: float = 6.0  # first gain guess: the compressor lowers the loudness by about this much

    @field_validator("tp_strategy")
    @classmethod
    def _tps(cls, v):
        if v not in ("post_compressor", "limiter_only"):
            raise ValueError("audio.tp_strategy: post_compressor | limiter_only")
        return v


class Cutlist(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    name: str | None = None  # project name → timeline <name>_V1_Rough … _V4_Polish
    pass_: str | None = Field(default=None, alias="pass")  # rough | fine | broll | polish (None = no pass rules)
    base_cutlist: str | dict | None = None  # timeline name of the previous pass (or an inline cutlist)
    format: str | None = None  # override of the configured profile (reel | youtube | course | commercial)
    style: str | None = None  # ruhig | ruhig-dicht | dicht
    timeline_name: str = "RC_v1"
    items: list[CutItem] = Field(default_factory=list)
    item_changes: list[ItemChange] = Field(default_factory=list)
    rejected: list[Rejected] = Field(default_factory=list)
    options: CutOptions = Field(default_factory=CutOptions)
    overlays: list[Overlay] = Field(default_factory=list)
    beats: list[Beat] = Field(default_factory=list)  # key statements / section ends inside items (fine cut)
    audio: AudioOptions | None = None
    punch_in: PunchIn | None = None
    subtitles: dict | None = None  # removed in Phase 5 (subtitles come from the platform; see export_transcript)
    corrections: list[Correction] = Field(default_factory=list)
    graphics: list[Graphic] = Field(default_factory=list)
    reframe: Reframe | None = None  # reel from a long version
    sfx: list[SfxCue] = Field(default_factory=list)  # also accepts the mode: "sfx": "off"
    sfx_mode: str | None = None  # off | subtil | normal (None = configuration)
    brand: str | None = None  # brand profile for graphics (design setup); None = active profile
    markers: bool = True
    alternates: bool = False
    revision_of: str | None = None  # timeline this is a revision of (revise / read_timeline_changes) → diff in validate
    manual: list[ManualItem] = Field(default_factory=list)  # hand edits without words, see ManualItem
    new_timeline: bool = False  # only when the user asks for a separate timeline; default: the working timeline

    @model_validator(mode="before")
    @classmethod
    def _sfx_mode(cls, data):
        if isinstance(data, dict) and isinstance(data.get("sfx"), str):
            data = {**data, "sfx_mode": data["sfx"]}
            del data["sfx"]
        return data


class Piece(BaseModel):
    item: int  # 1-based item index (0 = alternates)
    clip: str
    start_s: float
    end_s: float
    start_frame: int
    end_frame: int  # exclusive
    text: str
    word_ids: list[str] = Field(default_factory=list)
    start_shift: int = 0  # frames moved by the motion-aware rule (negative = earlier)
    end_shift: int = 0
    zoom: float = 1.0  # punch-in level of this piece
    fill: bool = False  # reel: Scaling = Fill, pan and tilt are the crop
    pan: float = 0.0
    tilt: float = 0.0
    start_motion: float | None = None  # motion score at the first / last frames (x clip median)
    end_motion: float | None = None
    decay_ms: int = 0  # end moved later by the decay of the last word
    onset_ms: int = 0  # start moved earlier to the real onset of the first word
    expressive: int = 0  # voiced sounds after a sentence end that stayed ({?}, hm, sigh)
    manual: bool = False  # from Cutlist.manual or a gap: no words, Schnippo does not change it
    gap: bool = False  # empty stretch on V1 (read back from a timeline only)
    tl_frames: int | None = None  # length on the timeline where it differs from the source frames

    @property
    def frames(self) -> int:
        return self.tl_frames if self.tl_frames is not None else self.end_frame - self.start_frame


class Plan(BaseModel):
    pieces: list[Piece] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    item_spans: list[tuple[str, int, int]] = Field(default_factory=list)  # (clip, from_n, to_n) per item
    overlays: list[PlacedOverlay] = Field(default_factory=list)
    graphics: list[PlacedGraphic] = Field(default_factory=list)
    sfx: list[PlacedSfx] = Field(default_factory=list)
    sfx_info: dict = Field(default_factory=dict)
    reframe: dict = Field(default_factory=dict)
    corrections: dict[str, str] = Field(default_factory=dict)
    beats: list[dict] = Field(default_factory=list)  # placed beats: word, kind, target/actual/original pause (s)
    hard_edges: list[dict] = Field(default_factory=list)  # edges above the noise floor: timeline time, side, level
    manual: list[dict] = Field(default_factory=list)  # hand-placed clips on upper/audio tracks: ManualItem fields + tl_start

    @property
    def ok(self) -> bool:
        return not self.errors

    def total_seconds(self, clips: dict) -> float:
        fps = next(((clips[p.clip].resolve_fps or clips[p.clip].fps) for p in self.pieces if not p.manual), None)
        return sum(p.frames / (fps or clips[p.clip].resolve_fps or clips[p.clip].fps) for p in self.pieces)


def _sounds(at: AnalyzedTranscript) -> list[Word]:
    return [e for e in at.entries if e.id[0] == "w" or (e.kind == "filler" and "inferred" in e.flags)]


MIN_CUT_S = 0.25
HESITATIONS = re.compile(r"^(ä+h+m*|ö+h+m*|e+h+m+|u+h+m*|um|erm)\W*$", re.I)


def _expressive(w: Word, f: Word | None, next_start: float) -> Word | None:
    """A voiced sound without a word, a "hm", a laugh or a sigh right after the end of a sentence (gap < 200 ms) belongs
    to the statement and stays. Not so a hesitation ("äh") or a sound that leads straight into the next words (restart)."""
    if f is None or not SENTENCE_END.search(w.text) or f.kind != "filler":
        return None
    if f.start_s - w.end_s >= 0.2 or next_start - f.end_s < 0.15 or HESITATIONS.match(f.text or ""):
        return None
    return f


def _choose(default: int, lo: int, hi: int, score, quiet: float, trigger: float, gain: float = 0.3) -> int:
    """If the default is restless (> trigger): nearest calm frame (<= quiet) within [lo, hi]; else the calmest if
    clearly better; else default."""
    if lo > hi:
        return default
    d = min(max(default, lo), hi)
    sd = score(d)
    if sd <= trigger:
        return default
    cands = sorted(range(lo, hi + 1), key=lambda k: (abs(k - d), k))
    for k in cands:
        if score(k) <= quiet:
            return k
    best = min(cands, key=lambda k: (score(k), abs(k - d)))
    return best if score(best) <= sd * (1 - gain) else d


def plan_item(idx: int, clip: Clip, at: AnalyzedTranscript, n0: int, n1: int, opt: CutOptions, fps: float,
              max_frame: int | None, motion=None, start_frame: int | None = None, end_frame: int | None = None,
              notes: list | None = None, pause_after_ms: int | None = None, beats: dict | None = None,
              ac=None) -> list[Piece]:
    from . import edges as ed
    natural = opt.plan_version >= 2 and ac is not None
    decay_max = opt.decay_max_ms / 1000
    pre, post = opt.pre_pad_ms / 1000, opt.post_pad_ms / 1000
    if pause_after_ms:
        post = max(post, pause_after_ms / 1000)
    keep, tighten = opt.keep_pause_ms / 1000, opt.tighten_gaps_over_ms / 1000
    keep_mid = keep if opt.keep_pause_mid_ms is None else opt.keep_pause_mid_ms / 1000

    def wanted(w) -> tuple[float, bool]:
        """(pause to keep after word w, is it a beat). Sentence end: keep; inside a sentence: keep_mid."""
        kind = (beats or {}).get(int(w.id[1:]))
        if kind:
            return (opt.beat_section_ms if kind == "section" else opt.beat_key_ms) / 1000, True
        return (keep if SENTENCE_END.search(w.text) else keep_mid), False

    ext_pre, ext_post = opt.motion_extend_pre_ms / 1000, opt.motion_extend_post_ms / 1000
    min_pre, min_post = opt.motion_min_pre_ms / 1000, opt.motion_min_post_ms / 1000
    if opt.plan_version >= 2:  # stretched words: {?} attached to a word belongs to it (not the analysis' business)
        ents = ed.unclamp(at.entries, ac) if ac is not None else at.entries
        at = at.model_copy(update={"entries": ed.merge_stretches(ents)})
    sounds = _sounds(at)
    tokens = [e for e in at.entries if e.id[0] == "w" and n0 <= int(e.id[1:]) <= n1]
    kept = [t for t in tokens if not (opt.cut_fillers and t.kind == "filler")] or tokens
    first, last = kept[0], kept[-1]
    prev_end = max((s.end_s for s in sounds if s.end_s <= first.start_s + 1e-6 and s is not first), default=-1.0)
    next_start = min((s.start_s for s in sounds if s.start_s >= last.end_s - 1e-6 and s is not last), default=1e9)
    start = max(prev_end + EPS, first.start_s - pre, 0.0)
    # item end: the rest pause (or the beat) minus the lead-in of the next piece; an original pause that is shorter stays
    pause_end, beat_end = wanted(last)
    tail_end = pause_end - min(pre, pause_end * 0.6)
    end_word = last.end_s  # where the sound of the item ends (a sound of expression after the sentence may follow)
    expr_end = 0
    if opt.plan_version >= 2:
        after = [x for x in sounds if x.start_s >= last.end_s - 1e-6 and x is not last]
        f = _expressive(last, after[0] if after else None, after[1].start_s if len(after) > 1 else 1e9)
        if f is not None:
            end_word, expr_end = f.end_s, 1
            next_start = after[1].start_s if len(after) > 1 else 1e9
    if opt.plan_version >= 2:
        end = min(end_word + max(post, tail_end), next_start - EPS, clip.duration_s)
    else:
        end = min(last.end_s + post, next_start - EPS, clip.duration_s)

    def faded(t_word: float, t_next: float, e: float) -> float:
        """End after the decay of the word that ends at t_word (never into the next word)."""
        if not natural:
            return e
        return max(e, ed.decay_end(ac, t_word, min(t_word + decay_max, t_next - ed.GUARD_S, clip.duration_s)))

    def begun(t_word: float, t_prev: float, s: float) -> float:
        """Start before the real onset of the word that starts (per ASR) at t_word."""
        if not natural:
            return s
        lim = max(t_word - ed.ONSET_MAX_S, t_prev + ed.GUARD_S, 0.0)
        return min(s, max(ed.onset_start(ac, t_word, lim) - ed.GUARD_S, lim))

    start0, end0 = start, end
    start, end = begun(first.start_s, prev_end, start), faded(end_word, next_start, end)

    # span: start, end, words, (start window lo, hi), (end window lo, hi) – windows never reach into a word/filler
    spans: list[dict] = [{"s": start, "e": None, "w": [first], "sw": (max(prev_end + EPS, start - ext_pre, 0.0),
                                                                      min(start, first.start_s - min_pre) if natural else first.start_s - min_pre),
                          "onset": round((start0 - start) * 1000), "first_w": first, "t_prev": prev_end}]
    for a, b in zip(kept, kept[1:]):
        gap = b.start_s - a.end_s
        fillers = [s for s in sounds if s.start_s >= a.end_s - 1e-6 and s.end_s <= b.start_s + 1e-6
                   and s is not a and s is not b] + [t for t in tokens if t.kind == "filler" and a.end_s <= t.start_s < b.start_s]
        pause, is_beat = wanted(a)
        head = min(pre, pause * 0.6)
        tail = pause - head
        a_end, expr = a.end_s, 0
        if opt.plan_version >= 2 and fillers:  # a sound of expression right after the sentence belongs to the statement
            fs = sorted(fillers, key=lambda x: x.start_s)
            f0 = _expressive(a, fs[0], fs[1].start_s if len(fs) > 1 else b.start_s)
            if f0 is not None:
                a_end, expr, fillers = f0.end_s, 1, fs[1:]
        if (gap > pause if is_beat else gap > tighten) or (opt.cut_fillers and fillers):
            e1, s2 = a_end + tail, b.start_s - head
            e_hi, s_lo = b.start_s - min_pre, a_end + min_post
            if fillers:
                e1 = min(e1, min(f.start_s for f in fillers) - EPS)
                s2 = max(s2, max(f.end_s for f in fillers) + EPS)
                e_hi, s_lo = min(f.start_s for f in fillers) - EPS, max(f.end_s for f in fillers) + EPS
            e_plain, s_plain = e1, s2
            next_sound = min([f.start_s for f in fillers] + [b.start_s])
            prev_sound = max([f.end_s for f in fillers] + [a_end])
            e1 = faded(a_end, next_sound, e1)
            s2 = begun(b.start_s, prev_sound, s2)
            if opt.keep_breaths and SENTENCE_END.search(a.text):
                breaths = [e for e in at.entries if e.kind == "breath" and e.start_s >= a.end_s - 1e-6
                           and e.end_s <= b.start_s + 1e-6 and b.start_s - e.start_s <= 1.0]
                if breaths:  # keep the natural breath before the new sentence (style ruhig)
                    s2 = min(s2, breaths[0].start_s - EPS)
                    s_lo = min(s_lo, s2)
            e1, s2 = max(e1, a.end_s), min(s2, b.start_s)
            # only cut if something is actually removed; without a filler, saving under 0.25 s of silence is not worth a jump
            # cut (Phase 8.5: such cuts took the quiet start of the next word with them, "am Ozean")
            if s2 - e1 > (MIN_CUT_S if opt.plan_version >= 2 and not fillers else 1.5 / fps):
                spans[-1]["e"] = e1
                spans[-1]["ew"] = (e1 if natural else a.end_s + min_post, min(e1 + ext_post, e_hi))
                spans[-1]["lock_e"] = is_beat  # the pause of a beat is not traded for a calmer frame
                spans[-1].update(decay=round((e1 - e_plain) * 1000), expr=expr, t_word=a_end, t_next=next_sound)
                spans.append({"s": s2, "e": None, "w": [], "sw": (max(s2 - ext_pre, s_lo),
                                                                  s2 if natural else b.start_s - min_pre),
                              "lock_s": is_beat, "onset": round((s_plain - s2) * 1000), "first_w": b, "t_prev": prev_sound})
        spans[-1]["w"].append(b)
    spans[-1]["e"] = end
    spans[-1]["ew"] = (end if natural else last.end_s + min_post, min(end + ext_post, next_start - EPS, clip.duration_s))
    spans[-1]["lock_e"] = beat_end
    spans[-1].update(decay=round((end - end0) * 1000), expr=expr_end, t_word=end_word, t_next=next_start)

    use_motion = opt.motion_aware_cuts and motion is not None and len(motion) > 2
    if use_motion:
        import numpy as np

        med = max(float(np.median(motion[1:])), 0.05)
        n = len(motion)
        mv = lambda k: float(motion[min(max(k, 0), n - 1)]) / med
        s_score = lambda k: max(mv(k), mv(k + 1))  # first two shown frames
        e_score = lambda ef: max(mv(ef - 1), mv(ef - 2))  # last two shown frames
        quiet = opt.motion_quiet_factor

    pieces: list[Piece] = []
    for sp in spans:
        s, e, words = sp["s"], sp["e"], sp["w"]
        sf0, ef0 = math.floor(s * fps + 1e-9), math.ceil(e * fps - 1e-9)
        sf, ef = sf0, ef0
        first_span, last_span = sp is spans[0], sp is spans[-1]
        if use_motion:
            trig = opt.motion_trigger_factor
            cap = round(opt.max_motion_shift_ms / 1000 * fps)
            slo, shi = math.ceil(sp["sw"][0] * fps - 1e-9), math.floor(sp["sw"][1] * fps + 1e-9)
            elo, ehi = math.ceil(sp["ew"][0] * fps - 1e-9), math.floor(sp["ew"][1] * fps + 1e-9)
            if not sp.get("lock_s"):
                sf = _choose(sf0, max(slo, sf0 - cap), min(shi, sf0 + cap), s_score, quiet, trig)
            if not sp.get("lock_e"):
                ef = _choose(ef0, max(elo, ef0 - cap), min(ehi, ef0 + cap), e_score, quiet, trig)
        explicit_s = first_span and start_frame is not None
        explicit_e = last_span and end_frame is not None
        if explicit_s:
            word0 = math.floor(sp["w"][0].start_s * fps + 1e-9)
            if start_frame > word0:
                raise ValueError(f"start_frame f{start_frame:04d} schneidet das erste Wort an (beginnt bei f{word0:04d})")
            lo = math.ceil(sp["sw"][0] * fps - 1e-9)
            if notes is not None and start_frame < lo:
                notes.append(f"start_frame f{start_frame:04d} liegt vor dem erlaubten Fenster (ab f{lo:04d}) – enthält Ton des vorherigen Worts/Füllworts")
            sf = start_frame
        if explicit_e:
            wordn = math.ceil(sp["w"][-1].end_s * fps - 1e-9)
            if end_frame + 1 < wordn:
                raise ValueError(f"end_frame f{end_frame:04d} schneidet das letzte Wort an (endet bei f{wordn:04d})")
            hi = math.floor(sp["ew"][1] * fps + 1e-9)
            if notes is not None and end_frame + 1 > hi:
                last = sp["w"][-1]
                after = [e for e in at.entries if e.start_s >= last.end_s - 1e-6 and e.start_s < (end_frame + 1) / fps
                         and (e.kind in ("word", "filler", "breath") or e.id.startswith("u"))]
                if after:  # a pure pause after the last word is a clean run-out (closing scene), no warning
                    what = "Atmer" if all(e.kind == "breath" for e in after) else "Ton des nächsten Worts"
                    notes.append(f"end_frame f{end_frame:04d} liegt hinter dem erlaubten Fenster (bis f{hi - 1:04d}) – enthält {what}")
            ef = end_frame + 1
        if natural:  # edge check: the last/first 10 ms should be close to the noise floor; if not, move the cut
            if not explicit_e and not ed.is_quiet(ac, ef, fps, "end", opt.edge_db):
                # room: never inside the sound of the word, i.e. not before its decay (the signal, not the word time)
                lim = min(sp["t_next"] - ed.GUARD_S, clip.duration_s, sp["t_word"] + 2 * decay_max)
                lo = ed.frames(ed.decay_end(ac, sp["t_word"], min(lim, sp["t_word"] + decay_max)), fps, True)
                hi = ed.frames(lim, fps, False)
                ef = ed.nearest_quiet(ac, ef, fps, "end", opt.edge_db, lo, hi) or ed.quietest(ac, ef, fps, "end", lo, hi) or ef
            if not explicit_s and not ed.is_quiet(ac, sf, fps, "start", opt.edge_db):
                w0 = sp["first_w"]
                lo = ed.frames(max(sp["t_prev"] + ed.GUARD_S, w0.start_s - 2 * ed.ONSET_MAX_S, 0.0), fps, True)
                onset = ed.onset_start(ac, w0.start_s, max(w0.start_s - ed.ONSET_MAX_S, sp["t_prev"] + ed.GUARD_S, 0.0))
                hi = ed.frames(onset - ed.GUARD_S, fps, False)
                sf = ed.nearest_quiet(ac, sf, fps, "start", opt.edge_db, lo, hi) or ed.quietest(ac, sf, fps, "start", lo, hi) or sf
        if max_frame is not None:
            ef = min(ef, max_frame)
        if pieces and sf < pieces[-1].end_frame and use_motion:  # motion moved two cuts into each other → defaults
            sf = max(sf0, pieces[-1].end_frame)
        if pieces and sf <= pieces[-1].end_frame:  # rounding made them touch → merge
            p = pieces[-1]
            pieces[-1] = p.model_copy(update={"end_s": round(e if ef == ef0 else ef / fps, 3), "end_frame": max(ef, p.end_frame),
                                              "end_shift": ef - ef0,
                                              "end_motion": round(e_score(ef), 1) if use_motion else None,
                                              "text": p.text + " " + " ".join(w.text for w in words),
                                              "word_ids": p.word_ids + [w.id for w in words]})
            continue
        if ef > sf:
            pieces.append(Piece(item=idx, clip=clip.id, start_s=round(s if sf == sf0 else sf / fps, 3),
                                end_s=round(e if ef == ef0 else ef / fps, 3), decay_ms=max(0, sp.get("decay", 0)),
                                onset_ms=max(0, sp.get("onset", 0)), expressive=sp.get("expr", 0),
                                start_frame=sf, end_frame=ef, text=" ".join(w.text for w in words),
                                word_ids=[w.id for w in words],
                                start_shift=0 if explicit_s else sf - sf0, end_shift=0 if explicit_e else ef - ef0,
                                start_motion=round(s_score(sf), 1) if (use_motion or explicit_s) and motion is not None else None,
                                end_motion=round(e_score(ef), 1) if (use_motion or explicit_e) and motion is not None else None))
    return pieces


def build_plan(cl: Cutlist, clips: dict[str, Clip], analyzed: dict[str, AnalyzedTranscript],
               segments: dict[str, list] | None = None, motions: dict | None = None, stills: set[str] | None = None,
               faces: dict | None = None, prof=None, tok: dict | None = None, sandbox: bool = False,
               acoustics: dict | None = None, sfx_opts: dict | None = None, reframe_opts: dict | None = None) -> Plan:
    plan = Plan()
    used: dict[str, list[tuple[int, int, int]]] = {}
    last_pos: dict[str, int] = {}
    beat_map: dict[str, dict[int, str]] = {}  # clip → word number → key | section
    for b in cl.beats:
        try:
            bc, bn = _word_ref(b.after)
            beat_map.setdefault(bc, {})[bn] = b.beat
        except ValueError as e:
            plan.errors.append(f"Beat: {e}")
    for it in cl.items:
        if it.beat:
            beat_map.setdefault(it.clip.strip().lower(), {})[int(it.to_word[1:])] = it.beat
    for i, it in enumerate(cl.items, 1):
        cid = it.clip.strip().lower()
        if cid not in clips:
            plan.errors.append(f"#{i}: unbekannter Clip {it.clip!r}")
            continue
        at = analyzed.get(cid)
        if at is None:
            plan.errors.append(f"#{i}: {cid} hat kein Transkript")
            continue
        try:
            n0, n1 = parse_word_ref(it.from_word), parse_word_ref(it.to_word)
        except ValueError as e:
            plan.errors.append(f"#{i}: {e}")
            continue
        ids = {int(e.id[1:]) for e in at.entries if e.id[0] == "w"}
        bad = [w for w, n in ((it.from_word, n0), (it.to_word, n1)) if n not in ids]
        if bad:
            plan.errors.append(f"#{i}: Wort-ID(s) {', '.join(bad)} existieren in {cid} nicht (w0001–w{max(ids):04d})")
            continue
        if n0 > n1:
            plan.errors.append(f"#{i}: from_word {it.from_word} liegt nach to_word {it.to_word}")
            continue
        for j, a, b in used.get(cid, []):
            if n0 <= b and a <= n1:
                plan.errors.append(f"#{i}: überlappt mit #{j} ({cid} w{max(a, n0):04d}–w{min(b, n1):04d} doppelt verwendet)")
        if cid in last_pos and n0 < last_pos[cid] and not (i == 2 and "cold open" in (cl.items[0].note or "").lower()):
            plan.warnings.append(f"#{i}: springt in der Aufnahme zurück (vor #{i - 1}) – nur mit Skript-Reihenfolge, bestätigter "
                                 f"Szenenfolge oder als Cold Open (#1, note „Cold Open“) sinnvoll")
        used.setdefault(cid, []).append((i, n0, n1))
        last_pos[cid] = n1
        plan.item_spans.append((cid, n0, n1))
        clip = clips[cid]
        fps = clip.resolve_fps or clip.fps
        max_frame = clip.resolve_frames or (clip.nb_frames if not clip.vfr else None)
        try:
            sfx = _frame_of(it.start_frame, cid) if it.start_frame else None
            efx = _frame_of(it.end_frame, cid) if it.end_frame else None
            notes: list[str] = []
            new = plan_item(i, clip, at, n0, n1, cl.options, fps, max_frame, (motions or {}).get(cid), sfx, efx, notes,
                            it.pause_after_ms, beat_map.get(cid), (acoustics or {}).get(cid))
            if plan.pieces and new and cl.options.plan_version >= 2:
                prev = plan.pieces[-1]  # items next to each other in the source: the run-out ends where the next piece starts
                if prev.clip == new[0].clip and prev.start_frame < new[0].start_frame < prev.end_frame:
                    prev.end_frame = new[0].start_frame
            plan.pieces += new
            plan.warnings += [f"#{i}: {n}" for n in notes]
        except ValueError as e:
            plan.errors.append(f"#{i}: {e}")
    # timeline-level overlap check (same clip, frame ranges)
    for a, b in zip(plan.pieces, plan.pieces[1:]):
        if a.clip == b.clip and a.item != b.item and b.start_frame < a.end_frame and b.end_frame > a.start_frame:
            plan.errors.append(f"#{a.item}/#{b.item}: Teilstücke überlappen im Quellmaterial ({a.clip} Frames "
                               f"{b.start_frame}–{a.end_frame})")
    measure_beats(cl, plan, clips, analyzed, beat_map)
    check_edges(cl, plan, clips, acoustics or {})
    splice_manual(cl, plan, clips)
    place_overlays(cl, plan, clips, analyzed, stills, prof)
    assign_zooms(cl, plan, clips, faces or {}, prof)
    if cl.reframe is not None:
        from . import reframe as rfm
        rfm.apply(cl, plan, clips, analyzed, faces or {}, reframe_opts)
        rfm.place_overlays(cl, plan, clips, (reframe_opts or {}).get("focus"))
    place_graphics(cl, plan, clips, analyzed, faces, prof, tok, sandbox)
    if sfx_opts is not None:
        from .sfx import place as place_sfx
        place_sfx(cl, plan, clips, analyzed, prof, tok, sfx_opts)
    for c in cl.corrections:
        try:
            cid, n = _word_ref(c.word)
        except ValueError as e:
            plan.errors.append(f"Korrektur: {e}")
            continue
        at = analyzed.get(cid)
        if at is None or not any(e.id == f"w{n:04d}" for e in at.entries):
            plan.errors.append(f"Korrektur: Wort {c.word} unbekannt")
            continue
        plan.corrections[f"{cid}:w{n:04d}"] = c.text
    if cl.subtitles is not None:
        plan.warnings.append("„subtitles“ wird ignoriert: Untertitel kommen nicht mehr in die Resolve-Timeline – "
                             "SRT/TXT mit export_transcript erzeugen (Untertitel setzt Instagram/Edits)")
    if segments is not None:
        known = {s.ref for segs in segments.values() for s in segs}
        for r in cl.rejected:
            if r.segment not in known:
                plan.errors.append(f"rejected: unbekanntes Segment {r.segment}")
    return plan


def first_piece(plan: Plan) -> Piece:
    """The first piece of real material: a hand-placed clip may lead the timeline and has its own frame rate."""
    return next((p for p in plan.pieces if not p.manual), plan.pieces[0])


GAP = "gap"  # pseudo clip of an empty stretch on V1


def manual_id(path: str) -> str:
    """Stable id for media that is no clip of the folder."""
    import hashlib
    return "m" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:8]


def manual_clip_id(m: ManualItem, clips: dict[str, Clip]) -> str:
    return next((cid for cid, c in clips.items() if c.path == m.media), manual_id(m.media))


def _position(pieces: list[Piece], clip: str, frame: int) -> int | None:
    """Timeline frame of a source frame of the cut, None if it is no longer in it."""
    rec = 0
    for p in pieces:
        if p.clip == clip and not p.gap and p.start_frame <= frame < p.end_frame:
            return rec + frame - p.start_frame
        rec += p.frames
    return None


def splice_manual(cl: Cutlist, plan: Plan, clips: dict[str, Clip]) -> None:
    """Hand-placed clips back into the plan: on V1 behind the frame they followed, on other tracks over the frame they lay on.
    When that frame was cut away, the position it had is the best there is, and the plan says so."""
    if not cl.manual:
        return
    v1 = sorted([m for m in cl.manual if m.track == 1 and m.track_type == "video"], key=lambda m: m.record_frame)
    for m in v1:
        cid = GAP if not m.media else manual_clip_id(m, clips)
        if cid not in clips:
            plan.errors.append(f"Handänderung „{m.name or m.media}“: Medium unbekannt")
            continue
        piece = Piece(item=0, clip=cid, start_s=0.0, end_s=0.0, start_frame=m.source_in_frame, end_frame=m.source_out_frame, text="", manual=True,
                      gap=not m.media, tl_frames=m.frames, zoom=float(m.properties.get("ZoomX") or 1.0))
        k = 0
        if m.anchor is not None:
            hit = next((j for j, p in enumerate(plan.pieces) if p.clip == m.anchor[0] and not p.gap and p.start_frame <= m.anchor[1] < p.end_frame), None)
            if hit is None:
                rec, k = 0, 0
                for j, p in enumerate(plan.pieces):
                    if rec >= m.record_frame:
                        break
                    rec += p.frames
                    k = j + 1
                plan.warnings.append(f"Handänderung „{m.name}“: die Stelle davor ist nicht mehr im Schnitt, bleibt bei Position {m.record_frame}")
            else:
                k = hit + 1
        plan.pieces.insert(k, piece)
    for m in cl.manual:
        if m.track == 1 and m.track_type == "video":
            continue
        at = None if m.anchor is None else _position(plan.pieces, m.anchor[0], m.anchor[1])
        if at is None:
            at = m.record_frame
            if m.anchor is not None:
                plan.warnings.append(f"Handänderung „{m.name}“: der Schnitt darunter ist weg, bleibt bei Position {m.record_frame}")
        plan.manual.append({**m.model_dump(), "tl_start": at})


def plan_text(cl: Cutlist, plan: Plan, clips: dict[str, Clip]) -> str:
    fps_of = lambda cid: (clips[cid].resolve_fps or clips[cid].fps) if cid in clips else 30.0
    total_frames = sum(p.frames for p in plan.pieces)
    total_s = plan.total_seconds(clips)
    raw_s = sum(clips[c].duration_s for c in {p.clip for p in plan.pieces} if c in clips)
    out = [f"Cutlist „{cl.timeline_name}“: {len(cl.items)} Items → {len(plan.pieces)} Teilstücke, "
           f"{ts(total_s)} ({total_frames} Frames)" + (f" | Rohmaterial {ts(raw_s)}, −{100 - 100 * total_s / raw_s:.0f} %" if raw_s else "")
           + (" | GÜLTIG" if plan.ok else " | UNGÜLTIG")]
    for e in plan.errors:
        out.append(f"FEHLER {e}")
    for w in plan.warnings:
        out.append(f"Warnung {w}")
    for i, it in enumerate(cl.items, 1):
        ps = [p for p in plan.pieces if p.item == i]
        if not ps:
            continue
        fps = fps_of(ps[0].clip)
        dur = sum(p.frames for p in ps) / fps
        zooms = "" if all(p.zoom == 1.0 for p in plan.pieces) else " Zoom " + "/".join(f"{p.zoom:g}" for p in ps)
        out.append(f"#{i:02d} {it.clip} {it.from_word}–{it.to_word} {ts(ps[0].start_s)}–{ts(ps[-1].end_s)} → {dur:.2f}s, "
                   f"{len(ps)} St. [{', '.join(f'{p.start_frame}–{p.end_frame}' for p in ps)}]{zooms} {it.note}")
        out.append("    " + " | ".join(_mark_text(p, {}, it, plan.corrections) for p in ps))
    cuts = cut_list(plan)
    if any(p.start_motion is not None for p in plan.pieces):
        flag = cl.options.motion_flag_factor
        moved = [c for c in cuts if c["shift"]]
        out.append(f"Schnitte (Bewegung = x Clip-Median an den angrenzenden Frames; ⚠ > {flag:g}; "
                   f"{len(moved)} von {len(cuts)} bewegungsbedingt verschoben):")
        for c in cuts:
            mark = " ⚠" if max(c["m_out"] or 0, c["m_in"] or 0) > flag else ""
            sh = f" verschoben {c['shift']}" if c["shift"] else ""
            out.append(f"  {c['id']} {c['label']} {c['f_out'] or '–'}|{c['f_in'] or '–'} "
                       f"Bew. {c['m_out'] if c['m_out'] is not None else '–'}|{c['m_in'] if c['m_in'] is not None else '–'}{sh}{mark}")
    if any(p.zoom != 1.0 for p in plan.pieces):
        n_zoom = sum(1 for a, b in zip(plan.pieces, plan.pieces[1:]) if a.zoom != b.zoom)
        n_dec = sum(1 for p in plan.pieces if p.decay_ms > 0)
        n_on = sum(1 for p in plan.pieces if p.onset_ms > 0)
        n_ex = sum(p.expressive for p in plan.pieces)
        if n_dec or n_on or n_ex or plan.hard_edges:
            out.append(f"Wortenden: {n_dec} Ausklänge verlängert (Ø {sum(p.decay_ms for p in plan.pieces) / max(n_dec, 1):.0f} ms), "
                       f"{n_on} Wortanfänge vorgezogen, {n_ex} Laute am Satzende behalten, {len(plan.hard_edges)} harte Kanten")
            for h in plan.hard_edges[:12]:
                out.append(f"  ⚠ harte Kante {ts(h['t'])} ({'Anfang' if h['side'] == 'start' else 'Ende'} von #{h['item']:02d}, "
                           f"{h['clip']}:f{h['frame']:04d}): {h['over_db']:+.0f} dB über dem Rauschboden")
        for b in plan.beats:
            orig = "Ende des Videos" if b["orig_s"] is None else f"Original {b['orig_s']:.2f} s"
            out.append(f"Beat {b['kind']} @{ts(b['t'])} nach {b['word']} „{b['text']}“: Pause {b['actual_s']:.2f} s (Ziel {b['target_s']:.2f} s, {orig})")
        lv = {}
        for p in plan.pieces:
            lv[p.zoom] = lv.get(p.zoom, 0) + 1
        out.append("Zoomstufen: " + ", ".join(f"{z * 100:.0f} % × {n}" for z, n in sorted(lv.items())))
        out.append(f"Punch-ins: {sum(1 for p in plan.pieces if p.zoom > 1)} von {len(plan.pieces)} Teilstücken gezoomt, "
                   f"{n_zoom} Zoomwechsel an Schnitten (Ausschnitt am Gesicht ausgerichtet)")
    if plan.overlays:
        fps0 = fps_of(first_piece(plan).clip) if plan.pieces else 30.0
        out.append("Overlays (B-Roll, Positionen im fertigen Schnitt):")
        for o in plan.overlays:
            what = (f"Video ab {o.media}:f{o.src_start:04d} ({o.src_frames} Quell-Frames{', Zeitlupe 50 %' if o.speed < 1 else ''}, "
                    f"Ton {'stumm' if o.audio == 'mute' else 'Atmo −20 dB'})" if o.kind == "video" else f"{o.fit}/{o.focus}/{o.motion}")
            out.append(f"  O{o.index} {o.media} V{o.track} {ts(o.tl_start / fps0)}–{ts(o.tl_end / fps0)} ({o.frames / fps0:.2f}s) "
                       f"über {o.words[0]}–{o.words[1]} · {what} {o.note}")
            if o.snap:
                from .snap import Snap, describe
                out.append("     Schnittkanten: " + describe(Snap(o.tl_start, o.tl_end, tuple(o.snap["moved"]), tuple(o.snap["on_cut"]),
                                                               o.snap["gaps"]), fps0))
    if plan.graphics:
        fps0 = fps_of(first_piece(plan).clip) if plan.pieces else 30.0
        out.append("Grafiken (Motion Graphics, Positionen im fertigen Schnitt):")
        for g in plan.graphics:
            out.append(f"  G{g.index} {g.template} V{g.track} {ts(g.tl_start / fps0)}–{ts(g.tl_end / fps0)} ({g.frames / fps0:.2f}s) "
                       f"über {g.words[0]}–{g.words[1]} · {g.params}{' · expressiv' if g.expressive else ''} {g.note}")
            if g.snap:
                from .snap import Snap, describe
                out.append("     Schnittkanten: " + describe(Snap(g.tl_start, g.tl_end, tuple(g.snap["moved"]), tuple(g.snap["on_cut"]),
                                                               g.snap["gaps"]), fps0))
    if plan.sfx:
        fps0 = fps_of(first_piece(plan).clip)
        i = plan.sfx_info
        out.append(f"Sound-Effekte (Modus {i.get('mode')}, Designsprache {i.get('style')}, höchstens {i.get('limit')}; Stimme "
                   f"{i.get('voice_lufs')} LUFS, {i.get('voice_source')}):")
        for s in plan.sfx:
            out.append(f"  S{s.index} {s.id} auf {s.at} ({s.what}): Transient {ts(s.event_frame / fps0)}, Clip ab {ts(s.tl_start / fps0)}, "
                       f"{s.gain_db:+g} dB zur Stimme (Clip-Lautstärke {s.volume_db:+.1f} dB){' · bewusst' if s.deliberate else ''} {s.note}")
    if plan.corrections:
        out.append("Korrekturen (nur Text, IDs unverändert): " + ", ".join(f"{k} → „{v}“" for k, v in plan.corrections.items()))
    out.append("Gesprochener Endtext (| = Schnitt im Item, ‖ = Item-Grenze, [i03 ▶ … ◀] = Overlay):")
    texts = []
    marks: dict[tuple[str, int], list[str]] = {}
    for o in plan.overlays:
        (ca, na), (cb, nb) = _word_ref(o.words[0]), _word_ref(o.words[1])
        marks.setdefault((ca, na), []).append(f"[{o.media} ▶")
        marks.setdefault((cb, nb), []).append("◀]")
    for i in range(1, len(cl.items) + 1):
        ps = [p for p in plan.pieces if p.item == i]
        if ps:
            texts.append(" | ".join(_mark_text(p, marks, cl.items[i - 1], plan.corrections) for p in ps))
    out.append(" ‖ ".join(texts))
    return "\n".join(out)


def cut_list(plan: Plan) -> list[dict]:
    """All cuts of the timeline incl. start and end: S00 = start of the first piece, Sk = between piece k and k+1."""
    ps, out = plan.pieces, []
    fid = lambda c, i: f"{c}:f{i:04d}"
    for k in range(len(ps) + 1):
        a = ps[k - 1] if k > 0 else None
        b = ps[k] if k < len(ps) else None
        label = ("Anfang" if a is None else "Ende" if b is None else
                 (f"#{a.item:02d}→#{b.item:02d}" if a.item != b.item else f"#{a.item:02d} intern"))
        sh = []
        if a is not None and a.end_shift:
            sh.append(f"Ende {a.end_shift:+d} F")
        if b is not None and b.start_shift:
            sh.append(f"Start {b.start_shift:+d} F")
        out.append({"id": f"S{k:02d}", "label": label, "a": a, "b": b,
                    "f_out": fid(a.clip, a.end_frame - 1) if a else None, "f_in": fid(b.clip, b.start_frame) if b else None,
                    "m_out": a.end_motion if a else None, "m_in": b.start_motion if b else None, "shift": ", ".join(sh)})
    return out


def _word_ref(ref: str) -> tuple[str, int]:
    m = re.fullmatch(r"(c\d+):w0*(\d+)", ref.strip(), re.I)
    if not m:
        raise ValueError(f"Wort-Referenz {ref!r} braucht den Clip, z. B. c01:w0082")
    return m.group(1).lower(), int(m.group(2))


def word_span(plan: Plan, clips: dict, analyzed: dict, from_word: str, to_word: str | None) -> tuple[int, int | None]:
    """Timeline frames (start, exclusive end) of a word range of the cut; end None if to_word is None."""
    recs, rec = [], 0
    for pc in plan.pieces:
        recs.append(rec)
        rec += pc.frames
    refs = [(from_word, False)] + ([(to_word, True)] if to_word else [])
    out = []
    for ref, is_end in refs:
        cid, n = _word_ref(ref)
        at = analyzed.get(cid)
        w = next((e for e in at.entries if e.id == f"w{n:04d}"), None) if at else None
        if w is None:
            raise ValueError(f"Wort {cid}:w{n:04d} unbekannt")
        fps = clips[cid].resolve_fps or clips[cid].fps
        lo, hi = math.floor(w.start_s * fps), math.ceil(w.end_s * fps)
        hit = next(((pc, r0) for pc, r0 in zip(plan.pieces, recs) if pc.clip == cid and pc.start_frame <= (hi if is_end else lo)
                    < pc.end_frame + (1 if is_end else 0)), None)
        if hit is None:
            hit = next(((pc, r0) for pc, r0 in zip(plan.pieces, recs) if pc.clip == cid and pc.start_frame <= hi and pc.end_frame > lo), None)
            if hit is None:
                raise ValueError(f"{ref} liegt nicht im Schnitt")
            pc, r0 = hit
            out.append(r0 + (pc.frames if is_end else 0))
        else:
            pc, r0 = hit
            out.append(r0 + (min(hi, pc.end_frame) if is_end else max(lo, pc.start_frame)) - pc.start_frame)
    return out[0], (out[1] if to_word else None)


def place_graphics(cl: Cutlist, plan: Plan, clips: dict, analyzed: dict, faces: dict | None = None,
                   prof=None, tok: dict | None = None, sandbox: bool = False) -> None:
    """Map graphics to timeline frames, enforce the minimum hold (extend), and check 05_motion_graphics limits."""
    if not cl.graphics or not plan.pieces:
        return
    from .mg.templates import TEMPLATES, min_duration
    fps = clips[first_piece(plan).clip].resolve_fps or clips[first_piece(plan).clip].fps
    total = sum(p.frames for p in plan.pieces)
    recs, rec = [], 0
    for pc in plan.pieces:
        recs.append(rec)
        rec += pc.frames
    last_item = max(p.item for p in plan.pieces)
    cta = cta_start(plan.pieces, recs, last_item)
    hook_f = round((prof.hook_s if prof else 3.0) * fps)
    for k, g in enumerate(cl.graphics, 1):
        tag = f"Grafik {k} ({g.template or 'frei'})"
        if g.html and not sandbox:
            plan.errors.append(f"{tag}: freies HTML nur im Sandbox-Modus (Konfiguration motion.sandbox = true)")
            continue
        if not g.html and g.template not in TEMPLATES:
            plan.errors.append(f"{tag}: unbekanntes Template – verfügbar: {', '.join(TEMPLATES)}")
            continue
        if g.template == "lower_third" and prof is not None and prof.layout == "reel":
            plan.errors.append(f"{tag}: Bauchbinden gibt es nur im Querformat, im Reel ein kurzer Namens-Callout (callout) oder keine")
            continue
        try:
            a, b = word_span(plan, clips, analyzed, g.from_word, g.to_word)
        except ValueError as e:
            plan.errors.append(f"{tag}: {e}")
            continue
        if b is None:
            b = a + round((g.duration_ms or 2500) / 1000 * fps)
        need = round(min_duration(g.template or "callout", tok, g.params) / 1000 * fps) if tok else round(2.15 * fps)
        if b - a < need:
            plan.warnings.append(f"{tag}: Wortbereich {(b - a) / fps:.2f} s < Mindestdauer {need / fps:.2f} s (Eingang + Haltezeit + "
                                 f"Ausgang) → verlängert")
            b = a + need
        if b > total:
            b = total
            if b - a < need:
                plan.warnings.append(f"{tag}: endet am Timeline-Ende, kürzer als die Mindestdauer")
        a, b, snapinfo = _snap(plan, a, b, fps, prof.graphic_snap_s if prof else 0.34, prof, need / fps, None, tag)
        if g.template != "hook_text" and a < hook_f:
            plan.warnings.append(f"{tag}: beginnt im Hook (erste {hook_f / fps:.0f} s) – dort nur hook_text")
        if g.template != "lower_third" and b > cta:
            plan.warnings.append(f"{tag}: läuft über den letzten Satz (CTA)")
        heads = head_track((faces or {}), plan, clips, a, b, tok, cl_reframe=cl.reframe)
        face = _union(heads) if heads else None
        plan.graphics.append(PlacedGraphic(index=k, template=g.template or "frei", params=g.params, track=g.track, tl_start=a,
                                           tl_end=b, words=(g.from_word, g.to_word or g.from_word), expressive=g.expressive,
                                           face=face, heads=heads, html=g.html, note=g.note, snap=snapinfo))
    gs = plan.graphics
    if prof is not None and prof.format in ("reel", "commercial") and len(gs) > (tok or {}).get("limits", {}).get("reel_max_graphics", 3):
        plan.warnings.append(f"{len(gs)} Grafiken – Reel: höchstens {(tok or {}).get('limits', {}).get('reel_max_graphics', 3)}")
    if sum(1 for g in gs if g.expressive) > (tok or {}).get("motion", {}).get("expressive_max_per_video", 2):
        plan.warnings.append("mehr als 2 expressive Grafiken – nur für 1–2 Schlüsselmomente")
    for g in gs:
        same = [o for o in gs if o is not g and o.tl_start < g.tl_end and g.tl_start < o.tl_end]
        ovs = [o for o in plan.overlays if o.tl_start < g.tl_end and g.tl_start < o.tl_end]
        if len(same) + 1 > (tok or {}).get("limits", {}).get("max_simultaneous_elements", 2):
            plan.warnings.append(f"Grafik {g.index}: mehr als 2 Elemente gleichzeitig")
        if ovs:
            plan.warnings.append(f"Grafik {g.index}: liegt über B-Roll {', '.join(o.media for o in ovs)} (Gesichtsbezug fehlt)")
        if any(o.track == g.track for o in same):
            plan.errors.append(f"Grafik {g.index}: überlappt eine andere Grafik auf Spur V{g.track}")


def head_track(faces: dict, plan: Plan, clips: dict, a: int, b: int, tok: dict | None, step: int = 3, cl_reframe=None) -> list:
    """Head box (timeline px, x y w h) every `step` frames of [a, b): face box of the source frame, transformed like the V1
    item (punch-in zoom around the centre, Pan +x, Tilt +up), widened to the head (up 0.6×h, sides 0.25×w)."""
    hf = (tok or {}).get("layout", {}).get("head_from_face", {"up": 0.6, "side": 0.25, "down": 0.05})
    out, rec = [], 0
    spans = []
    for pc in plan.pieces:
        spans.append((rec, pc))
        rec += pc.frames
    for t in range(a, b, step):
        pc, r0 = next(((pc, r0) for r0, pc in spans if r0 <= t < r0 + pc.frames), (None, None))
        if pc is None or pc.clip not in faces:
            continue
        boxes, (AW, AH) = faces[pc.clip]
        src = pc.start_frame + (t - r0)
        if src >= len(boxes) or boxes[src][0] < 0:
            continue
        clip = clips[pc.clip]
        if pc.fill:  # reel: the crop of the item, not the frame of the clip
            from . import reframe as rfm
            rf = cl_reframe
            hx, hy, hw, hh = rfm.head_box(boxes[src], (AW, AH), clip, hf)
            ax, ay = rfm.to_out(hx, hy, clip, pc, rf.width, rf.height)
            bx2, by2 = rfm.to_out(hx + hw, hy + hh, clip, pc, rf.width, rf.height)
            out.append([round(ax, 1), round(ay, 1), round(bx2 - ax, 1), round(by2 - ay, 1), t])
            continue
        w, h = (clip.height, clip.width) if abs(clip.rotation) % 180 == 90 else (clip.width, clip.height)
        bx = boxes[src]
        x, y, bw, bh = bx[0] / AW * w, bx[1] / AH * h, bx[2] / AW * w, bx[3] / AH * h
        x, y, bw, bh = x - hf["side"] * bw, y - hf["up"] * bh, bw * (1 + 2 * hf["side"]), bh * (1 + hf["up"] + hf.get("down", 0))
        z = pc.zoom or 1.0
        cx, cy = w / 2 + (x + bw / 2 - w / 2) * z + pc.pan, h / 2 + (y + bh / 2 - h / 2) * z - pc.tilt
        out.append([round(cx - bw * z / 2, 1), round(cy - bh * z / 2, 1), round(bw * z, 1), round(bh * z, 1), t])
    return out


def _union(boxes: list) -> tuple[float, float, float, float]:
    x0 = min(bx[0] for bx in boxes)
    y0 = min(bx[1] for bx in boxes)
    x1 = max(bx[0] + bx[2] for bx in boxes)
    y1 = max(bx[1] + bx[3] for bx in boxes)
    return (round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1))


def cut_frames(plan: Plan) -> list[int]:
    """Timeline frames of all cuts in V1 incl. start and end."""
    out, rec = [0], 0
    for pc in plan.pieces:
        rec += pc.frames
        out.append(rec)
    return out


def _snap(plan: Plan, a: int, b: int, fps: float, thr_s: float, prof, dmin_s: float, dmax_s: float | None, tag: str):
    from .snap import snap_span
    sliver = round((prof.sliver_s if prof else 0.5) * fps)
    margin = prof.cover_margin_frames if prof else 4
    sn = snap_span(a, b, cut_frames(plan), round(thr_s * fps), sliver, margin, round(dmin_s * fps),
                   round(dmax_s * fps) if dmax_s else 10**9, total=sum(p.frames for p in plan.pieces))
    info = {"orig": (a, b), "moved": sn.moved, "on_cut": sn.on_cut, "gaps": sn.gaps, "warnings": sn.warnings}
    for w in sn.warnings:
        plan.warnings.append(f"{tag}: {w}")
    return sn.start, sn.end, info


def place_overlays(cl: Cutlist, plan: Plan, clips: dict, analyzed: dict, stills: set[str] | None = None, prof=None) -> None:
    """Map overlay word ranges of the source to timeline frames of the cut (via the pieces)."""
    recs, rec = [], 0
    for pc in plan.pieces:
        recs.append(rec)
        rec += pc.frames
    total = rec
    for k, ov in enumerate(cl.overlays, 1):
        tag = f"Overlay {k} ({ov.media})"
        video = re.fullmatch(r"c\d+", ov.media.strip().lower()) is not None
        if video:
            vid = ov.media.strip().lower()
            if vid not in clips:
                plan.errors.append(f"{tag}: unbekannter Clip {ov.media}")
                continue
            if not ov.from_frame:
                plan.errors.append(f"{tag}: Video-B-Roll braucht from_frame (z. B. {vid}:f0120 aus get_frames(\"{vid}\", \"scenes\"))")
                continue
        elif not re.fullmatch(r"i\d+", ov.media) or ov.from_frame or ov.to_frame:
            plan.errors.append(f"{tag}: Medium muss ein Standbild (i03) oder ein Clip (c05 + from_frame) sein")
            continue
        elif stills is not None and ov.media not in stills:
            plan.errors.append(f"{tag}: unbekanntes Standbild")
            continue
        try:
            (c0, n0), (c1, n1) = _word_ref(ov.from_word), _word_ref(ov.to_word)
        except ValueError as e:
            plan.errors.append(f"{tag}: {e}")
            continue
        words = {}
        for cid, n in ((c0, n0), (c1, n1)):
            at = analyzed.get(cid)
            w = next((e for e in at.entries if e.id == f"w{n:04d}"), None) if at else None
            if w is None:
                plan.errors.append(f"{tag}: Wort {cid}:w{n:04d} unbekannt")
                break
            words[(cid, n)] = w
        else:
            fps0 = clips[c0].resolve_fps or clips[c0].fps
            fps1 = clips[c1].resolve_fps or clips[c1].fps

            def tl_of(cid: str, src_frame: int, end: bool) -> int | None:
                for pc, r0 in zip(plan.pieces, recs):
                    if pc.clip == cid and pc.start_frame <= src_frame < pc.end_frame + (1 if end else 0):
                        return r0 + (src_frame - pc.start_frame)
                return None

            w0, w1 = words[(c0, n0)], words[(c1, n1)]
            a = tl_of(c0, max(math.floor(w0.start_s * fps0), 0), False)
            if a is None:  # word start in removed padding → first piece that contains the word
                a = next((r0 for pc, r0 in zip(plan.pieces, recs) if pc.clip == c0
                          and pc.start_frame <= math.ceil(w0.end_s * fps0) and pc.end_frame > math.floor(w0.start_s * fps0)), None)
            b = tl_of(c1, math.ceil(w1.end_s * fps1), True)
            if b is None:
                b = next((r0 + pc.frames for pc, r0 in zip(plan.pieces, recs) if pc.clip == c1
                          and pc.start_frame <= math.ceil(w1.end_s * fps1) and pc.end_frame > math.floor(w1.start_s * fps1)), None)
            if a is None or b is None:
                plan.errors.append(f"{tag}: {ov.from_word}–{ov.to_word} liegt nicht (vollständig) im Schnitt")
                continue
            if b <= a:
                plan.errors.append(f"{tag}: Ende liegt vor dem Anfang")
                continue
            if b > total:
                plan.errors.append(f"{tag}: endet nach dem Timeline-Ende")
                continue
            if ov.tail:  # from the end of to_word to the end of its piece (the run-out the item keeps via end_frame)
                a = b
                b = next((r0 + pc.frames for pc, r0 in zip(plan.pieces, recs) if r0 <= a <= r0 + pc.frames
                          and pc.clip == c1), a)
                if b - a < round(0.5 * fps0):
                    plan.errors.append(f"{tag}: tail – nach {ov.to_word} bleiben nur {(b - a) / fps0:.2f} s; im Item "
                                       f"end_frame später setzen")
                    continue
            dmax = prof.broll_max_s if prof else 3.0
            if video:  # the material limits the length: snap only to cuts the clip can still reach
                try:
                    avail = _video_avail(ov, clips[vid], fps0, cl.options.broll_slowmo == "auto")
                    dmax = min(dmax, avail / fps0)
                except ValueError:
                    pass
            if ov.tail:
                from .snap import edge_gaps
                if video:
                    b = min(b, a + _video_avail(ov, clips[vid], fps0, cl.options.broll_slowmo == "auto"))
                cuts = cut_frames(plan)
                snapinfo = {"orig": (a, b), "moved": (0, 0), "on_cut": (a in cuts, b in cuts), "gaps": edge_gaps(a, b, cuts),
                            "warnings": []}
            else:
                a0, b0 = a, b
                a, b, snapinfo = _snap(plan, a, b, fps0, prof.overlay_snap_s if prof else 0.6, prof,
                                       prof.broll_min_s if prof else 1.5, dmax, tag)
                prev_end = max((o.tl_end for o in plan.overlays if o.track == ov.track and o.tl_end <= b0
                                and o.tl_end > a), default=None)
                if prev_end is not None and a < prev_end <= a0 + round(0.6 * fps0):
                    # snapping pulled the start back into the previous overlay → start where it ends (that is a cut)
                    snapinfo["warnings"].append(f"Anfang an das Ende von Overlay davor gelegt ({(prev_end - a) / fps0:+.2f} s)")
                    a = prev_end
            vinfo = {}
            if video:
                try:
                    vinfo = _video_span(ov, clips[vid], a, b, fps0, plan, tag, prof, cl.options.broll_slowmo == "auto")
                except ValueError as e:
                    plan.errors.append(f"{tag}: {e}")
                    continue
                b = a + vinfo.pop("tl_frames")
            for o in plan.overlays:
                if o.track == ov.track and a < o.tl_end and o.tl_start < b:
                    plan.errors.append(f"{tag}: überlappt Overlay {o.index} auf Spur V{ov.track}")
            if ov.track < 2:
                plan.errors.append(f"{tag}: Spur muss ≥ 2 sein (V1 ist der Schnitt)")
            plan.overlays.append(PlacedOverlay(index=k, media=ov.media, track=ov.track, tl_start=a, tl_end=b,
                                               words=(ov.from_word, ov.to_word), fit=ov.fit, focus=ov.focus,
                                               motion=ov.motion, note=ov.note, snap=snapinfo, kind="video" if video else "still",
                                               audio=ov.audio if video else "mute", tail=ov.tail, **vinfo))


def _video_avail(ov: Overlay, clip: Clip, tl_fps: float, auto_slow: bool = False) -> int:
    """Timeline frames the clip can fill from from_frame (to to_frame / clip end), at the speed the overlay will get."""
    src_fps = clip.resolve_fps or clip.fps
    ratio = src_fps / tl_fps
    slow = (ov.slowmo if ov.slowmo is not None else auto_slow) and ratio >= 2 - 1e-3
    speed = 0.5 if slow else 1.0
    start = _frame_of(ov.from_frame, clip.id)
    total = clip.resolve_frames or clip.nb_frames or round(clip.duration_s * src_fps)
    limit = (_frame_of(ov.to_frame, clip.id) + 1) if ov.to_frame else total
    return max(0, min(int((limit - start) / (ratio * speed)), int((total - start) / ratio)))


def _video_span(ov: Overlay, clip: Clip, a: int, b: int, tl_fps: float, plan: Plan, tag: str, prof,
                auto_slow: bool = False) -> dict:
    """Source frames for a video B-roll over timeline frames [a, b). Integer multiples (50 → 25) map frame-exactly;
    other rates only for B-roll without sound (±1 frame, warning). Slow motion (50 %) only for ≥ 2× the timeline rate."""
    src_fps = clip.resolve_fps or clip.fps
    ratio = src_fps / tl_fps
    whole = abs(ratio - round(ratio)) < 1e-3 and round(ratio) >= 1
    if not whole:
        plan.warnings.append(f"{tag}: B-Roll {src_fps:g} fps in {tl_fps:g}-fps-Timeline – nicht ganzzahlig, ±1 Frame (ohne Ton unkritisch)")
    want_slow = ov.slowmo if ov.slowmo is not None else (auto_slow and ratio >= 2 - 1e-3)
    speed = 1.0
    if want_slow:
        if ratio >= 2 - 1e-3:
            speed = 0.5
        else:
            plan.warnings.append(f"{tag}: Zeitlupe nur mit ≥ {2 * tl_fps:g} fps möglich (Clip hat {src_fps:g}) – normale Geschwindigkeit")
    start = _frame_of(ov.from_frame, clip.id)
    total = clip.resolve_frames or clip.nb_frames or round(clip.duration_s * src_fps)
    limit = (_frame_of(ov.to_frame, clip.id) + 1) if ov.to_frame else total
    if start >= limit:
        raise ValueError(f"from_frame {ov.from_frame} liegt hinter dem Clip-Ende/to_frame")
    n = b - a
    shown_src = round(n * ratio * speed)  # source frames actually visible
    avail = limit - start
    if shown_src > avail:
        n = max(1, int(avail / (ratio * speed)))
        plan.warnings.append(f"{tag}: B-Roll-Material reicht nur für {n / tl_fps:.2f} s (Bereich {(b - a) / tl_fps:.2f} s) → gekürzt")
    append_src = round(n * ratio)  # appended at normal speed (duration n); SetSpeed 50 % then shows half of it
    if start + append_src > total:  # slow motion: the appended range must exist in the clip even if only half is shown
        append_src = total - start
        n = int(append_src / ratio)
    return {"tl_frames": n, "src_start": start, "src_frames": append_src, "speed": speed}


def _mark_text(p: Piece, marks: dict, item: CutItem, corr: dict[str, str] | None = None) -> str:
    """Piece text with overlay markers inserted at the overlay's first/last word."""
    corr = corr or {}
    words = p.text.split(" ")
    if (not marks and not corr) or len(words) != len(p.word_ids):
        return p.text
    out = []
    for wid, txt in zip(p.word_ids, words):
        txt = corr.get(f"{p.clip}:{wid}", txt)
        key = (p.clip, int(wid[1:]))
        m = marks.get(key, [])
        out += [x for x in m if x.endswith("▶")] + [txt] + [x for x in m if x == "◀]"]
    return " ".join(out)


def merge_cutlists(parts: list[Cutlist], timeline_name: str | None = None) -> Cutlist:
    """Concatenate per-page decisions; options/flags from the first part."""
    if not parts:
        raise ValueError("keine Cutlists übergeben")
    merged = parts[0].model_copy(deep=True)
    merged.timeline_name = timeline_name or merged.timeline_name
    for c in parts[1:]:
        merged.items += [i.model_copy() for i in c.items]
        merged.rejected += [r.model_copy() for r in c.rejected]
        merged.overlays += [o.model_copy() for o in c.overlays]
    return merged


def _frame_of(ref: str, clip_id: str) -> int:
    m = re.fullmatch(r"(c\d+):f0*(\d+)", ref.strip(), re.I)
    if not m:
        raise ValueError(f"Frame-ID {ref!r} ungültig (z. B. {clip_id}:f0114)")
    if m.group(1).lower() != clip_id:
        raise ValueError(f"Frame-ID {ref} gehört nicht zu {clip_id}")
    return int(m.group(2))


def check_edges(cl: Cutlist, plan: Plan, clips: dict, acoustics: dict) -> None:
    """Every edge of every piece against the noise floor; what is left above the threshold is a "hard edge"."""
    from . import edges as ed
    rec = 0
    for pc in plan.pieces:
        ac = acoustics.get(pc.clip)
        fps = clips[pc.clip].resolve_fps or clips[pc.clip].fps
        if ac is not None:
            for side, frame, at_tl in (("start", pc.start_frame, rec), ("end", pc.end_frame, rec + pc.frames)):
                if not ed.is_quiet(ac, frame, fps, side, cl.options.edge_db):
                    plan.hard_edges.append({"tl": at_tl, "t": round(at_tl / fps, 2), "side": side, "item": pc.item, "clip": pc.clip,
                                            "frame": frame, "over_db": round(ed.edge_level(ac, frame, fps, side) - ac.floor_db, 1)})
        rec += pc.frames


def measure_beats(cl: Cutlist, plan: Plan, clips: dict, analyzed: dict, beat_map: dict) -> None:
    """Actual pause behind every beat in the finished cut (end of the word → start of the next word on the timeline)."""
    seq, r0 = [], 0  # (clip, word number, word, timeline start, timeline end)
    for pc in plan.pieces:
        fps = clips[pc.clip].resolve_fps or clips[pc.clip].fps
        by_id = {e.id: e for e in analyzed[pc.clip].entries}
        for wid in pc.word_ids:
            w = by_id.get(wid)
            if w is not None and w.kind == "word":
                seq.append((pc.clip, int(wid[1:]), w, (r0 + (w.start_s * fps - pc.start_frame)) / fps,
                            (r0 + min(pc.frames, w.end_s * fps - pc.start_frame)) / fps))
        r0 += pc.frames
    total = r0 / (clips[first_piece(plan).clip].resolve_fps or clips[first_piece(plan).clip].fps) if plan.pieces else 0.0
    pos = {(c, n): k for k, (c, n, *_ ) in enumerate(seq)}
    for cid, words in beat_map.items():
        for n, kind in sorted(words.items()):
            k = pos.get((cid, n))
            if k is None:
                plan.warnings.append(f"Beat nach {cid}:w{n:04d}: das Wort ist nicht im Schnitt")
                continue
            c, _, w, _, t_end = seq[k]
            t_next = seq[k + 1][3] if k + 1 < len(seq) else total
            sounds = [e for e in analyzed[c].entries if e.start_s >= w.end_s - 1e-6 and e.id != w.id
                      and (e.id[0] == "w" or e.kind == "filler")]
            orig = (sounds[0].start_s - w.end_s) if sounds else None
            target = (cl.options.beat_section_ms if kind == "section" else cl.options.beat_key_ms) / 1000
            plan.beats.append({"word": f"{c}:w{n:04d}", "kind": kind, "text": w.text, "t": round(t_end, 2), "target_s": target,
                               "actual_s": round(t_next - t_end, 2), "orig_s": None if orig is None else round(orig, 2)})
    plan.beats.sort(key=lambda b: b["t"])


def cta_start(pieces: list, recs: list[int], last_item: int) -> int:
    """Timeline frame where the last sentence (CTA) begins: after the last sentence end before the final piece's end,
    inside the last item. A one-take item (commercial) is not entirely the CTA (Phase 8: every overlay was flagged)."""
    first = next(k for k, p in enumerate(pieces) if p.item == last_item)
    start = first
    for k in range(len(pieces) - 1, first, -1):
        prev = pieces[k - 1].text.split()
        if prev and SENTENCE_END.search(prev[-1]):
            start = k
            break
    return recs[start]


def assign_zooms(cl: Cutlist, plan: Plan, clips: dict, faces: dict, prof=None) -> None:
    """Alternate 1.0 / punched in at jump cuts (same clip on both sides); every n-th punch-in uses a variation level
    (112 %, 125 %, alternating), so the sequence is e.g. 100-120-100-120-100-112-100-120-100-120-100-125. Two equal levels
    never follow each other because every second level is 100 %. Cuts hidden under an overlay keep the level; automatic
    levels stay below the limit of the source resolution, item.zoom overrides (accent; a warning if it is above the
    limit). Pan/Tilt keep the face position (framing.punch_in)."""
    from .framing import punch_in
    from .profiles import max_zoom_for

    pi = cl.punch_in
    if not plan.pieces or (pi is None and not any(it.zoom for it in cl.items)):
        return
    recs, rec = [], 0
    for pc in plan.pieces:
        recs.append(rec)
        rec += pc.frames
    hidden = {r for r in recs[1:] if any(o.tl_start < r < o.tl_end for o in plan.overlays)}
    rule = (pi.rule if pi and pi.rule else "every")
    scale = (pi.scale if pi and pi.scale else 1.12)
    variation = list(pi.variation or []) if pi else []
    every = (pi.variation_every or 0) if pi else 0
    level = False  # False = 1.0, True = punched in
    current = scale  # the level of the running punch-in
    n_in = 0  # punch-ins so far
    uncovered = 0  # consecutive jump cuts without a level change
    fps = (clips[first_piece(plan).clip].resolve_fps or clips[first_piece(plan).clip].fps) if clips else 25.0
    hold = round((pi.min_hold_s if pi and pi.min_hold_s is not None else 0.0) * fps)
    since = 0  # timeline frames since the last level change
    for k, pc in enumerate(plan.pieces):
        if pc.manual:
            level, since, uncovered = False, 0, 0
            continue
        if k and pi and pi.mode == "alternate":
            prev = plan.pieces[k - 1]
            since += prev.frames
            if prev.clip == pc.clip and recs[k] not in hidden:
                starts_sentence = bool(prev.text) and bool(SENTENCE_END.search(prev.text.split()[-1]))
                toggle = (rule == "every" or starts_sentence or (rule == "sentence_no_repeat" and uncovered >= 1))
                if toggle and since < hold:  # never flash a level shorter than min_hold_s (Phase 8: 6-frame pieces)
                    toggle = False
                if toggle:
                    since = 0
                    level = not level
                    uncovered = 0
                    if level:
                        n_in += 1
                        current = scale
                        if variation and every and n_in % every == 0:
                            current = variation[(n_in // every - 1) % len(variation)]
                else:
                    uncovered += 1
            else:
                uncovered = 0
        override = cl.items[pc.item - 1].zoom if 0 < pc.item <= len(cl.items) else None
        z = override if override else (current if (pi and pi.mode == "alternate" and level) else 1.0)
        if not override and prof is not None and z > 1.0:
            c0 = clips[pc.clip]
            z = min(z, max_zoom_for(prof, c0.width, c0.height))
        pc.zoom = round(float(z), 3)
        item = cl.items[pc.item - 1] if override and 0 < pc.item <= len(cl.items) else None
        if item is not None and item.pan is not None:
            pc.pan, pc.tilt = item.pan, item.tilt or 0.0
        elif pc.zoom > 1.0:
            clip = clips[pc.clip]
            w, h = (clip.height, clip.width) if abs(clip.rotation) % 180 == 90 else (clip.width, clip.height)
            fx, fy = _face_center(faces.get(pc.clip), pc.start_frame, pc.end_frame)
            pc.pan, pc.tilt = punch_in(fx, fy, pc.zoom, w, h) if w and h else (0.0, 0.0)


def _face_center(fa, a: int, b: int) -> tuple[float, float]:
    if not fa:
        return 0.5, 0.5
    boxes, (W, H) = fa
    sel = [bx for bx in boxes[a:b] if bx[0] >= 0]
    if not sel:
        return 0.5, 0.5
    import numpy as np

    arr = np.array(sel, dtype=float)
    return float(np.median(arr[:, 0] + arr[:, 2] / 2) / W), float(np.median(arr[:, 1] + arr[:, 3] / 2) / H)
