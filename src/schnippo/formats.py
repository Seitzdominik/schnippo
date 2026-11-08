"""Format from the material (reel | youtube | course | commercial). Step 1 – Reel vs. landscape from the material: aspect ratio of the main clip (rotation-aware), speech in the raw material,
script length (~130 words/min German) and an optional hint from the chat. Below the confidence threshold or with
contradicting signals the result says "ask" – Claude asks the user instead of guessing.
Step 2 (refine, needs transcripts) – landscape material is split into youtube / course / commercial by content signals:
speakers (interview → youtube), course vocabulary and calm monologue takes (course), many silent B-roll clips plus short
repeated takes (commercial)."""

from __future__ import annotations

from dataclasses import dataclass, field

WORDS_PER_MIN = 130
ASK_BELOW = 0.75


@dataclass
class Detection:
    format: str  # reel | youtube
    confidence: float
    reasons: list[str] = field(default_factory=list)
    ask: bool = False
    conflict: str = ""
    orient: str | None = None
    scores: dict = field(default_factory=dict)
    content_type: str | None = None  # what is being cut, independent of the delivery format; None before the transcripts are known

    def text(self) -> str:
        head = f"{self.format} ({self.confidence:.2f}): " + ", ".join(self.reasons)
        if self.ask:
            head += f" → bitte beim Nutzer nachfragen{': ' + self.conflict if self.conflict else ''}"
        return head


CONTENT_TYPES = ("interview", "course", "commercial", "talking_head")
CONTENT_LABELS = {"interview": "Interview", "course": "Kurs", "commercial": "Werbung", "talking_head": "Talking Head"}
CONTENT_WORDS = {"interview": "interview", "interviews": "interview", "gespräch": "interview", "kurs": "course", "kurse": "course", "course": "course", "kursvideo": "course",
                 "werbung": "commercial", "werbefilm": "commercial", "werbespot": "commercial", "commercial": "commercial",
                 "talking head": "talking_head", "talking_head": "talking_head", "talkinghead": "talking_head", "monolog": "talking_head", "ansprache": "talking_head"}


def content_of(fmt: str, speakers: int) -> str:
    """Two people talking is an interview in every format, a reel of one included. Otherwise the format says what it is."""
    if speakers >= 2:
        return "interview"
    return fmt if fmt in ("course", "commercial") else "talking_head"


def _mmss(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def detect(clips: list, speech_s: float, raw_s: float, script_words: int | None = None, hint: str | None = None) -> Detection:
    """clips: Clip models (main clip first). Scores: + for reel, − for youtube, weighted."""
    score, weight, reasons = 0.0, 0.0, []
    orient = None
    if clips:
        c = clips[0]
        w, h = (c.height, c.width) if abs(c.rotation) % 180 == 90 else (c.width, c.height)
        if w and h:
            ratio = w / h
            if ratio < 0.8:
                orient, s = "hoch", 1.0
            elif ratio > 1.25:
                orient, s = "quer", -1.0
            else:
                orient, s = "quadratisch", 0.0
            score += 3.0 * s
            weight += 3.0
            reasons.append(f"{w}×{h} ({'9:16' if abs(ratio - 9 / 16) < 0.02 else '16:9' if abs(ratio - 16 / 9) < 0.02 else f'{ratio:.2f}'}, {orient})")
    reasons.append(f"{_mmss(raw_s)} Rohmaterial, {_mmss(speech_s)} Sprechanteil")
    # speech: a reel is cut from a few minutes, a YouTube video from 10+ minutes of speech
    s_speech = 1.0 if speech_s <= 300 else -1.0 if speech_s >= 900 else (600 - speech_s) / 300
    score += 2.0 * max(-1.0, min(1.0, s_speech))
    weight += 2.0
    est = None
    if script_words:
        est = script_words / WORDS_PER_MIN * 60
        s_script = 1.0 if est <= 90 else -1.0 if est >= 300 else (195 - est) / 105
        score += 2.5 * max(-1.0, min(1.0, s_script))
        weight += 2.5
        reasons.append(f"Skript ≈ {_mmss(est)} ({script_words} Wörter)")
    fam_hint = {"reel": "reel", "youtube": "youtube", "course": "youtube"}.get(hint or "")
    if fam_hint:
        hint = fam_hint
    if hint in ("reel", "youtube"):
        score += 4.0 * (1.0 if hint == "reel" else -1.0)
        weight += 4.0
        reasons.append(f"Hinweis aus dem Chat: {hint}")
    fmt = "reel" if score >= 0 else "youtube"
    conf = round(0.5 + 0.5 * abs(score) / weight, 2) if weight else 0.5
    conflict = ""
    long_content = speech_s >= 900 or (est is not None and est >= 300)
    short_content = (est is not None and est <= 90) or (est is None and speech_s <= 120)
    if orient == "hoch" and long_content:
        conflict = "Hochformat, aber langer Inhalt"
    elif orient == "quer" and short_content:
        conflict = "Querformat, aber kurzer Inhalt"
    det = Detection(fmt, conf, reasons, ask=bool(conflict) or conf < ASK_BELOW, conflict=conflict, orient=orient)
    if hint in ("reel", "youtube") and not conflict:
        det.ask = False
    return det


COURSE_WORDS = ("willkommen zum", "willkommen im", "kurs", "lektion", "modul", "kapitel", "in diesem video", "lernst du",
                "übung", "schritt für schritt", "guide", "tutorial", "anleitung", "teil 1", "teil 2")


def refine(base: Detection, *, speakers: int, aroll_clips: int, broll_clips: int, longest_take_speech_s: float,
           aroll_speech_s: float, text: str, hint: str | None = None) -> Detection:
    """Split by content. Scores (calibrated on the Phase-8 material: interview, course, commercial):
    youtube  1 base + 1.5 interview (≥ 2 speakers with ≥ 5 % of the words each) + 1 long speech (≥ 10 min)
    course   up to 2 course vocabulary + 0.5 single speaker + 0.5 takes of 20 s–10 min speech + 0.5 several takes
    commercial 1 many B-roll clips (≥ 3 and ≥ half as many as takes) + 1.5 short takes (≤ 45 s speech) + 1 little speech (≤ 2 min)
    A portrait main clip stays reel unless commercial scores ≥ 3 (then commercial in portrait layout)."""
    low = " " + text.lower() + " "
    hits = sorted({w for w in COURSE_WORDS if w in low})
    sc = {"youtube": 1.0, "course": 0.0, "commercial": 0.0}
    why: dict[str, list[str]] = {k: [] for k in sc}
    if speakers >= 2:
        sc["youtube"] += 1.5
        why["youtube"].append(f"{speakers} Sprecher (Interview)")
    if aroll_speech_s >= 600:
        sc["youtube"] += 1.0
        why["youtube"].append("viel Sprache")
    if hits:
        sc["course"] += min(2.0, 0.8 * len(hits))
        why["course"].append("Kurs-Wörter: " + ", ".join(hits[:4]))
    if speakers <= 1:
        sc["course"] += 0.5
    if 20 <= longest_take_speech_s <= 600:
        sc["course"] += 0.5
    if aroll_clips >= 3:
        sc["course"] += 0.5
        why["course"].append(f"{aroll_clips} Takes")
    if broll_clips >= 3 and broll_clips >= 0.5 * aroll_clips:
        sc["commercial"] += 1.0
        why["commercial"].append(f"{broll_clips} B-Roll-Clips")
    if longest_take_speech_s <= 45:
        sc["commercial"] += 1.5
        why["commercial"].append(f"kurze Takes (≤ {longest_take_speech_s:.0f} s Sprache)")
    if aroll_speech_s <= 120:
        sc["commercial"] += 1.0
        why["commercial"].append("wenig Text")
    if hint in sc:
        sc[hint] += 4.0
        why[hint].append("Hinweis aus dem Chat")
    if base.format == "reel" or base.orient == "hoch":
        if sc["commercial"] >= 3.0 and hint != "reel":
            fmt = "commercial"
        else:
            base.content_type = content_of(base.format, speakers)
            return base
    else:
        fmt = max(sc, key=sc.get)
    ranked = sorted(sc.values(), reverse=True)
    best, second = sc[fmt], (ranked[1] if ranked[0] == sc[fmt] else ranked[0])
    conf = round(min(0.95, 0.5 + 0.5 * max(0.0, best - second) / max(best, 1e-6)), 2)
    if base.orient not in ("hoch", "quer"):  # square / unknown picture: keep the doubt of step 1
        conf = min(conf, base.confidence)
    reasons = list(base.reasons) + (why[fmt] or ["keine besonderen Merkmale"])
    det = Detection(fmt, conf, reasons, ask=conf < ASK_BELOW, orient=base.orient,
                    scores={k: round(v, 1) for k, v in sc.items()}, content_type=content_of(fmt, speakers))
    if hint in sc or hint == "reel":
        det.ask = False
    return det
