"""User configuration.

Sources, later wins:
  1. built-in defaults
  2. ``config.toml`` in ``~/.config/schnippo`` or ``%APPDATA%\\schnippo`` (or ``$SCHNIPPO_CONFIG``)
  3. environment variables (``GLADIA_API_KEY``, ``SCHNIPPO_CACHE``, ``SCHNIPPO_LANGUAGE``,
     ``SCHNIPPO_EXPORT_FOLDER``, ``SCHNIPPO_FORMAT``, ``SCHNIPPO_STYLE``; set by the .mcpb bundle)
  4. onboarding answers (preferences.json next to the config), see prefs.apply

The API key is never logged, printed or written anywhere by this package.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .platforms import cache_dir, config_dir, key_store

DEFAULT_HARD_FILLERS = [  # German hesitations; NOT "um"/"eh" – real German words ("um zu", "eh schon"), Phase 8 interview
    "äh", "ähm", "öh", "öhm", "hm", "hmm", "mhm", "ehm", "äm", "ähh", "ähmm",
]
EN_HARD_FILLERS = ["uh", "um", "uhm", "erm", "er", "em"]  # only for English transcripts
DEFAULT_RETAKE_WORDS = ["nochmal", "noch mal", "nochmals", "noch einmal", "cut", "schnitt", "stopp", "von vorne", "neu"]
DEFAULT_SOFT_FILLERS = [
    "also", "halt", "quasi", "sozusagen", "irgendwie", "eigentlich", "genau", "ja", "okay", "ok", "naja", "gell",
]


@dataclass
class Config:
    gladia_api_key: str | None = None
    language: str = "de"
    cache_dir: Path = field(default_factory=cache_dir)
    pause_threshold_s: float = 0.4
    long_pause_s: float = 1.5
    hard_fillers: list[str] = field(default_factory=lambda: list(DEFAULT_HARD_FILLERS))
    soft_fillers: list[str] = field(default_factory=lambda: list(DEFAULT_SOFT_FILLERS))
    # gap fallback: voiced activity inside a word gap at least this long -> {?} (filler candidate)
    gap_speech_min_s: float = 0.12
    hug_max_s: float = 0.12  # activity touching a word and shorter than this = word tail, ignored
    bridge_min_s: float = 0.2  # activity filling a whole gap between two words must be this long to count
    clamp_silence_s: float = 0.3  # silence of this length inside a word timestamp is cut off the word
    acoustic_delta_db: float = 25.0  # activity threshold above the measured noise floor
    guides_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "data" / "guides")
    export_folder: Path | None = None  # None → <material folder>/schnippo-export
    content_type: str = "auto"  # auto | interview | course | commercial | talking_head: what is cut, independent of the format
    format: str = "auto"  # auto (detected from the material, ask when unclear) | reel | youtube | course | commercial
    style: str = "ruhig-dicht"  # ruhig | ruhig-dicht | dicht
    profile_overrides: dict = field(default_factory=dict)
    projects_folder: Path | None = None  # projects by name
    update_check: bool = True  # GitHub Releases, once a day
    setting_problems: list[str] = field(default_factory=list)  # values from the settings that were not understood
    graphics: bool = True  # False: no motion pass unless asked for
    sfx_mode: str = "subtil"  # off | subtil | normal
    sfx_folder: Path | None = None  # own sound effects (category from folder/file name, licence with the user)
    freesound_api_key: str | None = None  # optional, never logged
    elevenlabs_api_key: str | None = None  # optional, never logged
    motion_sandbox: bool = False  # free HTML graphics (seek contract checked, tokens, safe zone, no network)
    gladia_key_source: str | None = None  # Erweiterung | Umgebungsvariable | Config-Datei (never the key itself)  # [profile] / [profile.reel] / [profile.youtube]
    segment_pause_s: float = 0.7
    retake_window_s: float = 90.0
    retake_words: list[str] = field(default_factory=lambda: list(DEFAULT_RETAKE_WORDS))  # spoken retake markers
    clap_markers: bool = True  # hand clap after a slip = retake marker (README "So nimmst du auf")
    broll_max_confidence: float = 0.25  # clip = B-roll if no words or mean ASR confidence below (measured: hallucinations 0.04–0.14, speech ≥ 0.35)
    gladia_model: str = "solaria-3"
    gladia_price_usd_per_hour: float = 0.61  # assumption (pay-as-you-go list price) – shown with every estimate, adjustable
    transcribe_confirm_over_min: float = 30.0  # uncached audio above this → estimate first, transcribe(confirm=true) to start
    gladia_diarization: bool = True  # speaker IDs (interviews); part of the transcript cache key
    gladia_custom_vocabulary: list[str] = field(default_factory=list)
    gladia_poll_timeout_s: float = 900.0
    resolve_bin_prefix: str = ""

    def profile(self, fmt: str | None = None, style: str | None = None, layout: str | None = None):
        """fmt must be concrete (reel | youtube | course | commercial); "auto" is resolved by the workspace."""
        from .profiles import make_profile
        f = fmt if fmt not in (None, "auto") else (self.format if self.format != "auto" else "reel")
        return make_profile(f, style or self.style, self.profile_overrides, layout)

    def __repr__(self) -> str:  # never leak the key
        return f"Config(language={self.language!r}, cache_dir={str(self.cache_dir)!r}, key={'set' if self.gladia_api_key else 'unset'})"


def config_path() -> Path:
    return Path(os.environ.get("SCHNIPPO_CONFIG", config_dir() / "config.toml"))


def load_config() -> Config:
    from .migrate import run as migrate
    migrate()  # the working title's folders, once
    cfg = Config()
    p = config_path()
    if p.exists():
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        g = data.get("gladia", {})
        cfg.gladia_api_key = g.get("api_key") or cfg.gladia_api_key
        if g.get("api_key"):
            cfg.gladia_key_source = f"Config-Datei ({p.name})"
        cfg.gladia_custom_vocabulary = g.get("custom_vocabulary", cfg.gladia_custom_vocabulary)
        cfg.gladia_model = g.get("model", cfg.gladia_model)
        cfg.gladia_diarization = bool(g.get("diarization", cfg.gladia_diarization))
        cfg.gladia_price_usd_per_hour = float(g.get("price_usd_per_hour", cfg.gladia_price_usd_per_hour))
        cfg.transcribe_confirm_over_min = float(g.get("confirm_over_min", cfg.transcribe_confirm_over_min))
        cfg.gladia_poll_timeout_s = float(g.get("poll_timeout_s", cfg.gladia_poll_timeout_s))
        cfg.language = data.get("language", cfg.language)
        cfg.format = data.get("format", cfg.format)
        cfg.style = data.get("style", cfg.style)
        cfg.profile_overrides = dict(data.get("profile", {}))
        cfg.motion_sandbox = bool(data.get("motion", {}).get("sandbox", cfg.motion_sandbox))
        cfg.sfx_mode = data.get("sfx", {}).get("mode", cfg.sfx_mode)
        cfg.update_check = bool(data.get("updates", {}).get("check", cfg.update_check))
        if data.get("projects_folder"):
            cfg.projects_folder = Path(data["projects_folder"]).expanduser()
        if data.get("sfx", {}).get("folder"):
            cfg.sfx_folder = Path(data["sfx"]["folder"]).expanduser()
        cfg.freesound_api_key = data.get("sfx", {}).get("freesound_api_key") or cfg.freesound_api_key
        cfg.elevenlabs_api_key = data.get("sfx", {}).get("elevenlabs_api_key") or cfg.elevenlabs_api_key
        if "guides_dir" in data:
            cfg.guides_dir = Path(data["guides_dir"]).expanduser()
        if data.get("export_folder"):
            cfg.export_folder = Path(data["export_folder"]).expanduser()
        if "cache_dir" in data:
            cfg.cache_dir = Path(data["cache_dir"]).expanduser()
        a = data.get("analysis", {})
        cfg.pause_threshold_s = float(a.get("pause_threshold_s", cfg.pause_threshold_s))
        cfg.long_pause_s = float(a.get("long_pause_s", cfg.long_pause_s))
        cfg.hard_fillers = a.get("hard_fillers", cfg.hard_fillers)
        cfg.soft_fillers = a.get("soft_fillers", cfg.soft_fillers)
        cfg.gap_speech_min_s = float(a.get("gap_speech_min_s", cfg.gap_speech_min_s))
        cfg.hug_max_s = float(a.get("hug_max_s", cfg.hug_max_s))
        cfg.bridge_min_s = float(a.get("bridge_min_s", cfg.bridge_min_s))
        cfg.clamp_silence_s = float(a.get("clamp_silence_s", cfg.clamp_silence_s))
        cfg.acoustic_delta_db = float(a.get("acoustic_delta_db", cfg.acoustic_delta_db))
        cfg.segment_pause_s = float(a.get("segment_pause_s", cfg.segment_pause_s))
        cfg.retake_window_s = float(a.get("retake_window_s", cfg.retake_window_s))
        cfg.broll_max_confidence = float(a.get("broll_max_confidence", cfg.broll_max_confidence))
        cfg.retake_words = list(a.get("retake_words", cfg.retake_words))
        cfg.clap_markers = bool(a.get("clap_markers", cfg.clap_markers))
    def env(name: str) -> str | None:
        """Bundle user_config values arrive as env vars; unset optional fields come as "" or a literal ${…}."""
        v = os.environ.get(name, "").strip()
        return v if v and not v.startswith("${") else None

    if env("GLADIA_API_KEY"):
        cfg.gladia_api_key = env("GLADIA_API_KEY")
        cfg.gladia_key_source = "Erweiterung (Einstellungen in Claude)" if os.environ.get("SCHNIPPO_BUNDLE") else "Umgebungsvariable GLADIA_API_KEY"
    if env("SCHNIPPO_CACHE"):
        cfg.cache_dir = Path(env("SCHNIPPO_CACHE")).expanduser()
    if env("SCHNIPPO_LANGUAGE"):
        cfg.language = env("SCHNIPPO_LANGUAGE")
    for name, attr in (("SCHNIPPO_FORMAT", "format"), ("SCHNIPPO_STYLE", "style")):
        if env(name):
            setattr(cfg, attr, env(name).lower())
    if env("SCHNIPPO_SFX_MODE"):
        cfg.sfx_mode = env("SCHNIPPO_SFX_MODE").lower()
    if env("SCHNIPPO_SFX_FOLDER"):
        cfg.sfx_folder = Path(env("SCHNIPPO_SFX_FOLDER")).expanduser()
    if env("FREESOUND_API_KEY"):
        cfg.freesound_api_key = env("FREESOUND_API_KEY")
    if env("ELEVENLABS_API_KEY"):
        cfg.elevenlabs_api_key = env("ELEVENLABS_API_KEY")
    if env("SCHNIPPO_EXPORT_FOLDER"):
        cfg.export_folder = Path(env("SCHNIPPO_EXPORT_FOLDER")).expanduser()
    if env("SCHNIPPO_PROJECTS_FOLDER"):
        cfg.projects_folder = Path(env("SCHNIPPO_PROJECTS_FOLDER")).expanduser()
    if (env("SCHNIPPO_UPDATE_CHECK") or "").lower() in ("0", "false", "aus", "off", "nein"):
        cfg.update_check = False
    from . import prefs
    prefs.apply(cfg)
    prefs.normalize(cfg)
    if not cfg.gladia_api_key:
        from .keychain import read
        cfg.gladia_api_key = read("gladia")
        cfg.gladia_key_source = key_store() if cfg.gladia_api_key else cfg.gladia_key_source
    cfg.freesound_api_key = cfg.freesound_api_key or _keychain("freesound")
    cfg.elevenlabs_api_key = cfg.elevenlabs_api_key or _keychain("elevenlabs")
    return cfg


def _keychain(account: str) -> str | None:
    from .keychain import read
    return read(account)
