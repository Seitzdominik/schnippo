"""Sound effects (Phase 9): the shipped library (sfx/library.json + wav files) and the user's own folder (config sfx_folder).
Every effect carries hit_offset_ms: where its transient lies. The transient is aligned, not the start of the file."""

from __future__ import annotations

from .cutlist import first_piece

from . import platforms
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .media import _bin

SR = 48000
CATEGORIES = ("whoosh", "swish", "pop", "tick", "click", "ding", "impact_soft", "impact", "riser", "downer", "typing", "clock", "alarm", "atmo", "applause")
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".mp3", ".flac", ".m4a", ".ogg"}
# order counts: "alarm-clock" is an alarm, "swoosh-riser" a riser, "clock-ticking" a clock
KEYWORDS = {"applause": ("applause", "aplause", "applaus", "clapping", "beifall"),
            "atmo": ("birds", "bird", "vogel", "vögel", "atmo", "ambience", "ambient", "forest", "wald", "rain", "regen", "nature"),
            "alarm": ("alarm", "wecker"), "clock": ("clock", "uhr", "ticking"), "typing": ("typing", "keyboard", "tastatur", "tippen", "keystroke"),
            "riser": ("riser", "rise", "build", "uplift", "sweep"), "downer": ("needle", "vinyl", "record", "scratch", "tape stop", "tapestop", "downer"),
            "impact": ("impact", "hit", "boom", "thud", "sub", "drop"), "whoosh": ("whoosh", "woosh", "swoosh", "transition", "pass", "fly"),
            "swish": ("swish", "swipe", "swoop", "air"), "ding": ("ding", "bell", "glocke", "chime", "notification", "reveal"),
            "click": ("click", "mouse", "maus", "klick"), "pop": ("pop", "bubble", "blip"), "tick": ("tick", "tap", "clack", "ui")}
# synthetic effects replaced by real recordings: older cutlists keep working
RENAMED = {"clock_wall": "clock_timer", "clock_mech": "clock_timer", "clock_tension": "clock_timer", "typing_soft": "typing_mech_b", "downer_needle": "downer_vinyl"}
TYPE_OF = {"atmo": "bed", "clock": "bed", "typing": "sequence"}
ALIGN_OF = {"atmo": "start", "clock": "start", "typing": "start", "alarm": "start", "riser": "end"}


def library_dir() -> Path:
    """Repo checkout and installed bundle have the same layout."""
    return Path(__file__).resolve().parent / "data" / "sfx"


def measure(x: np.ndarray, sr: int = SR) -> dict:
    """x: samples (n,) or (n, ch). hit_offset_ms = loudest 5-ms window, for a slow swell the point where the rise ends;
    peak_rms_db = loudest 100 ms: the level the effect is perceived at."""
    m = x if x.ndim == 1 else np.sqrt(np.mean(x ** 2, axis=1))
    hop = max(1, sr // 200)
    n = max(1, len(m) // hop)
    env = np.sqrt(np.mean(m[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-14)
    smooth = np.convolve(env, np.ones(3) / 3, mode="same")
    level = 20 * np.log10(np.concatenate([[1e-6, 1e-6], smooth]) + 1e-9)
    jump = np.nonzero((level[2:] - level[:-2] >= 9) & (level[2:] > level.max() - 20))[0]  # a strike counts from its onset, not from its loudest moment
    hit = (int(jump[0]) if len(jump) else int(np.argmax(smooth))) * hop + hop // 2
    w = max(1, sr // 10)
    c = np.cumsum(np.concatenate([[0.0], m ** 2]))
    rms = (c[w:] - c[:-w]) / w if len(m) > w else np.array([float(np.mean(m ** 2))])
    audible = np.nonzero(smooth > smooth.max() * 10 ** (-30 / 20))[0]  # the tail below −30 dB is gone under speech
    return {"hit_offset_ms": round(hit / sr * 1000), "duration_ms": round(len(m) / sr * 1000),
            "audible_ms": round((int(audible[-1]) + 1) * hop / sr * 1000),
            "peak_rms_db": round(float(10 * np.log10(rms.max() + 1e-14)), 1)}


def decode(path: Path) -> np.ndarray:
    raw = platforms.run([_bin("ffmpeg"), "-nostdin", "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)


def guess_category(path: Path) -> str | None:
    text = " ".join(p.lower() for p in path.parts[-3:])
    for cat, words in KEYWORDS.items():
        if any(re.search(rf"(^|[^a-z]){w}", text) for w in words):
            return cat
    return None


def scan_user_folder(folder: Path, cache_file: Path) -> list[dict]:
    """Own sounds: category from folder/file name, transient measured (cached by size + time). The licence is the user's."""
    from .guard import real
    folder = real(folder)
    known = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    out = []
    for p in sorted(folder.rglob("*")):
        if p.suffix.lower() not in AUDIO_EXTS or p.name.startswith(".") or not p.is_file() or folder not in real(p).parents:
            continue
        key = f"{p}|{p.stat().st_size}|{int(p.stat().st_mtime)}"
        if key not in known:
            known[key] = measure(decode(p))
        cat = guess_category(p.relative_to(folder))
        align = "transient" if cat == "riser" and "impact" in p.name.lower() else ALIGN_OF.get(cat or "", "transient")
        m = dict(known[key])
        m["hit_offset_ms"] = {"end": m["duration_ms"], "start": 0}.get(align, m["hit_offset_ms"])
        side = p.with_name(p.name + ".json")  # source, author and licence of downloaded sounds
        info = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {}
        out.append({"id": "user:" + p.stem, "file": str(p), "category": cat, "intensity": 2, "styles": [], "license": info.get("license", "Nutzer"), "credit": info.get("credit", ""),
                    "type": TYPE_OF.get(cat or "", "oneshot"), "event_align": align, **m})
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(known), encoding="utf-8")
    return out


def load(user_folder: Path | None = None, cache_dir: Path | None = None) -> list[dict]:
    lib = library_dir()
    data = json.loads((lib / "library.json").read_text(encoding="utf-8"))
    out = [{**e, "file": str(lib / e["file"])} for e in data["effects"]]
    if user_folder and Path(user_folder).is_dir():
        out = scan_user_folder(Path(user_folder), Path(cache_dir or lib) / "sfx_user.json") + out  # own sounds first, also for a sound named in cue.file
    return out


# ---------------------------------------------------------------- placement (guides/06_sound_design.md)
MODES = ("off", "subtil", "normal")
GAIN_RANGE = (-24.0, -18.0)  # below the voice
RANGES = {"atmo": (-32.0, -28.0), "clock": (-30.0, -20.0)}  # beds lie deeper
MIN_GAP_S = 3.0
AIRY = ("whoosh", "swish", "riser")
SENTENCE_END = re.compile(r"[.!?…]$")


def default_gain(category: str, mode: str, style: str | None) -> float:
    """dB below the voice: −20 by default, airy effects quieter than accents, clicks and typing very quiet, beds below everything;
    the design language shifts it."""
    base = {"atmo": -30.0, "clock": -26.0, "click": -24.0, "typing": -24.0, "applause": -24.0}.get(category, -20.0)
    g = base + (2 if mode == "normal" else 0) - (2 if category in AIRY else 0) + {"minimal": -2, "bold": 2}.get(style or "", 0)
    lo, hi = RANGES.get(category, GAIN_RANGE)
    return max(lo, min(hi, g))


def volume_for(voice_lufs: float, gain_db: float, peak_rms_db: float) -> float:
    """AudioVolume that puts the loudest 100 ms of the effect gain_db below the voice."""
    return round(max(-60.0, min(12.0, voice_lufs + gain_db - peak_rms_db)), 1)


def max_effects(fmt: str, total_s: float, style: str | None) -> int:
    if fmt in ("reel", "commercial"):
        return 3 if style == "minimal" else 5
    n = max(4, round(total_s / 60 * 1.5))
    return max(3, n // 2) if style == "minimal" else n


def context(plan, analyzed: dict, fps: float, prof) -> dict:
    """Where effects may not go: end of the hook sentence, start of the CTA, sentence starts and cuts (timeline frames)."""
    from .cutlist import cta_start
    words, rec, recs = [], 0, []
    maps: dict[str, dict] = {}
    for pc in plan.pieces:
        recs.append(rec)
        if pc.clip not in maps:
            at = analyzed.get(pc.clip)
            maps[pc.clip] = {e.id: e for e in at.entries} if at else {}
        for wid in pc.word_ids:
            w = maps[pc.clip].get(wid)
            if w is not None:
                words.append((rec + max(0, round(w.start_s * fps) - pc.start_frame),
                              rec + min(pc.frames, round(w.end_s * fps) - pc.start_frame), w.text))
        rec += pc.frames
    hook_s = getattr(prof, "hook_s", 3.0)
    ends = [b for _, b, t in words if SENTENCE_END.search(t)]
    hook = min(ends[0], round(2 * hook_s * fps)) if ends else round(hook_s * fps)
    starts = [words[k + 1][0] for k in range(len(words) - 1) if SENTENCE_END.search(words[k][2])]
    last = max((p.item for p in plan.pieces), default=0)  # words are finer than pieces: a long last piece is not all CTA
    cta = starts[-1] if starts else (cta_start(plan.pieces, recs, last) if plan.pieces else rec)
    return {"hook_end": hook, "cta": cta, "sentences": starts, "cuts": recs[1:], "total": rec}


def rules(cues: list[dict], ctx: dict, fps: float, limit: int, short_format: bool = True) -> list[tuple[bool, str]]:
    """cues: label, event, start, end (audible end), target_end, deliberate, category, kind; frames. Returns (hard rule?, text).
    Beds (atmo, ticking) lie under the picture: they do not count as effects and need no distance."""
    out: list[tuple[bool, str]] = []
    every = sorted(cues, key=lambda c: c["event"])
    beds = [c for c in every if c.get("kind") == "bed"]
    cues = [c for c in every if c.get("kind") != "bed"]
    if len(cues) > limit:
        out.append((True, f"{len(cues)} Effekte, höchstens {limit} für dieses Format und diese Designsprache"))
    order = cues
    for cat, text, cap in (("downer", "Downer", 1), ("impact", "Impact", 1), ("alarm", "Wecker", 1), ("applause", "Applaus", 1)):
        n = sum(1 for c in order if (c.get("category") or "").startswith(cat))
        if n > cap and short_format:
            out.append((True, f"{n}× {text}: höchstens {cap} in kurzen Formaten"))
    hits = [c for c in order if (c.get("category") or "").startswith("impact") or "impact" in c["label"]]
    if any(order.index(b) == order.index(a) + 1 for a, b in zip(hits, hits[1:])):
        out.append((True, "Impacts direkt hintereinander"))
    for c in every:
        if c.get("category") == "atmo" and not c.get("under_overlay"):
            out.append((True, f"{c['label']}: Atmo nur unter passender B-Roll (at = Overlay)"))
    for c in cues:
        if c.get("category") == "riser" and "impact" not in c["label"] and not 1000 <= c.get("span_ms", 2000) <= 3000:
            out.append((False, f"{c['label']}: Riser {c.get('span_ms', 0) / 1000:.1f} s, Richtwert 1–3 s"))
    for a, b in zip(order, order[1:]):
        gap = (b["event"] - a["event"]) / fps
        if gap < MIN_GAP_S - 1e-6:
            out.append((True, f"{a['label']} und {b['label']} nur {gap:.1f} s auseinander (mindestens {MIN_GAP_S:g} s)"))
    for c in every:
        if not c.get("deliberate"):
            if c["start"] < ctx["hook_end"]:
                out.append((True, f"{c['label']} liegt im Hook-Satz (deliberate=true, wenn bewusst)"))
            if c["end"] > ctx["cta"]:
                out.append((True, f"{c['label']} liegt im letzten Satz/CTA (deliberate=true, wenn bewusst)"))
        if c.get("target_end") is not None and c["end"] > c["target_end"]:
            out.append((False, f"{c['label']} klingt {(c['end'] - c['target_end']) / fps:.2f} s über das Ende des Elements hinaus"))
        if c.get("kind") == "oneshot" and any(c["event"] + 3 < s < c["end"] for s in ctx["sentences"]):
            out.append((False, f"{c['label']} klingt in den nächsten Satz aus"))
    if len(ctx["cuts"]) >= 4:
        hit = sum(any(abs(cut - c["event"]) <= 2 for c in cues) for cut in ctx["cuts"])
        if hit / len(ctx["cuts"]) > 0.5:
            out.append((True, f"Effekte auf {hit} von {len(ctx['cuts'])} Schnitten: nicht auf jeden Schnitt"))
    return out


def _pick(lib: list[dict], cue, category: str | None, want: int, explicit: bool, uses: dict, style: str | None = None) -> dict | None:
    if cue.file:
        name = RENAMED.get(cue.file.strip().lower(), cue.file.strip().lower())
        return next((e for e in lib if name in (e["id"].lower(), e["id"].split(":")[-1].lower(), Path(e["file"]).name.lower())), None)
    # auto_styles: placed by category only in these design languages, otherwise only when named (cue.file)
    cands = [e for e in lib if e["category"] == category and ("auto_styles" not in e or style in e["auto_styles"])]
    cands = [e for e in cands if e["id"].startswith("user:")] or cands  # the user's own sounds win their category, the library fills the rest
    if not explicit:  # vary, but never louder than one step above the wish
        cands = [e for e in cands if e["intensity"] <= want + 1] or cands
    return min(cands, key=lambda e: abs(e["intensity"] - want) + (0 if explicit else 1.5 * uses.get(e["id"], 0)), default=None)


def _graphic_event(g, tok: dict | None, fps: float, event: str) -> float:
    m = (tok or {}).get("motion") or {}
    dur, stag = m.get("dur", {}), m.get("stagger", {})
    t_in = dur.get("emph_ms", 500) if g.expressive else dur.get("in_ms", 300)
    delay = stag.get("text_after_box_frames", 2) * 1000 / fps
    if event == "end":
        ms = delay + (dur.get("emph_ms", 500) + (stag.get("line_ms", 0) if g.params.get("label") else 0) if g.template == "counter" else t_in)
    else:
        ms = t_in / 2  # the wipe decelerates: at half its time the box is mostly open
    return g.tl_start + ms / 1000 * fps


def place(cl, plan, clips: dict, analyzed: dict, prof, tok: dict | None, opts: dict) -> None:
    """cl.sfx → plan.sfx. opts: library, mode, style, voice_lufs, voice_source."""
    from .cutlist import PlacedSfx, word_span
    if not cl.sfx or not plan.pieces:
        return
    mode, style, lib = opts["mode"], opts.get("style"), opts["library"]
    if mode not in MODES:
        plan.errors.append(f"sfx: Modus {mode!r} unbekannt ({' | '.join(MODES)})")
        return
    if mode == "off":
        plan.warnings.append(f"sfx: Modus off – {len(cl.sfx)} Effekt(e) werden nicht gesetzt")
        return
    fps = clips[first_piece(plan).clip].resolve_fps or clips[first_piece(plan).clip].fps
    total = sum(p.frames for p in plan.pieces)
    uses: dict[str, int] = {}
    for k, cue in enumerate(cl.sfx, 1):
        tag = f"S{k}"
        category = cue.category
        if cue.file is None and category not in CATEGORIES:
            plan.errors.append(f"{tag}: category oder file angeben (Kategorien: {', '.join(CATEGORIES)})")
            continue
        if cue.file is None and style == "tech" and category in AIRY:
            plan.warnings.append(f"{tag}: Clean Tech nimmt Ticks statt {category}")
            category = "tick"
        if cue.file is None and style == "soft" and category == "impact_soft" and not cue.deliberate:
            plan.warnings.append(f"{tag}: Soft Premium: nur der weichste Impact")
        want = cue.intensity or (2 if mode == "normal" else 1) + (1 if style == "bold" else 0)
        if cue.file is None and style == "soft" and category == "impact":
            category = "impact_soft"
            plan.warnings.append(f"{tag}: Soft Premium nimmt den weichen Impact")
        cap = {"minimal": 1, "soft": 1 if category == "impact_soft" else 2}.get(style or "", 3)
        want = max(1, min(want, cap))
        e = _pick(lib, cue, category, want, cue.intensity is not None or style in ("minimal",), uses, style)
        if e is None:
            plan.errors.append(f"{tag}: kein Effekt für {cue.file or category} (list_sfx zeigt die Bibliothek)")
            continue
        uses[e["id"]] = uses.get(e["id"], 0) + 1
        ref = cue.at.strip()
        event = cue.event or ("end" if (e["category"] in ("tick", "ding") and ref[:1].upper() == "G") else "in")
        kind, align = e.get("type", "oneshot"), e.get("event_align", "transient")
        span_end = None
        target_end, what = None, None
        m = re.fullmatch(r"([GgOo])0*(\d+)", ref)
        if m:
            pool = plan.graphics if m.group(1).upper() == "G" else plan.overlays
            el = next((x for x in pool if x.index == int(m.group(2))), None)
            if el is None:
                plan.errors.append(f"{tag}: {ref.upper()} gibt es nicht in diesem Schnitt")
                continue
            target_end = span_end = el.tl_end
            if m.group(1).upper() == "G":
                is_counter = el.template == "counter"
                if event == "end" and not is_counter:
                    event = "in"
                at_frame = _graphic_event(el, tok, fps, event)
                what = "Endwert" if event == "end" else "Box öffnet"
            else:
                at_frame, what = float(el.tl_start), "Bildwechsel"
        else:
            try:
                at_frame, what = float(word_span(plan, clips, analyzed, ref, None)[0]), "Wort"
            except ValueError as err:
                plan.errors.append(f"{tag}: {err}")
                continue
        # beds and sequences run for as long as the element (or duration_ms): the file is cut or looped to that length when staged
        length_ms = None
        if kind in ("bed", "sequence"):
            length_ms = cue.duration_ms or (round((span_end - at_frame) / fps * 1000) if span_end else 2000)
            if kind == "sequence" and not cue.duration_ms:
                length_ms = min(length_ms, 2000)
        dur_ms = length_ms or e["duration_ms"]
        start = round(at_frame - e["hit_offset_ms"] / 1000 * fps)
        frames = math.ceil(dur_ms / 1000 * fps)
        if start < 0:
            plan.errors.append(f"{tag}: {e['id']} müsste {-start / fps:.2f} s vor dem Timeline-Anfang beginnen")
            continue
        if start + frames > total:
            plan.errors.append(f"{tag}: {e['id']} läuft über das Timeline-Ende hinaus")
            continue
        gain = cue.gain_db if cue.gain_db is not None else default_gain(e["category"] or "", mode, style)
        lo, hi = RANGES.get(e["category"] or "", GAIN_RANGE)
        if cue.gain_db is not None and not lo <= cue.gain_db <= hi:
            plan.warnings.append(f"{tag}: gain_db {cue.gain_db:g} außerhalb des Leitfadens ({lo:g} bis {hi:g} dB unter der Stimme)")
        plan.sfx.append(PlacedSfx(index=k, id=e["id"], category=e["category"] or "", file=e["file"], at=ref.upper() if m else ref, event=event,
                                  what=what, event_frame=round(at_frame), tl_start=start, frames=frames, hit_ms=e["hit_offset_ms"],
                                  audible_ms=length_ms or e.get("audible_ms", e["duration_ms"]), gain_db=gain, kind=kind, align=align, length_ms=length_ms,
                                  under_overlay=bool(m and m.group(1).upper() == "O"),
                                  volume_db=volume_for(opts["voice_lufs"], gain, e["peak_rms_db"]), note=cue.note, deliberate=cue.deliberate,
                                  target_end=target_end, license=e.get("license", ""), credit=e.get("credit", "")))
    ctx = context(plan, analyzed, fps, prof)
    limit = max_effects(prof.format, total / fps, style)
    plan.warnings += [f"SFX: {text}" for _, text in rules(cues_of(plan.sfx, fps), ctx, fps, limit, prof.format in ("reel", "commercial"))]
    plan.sfx_info = {"mode": mode, "style": style or "standard", "limit": limit, "voice_lufs": opts["voice_lufs"],
                     "voice_source": opts.get("voice_source", "")}


def cues_of(placed: list, fps: float, starts: list[int] | None = None) -> list[dict]:
    """The rule view of placed effects; starts = positions read back from the timeline."""
    out = []
    for k, s in enumerate(placed):
        start = starts[k] if starts is not None else s.tl_start
        out.append({"label": f"S{s.index} {s.id}", "start": start, "event": start + s.hit_ms / 1000 * fps, "end": start + s.audible_ms / 1000 * fps,
                    "target_end": s.target_end, "deliberate": s.deliberate, "category": s.category, "kind": s.kind, "span_ms": s.audible_ms,
                    "under_overlay": s.under_overlay})
    return out


def fit_length(x: np.ndarray, seconds: float, fade_s: float, overlap_s: float = 0.25) -> np.ndarray:
    """Cuts or loops x to a length (crossfaded joins), with soft ends. Only ever on a copy."""
    n = int(seconds * SR)
    o = min(int(overlap_s * SR), len(x) // 3)
    out = x[:n].copy()
    while len(out) < n:
        r = np.linspace(0, 1, o)[:, None]
        joined = out[-o:] * (1 - r) + x[:o] * r
        out = np.concatenate([out[:-o], joined, x[o:]])
    out = out[:n]
    f = min(int(fade_s * SR), n // 2)
    r = np.linspace(0, 1, f)[:, None] ** 1.5
    out[:f] *= r
    out[-f:] *= r[::-1]
    return out


def write_wav(path: Path, x: np.ndarray) -> None:
    raw = (np.clip(x, -1, 1) * (2 ** 31 - 1)).astype("<i4").tobytes()
    platforms.run([_bin("ffmpeg"), "-y", "-nostdin", "-v", "error", "-f", "s32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_s24le", str(path)], input=raw, check=True)


def stage_files(placed: list, folder: Path) -> dict[int, str]:
    """index → file for Resolve. Shipped effects are copied next to the export, since the path inside the extension changes with every update and a
    project must not go offline. Beds and sequences get their own copy at the needed length (the original stays as it is)."""
    lib, out = library_dir(), {}
    for s in placed:
        src = Path(s.file)
        if s.length_ms:
            dst = Path(folder) / "sfx" / f"{src.stem}_{hashlib.sha256(src.read_bytes()).hexdigest()[:8]}_{s.length_ms}ms.wav"
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                fade = min(0.8, max(0.3, s.length_ms / 5000)) if s.category == "atmo" else 0.15 if s.kind == "bed" else 0.03
                write_wav(dst, fit_length(decode(src), s.length_ms / 1000, fade))
            out[s.index] = str(dst)
        elif lib in src.parents:  # content in the name: a newer library never changes the sound of a finished timeline
            dst = Path(folder) / "sfx" / f"{src.stem}_{hashlib.sha256(src.read_bytes()).hexdigest()[:8]}.wav"
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                platforms.copy(src, dst)
            out[s.index] = str(dst)
        else:
            out[s.index] = s.file
    return out
