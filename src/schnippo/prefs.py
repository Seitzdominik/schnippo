"""Answers from the onboarding and its state, kept next to the user's config (preferences.json). Defaults for every job, each job can still override them.

Precedence for format, style, language and sound: what the user set away from the default in the extension settings wins, otherwise the onboarding answer. The settings always
arrive as environment variables, also when nobody touched them, so "set" alone says nothing."""

from __future__ import annotations

from . import platforms
import json
import os
from pathlib import Path

VERSION = 1  # raise it and add to NEWS when a later onboarding has something to show
NEWS: dict[int, str] = {}
DEFAULTS = {"format": "auto", "style": "ruhig-dicht", "language": "de", "sfx": "subtil"}
FORMATS = {"reels": "reel", "reel": "reel", "youtube": "youtube", "kurse": "course", "kurs": "course", "course": "course", "interviews": "youtube", "interview": "youtube",
           "werbung": "commercial", "commercial": "commercial", "automatisch": "auto", "auto": "auto", "automatisch erkennen": "auto"}
STYLES = {"ruhig": "ruhig", "ausgewogen": "ruhig-dicht", "ruhig-dicht": "ruhig-dicht", "dicht": "dicht"}
LANGUAGES = {"deutsch": "de", "de": "de", "englisch": "en", "english": "en", "en": "en"}
SOUNDS = {"aus": "off", "off": "off", "subtil": "subtil", "normal": "normal"}


def path() -> Path:
    from .config import config_path
    return config_path().parent / "preferences.json"


def load() -> dict:
    p = path()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    data.setdefault("onboarding", {"done": False, "version": 0, "later": 0})
    data.setdefault("preferences", {})
    return data


def save(data: dict) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    platforms.replace(tmp, p)


def apply(cfg, data: dict | None = None) -> None:
    """Onboarding answers into the config, unless the extension settings say otherwise."""
    prefs = (data or load())["preferences"]
    env = {"format": ("SCHNIPPO_FORMAT", "format"), "style": ("SCHNIPPO_STYLE", "style"), "language": ("SCHNIPPO_LANGUAGE", "language"), "sfx": ("SCHNIPPO_SFX_MODE", "sfx_mode")}
    for key, (name, attr) in env.items():
        given = (os.environ.get(name) or "").strip().lower()
        if key in prefs and (not given or given.startswith("${") or given == DEFAULTS[key]):
            setattr(cfg, attr, prefs[key])
    if prefs.get("content_type"):
        cfg.content_type = prefs["content_type"]
    if "graphics" in prefs:
        cfg.graphics = bool(prefs["graphics"])
    if prefs.get("projects_folder") and cfg.projects_folder is None:
        cfg.projects_folder = Path(prefs["projects_folder"]).expanduser()


def normalize(cfg) -> None:
    """What the settings form lets through as free text: friendly words become the real values, typos become a visible note instead of a silent default."""
    for attr, table, valid, default in (("format", FORMATS, "auto, reel, youtube, course, commercial", "auto"), ("sfx_mode", SOUNDS, "off, subtil, normal", "subtil")):
        v = str(getattr(cfg, attr)).strip().lower()
        if v in table:
            setattr(cfg, attr, table[v])
        else:
            cfg.setting_problems.append(f"{'Format' if attr == 'format' else 'Sound-Effekte'}: „{getattr(cfg, attr)}“ gibt es nicht. Gültig: {valid}. Vorerst gilt {default}.")
            setattr(cfg, attr, default)
    v = str(cfg.language).strip().lower()
    if v in LANGUAGES:
        cfg.language = LANGUAGES[v]
    elif not (len(v) == 2 and v.isalpha()):
        cfg.setting_problems.append(f"Sprache: „{cfg.language}“ ist kein Sprachcode. Gültig: zwei Buchstaben wie de oder en. Vorerst gilt de.")
        cfg.language = "de"


def read_answers(answers: dict) -> tuple[dict, list[str]]:
    """Free text answers → stored values. Whatever is not understood stays out and is reported."""
    from .guard import clean_path
    out, bad = {}, []
    for key, table in (("format", FORMATS), ("style", STYLES), ("language", LANGUAGES), ("sfx", SOUNDS)):
        if answers.get(key) in (None, ""):
            continue
        v = str(answers[key]).strip().lower()
        if v in table:
            out[key] = table[v]
        elif key == "language" and len(v) == 2 and v.isalpha():
            out[key] = v
        else:
            bad.append(f"{key}: „{answers[key]}“")
    if str(answers.get("format") or "").strip().lower() in ("interview", "interviews"):
        out["content_type"] = "interview"
    g = answers.get("graphics")
    if g is not None and g != "":
        v = str(g).strip().lower()
        if v in ("an", "ja", "true", "on", "1"):
            out["graphics"] = True
        elif v in ("aus", "nein", "false", "off", "0"):
            out["graphics"] = False
        else:
            bad.append(f"graphics: „{g}“")
    if answers.get("projects_folder"):
        p = clean_path(answers["projects_folder"])
        if p.is_dir():
            out["projects_folder"] = str(p)
        else:
            bad.append(f"projects_folder: Ordner „{p}“ nicht gefunden")
    return out, bad
