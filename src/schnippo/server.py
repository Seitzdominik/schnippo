"""MCP server (stdio). Tool outputs are compact text, not JSON dumps.

Note: the brief says FastMCP; in mcp>=2 the class was renamed to MCPServer (same decorator API).
"""

from __future__ import annotations

from . import platforms
import functools
import logging
import sys

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.utilities.types import Image
from mcp.types import CallToolResult, TextContent
from pathlib import Path

from typing import Annotated

from pydantic import Field

from .branding import DISPLAY_NAME, SLUG
from .config import load_config
from .media import MediaError
from .resolve_bridge import BuildError, ResolveUnavailable, build_timeline as _build
from .cutlist import Cutlist
from pydantic import ValidationError
import json
from .transcribe.base import TranscriptionError
from .formatting import format_transcript, parse_word_ref, ts
from .resolve_bridge import ResolveBridge
from .workspace import Workspace

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

WORKFLOW = """Ablauf in vier Durchgängen, jeder mit genau einem Job und einer eigenen Timeline (nie überschreiben):
0. Einrichtung: beim ersten Kontakt oder auf „Richte mich ein“ check_setup aufrufen und fehlende Punkte erklären.
   ingest_folder (import_to_resolve=true) zeigt Clips, A-/B-Roll und das erkannte Format (reel | youtube | course |
   commercial); bei „nachfragen“ detect_format (Auswahlkarte) und erst nach der Antwort schneiden. transcribe zeigt vorher
   Audio, Kosten und Dauer; ab 30 min neuem Audio erst nach OK des Nutzers mit confirm=true.
1. Rough Cut (Inhalt, Reihenfolge, Take-Wahl, Laufzeit; nur harte Schnitte): get_edit_context(pass="rough") (lange
   Videos: overview=true, dann page=N) → Cutlist {"name": …, "pass": "rough", …} → validate_cutlist (Endtext mitlesen)
   → build_timeline → <Name>_V1_Rough. Interview: Fragen (S2) je nach Fassung raus oder kurz behalten, Vorgespräch raus.
   Retake-Marker („nochmal“, Klatscher) markieren den Satz davor. Werbespot/Szenen ohne Skript: VOR dem Rough Cut mit
   get_frames("clips") Szenen bilden, Reihenfolge per show_review(decisions=[{kind: "reihenfolge", frame: …}]) bestätigen
   lassen – nie eigenmächtig umstellen; ein Storyboard/eine Shotlist gilt als Skript.
   ⏸ Danach show_review(timeline, decisions=[…]) mit Grenzfällen (note "Grenzfall: …"), verworfenen Inhalten, inhaltlichen
   Widersprüchen und knappen Take-Entscheidungen (je kind, question, words/segment, recommendation). Die Antworten kommen
   als Nachricht zurück (behalten/raus/egal) → in der Cutlist des nächsten Durchgangs umsetzen. Erst nach Antwort weiter.
2. Fine Cut (Rhythmus, unsichtbare Schnitte, Punch-ins, Atempausen): get_edit_context(pass="fine", include_guide=true,
   overview=true reicht) → {"pass": "fine", "base_cutlist": "<Name>_V1_Rough", "punch_in": {"mode": "alternate"},
   "beats": [{"after": "c01:w0330", "beat": "key"|"section"}], …} (lange Formate: Pflicht, etwa ein Beat je 30–60 s) →
   validate_cutlist → preview_cuts bei ⚠ → build_timeline → <Name>_V2_Fine.
   ⏸ Wieder show_review (auffällige Schnitte, geänderte Takes, bewusste Pausen), erst nach Antwort weiter.
3. B-Roll (nur Bilder ergänzen, Schnitt bleibt): get_frames("stills") / get_frames("broll") (Video-B-Roll mit Frame-IDs)
   → {"pass": "broll", "base_cutlist": "<Name>_V2_Fine", "overlays": […]} (Video: media "c05" + from_frame, stumm; optional
   audio "atmo", slowmo) → validate_cutlist → build_timeline → <Name>_V3_BRoll. Kein passendes Bild → keine B-Roll.
   Sound-Effekte: im B-Roll- oder Motion-Durchgang "sfx": […] nach guides/06_sound_design.md (list_sfx zeigt die Bibliothek).
   Neues Projekt: create_project anbieten. Liegt ein brief.md im Projekt, lies ihn vor dem Rough Cut (steht in get_edit_context) und richte Auswahl, Hook und Länge danach aus.
   Reels aus dem fertigen langen Video: get_edit_context(pass="reel", include_guide=true), find_reel_candidates → show_reel_candidates (Nutzer wählt) → reel_cutlist → validate_cutlist →
   build_timeline → reel_sheet → run_qc(audio=true) → sense_check → export_reels. Die lange Fassung bleibt unangetastet.
4. Polish (Ton, QC, Export): analyze_audio → {"pass": "polish", "base_cutlist": "<Name>_V3_BRoll", "audio":
   {"target_lufs": -14}} → build_timeline → <Name>_V4_Polish → run_qc(timeline, audio=true) →
   export_final(timeline) (Reel 1080×1920 oder YouTube 1080p/4K, H.264, geprüft, SRT/TXT daneben).
Korrekturen danach: Was der Nutzer meint („#05“ = Marker in Resolve, Zeit „0:23“, Zitat) mit locate finden →
revise(base_timeline, [Operationen]) baut eine neue Version <Timeline>_r2 und zeigt den Unterschied. Hat der Nutzer in
Resolve selbst geschnitten: read_timeline_changes(timeline) übernimmt das framegenau; „Unklar“-Punkte nachfragen.
Abgebrochen (Absturz, Resolve zu, App beendet)? resume_job() setzt den letzten Auftrag fort; halbe Timelines heißen
„…_unvollstaendig“. Große Caches: clear_cache().
Abschlussbericht an den Nutzer: Laufzeit, Lautheit/True Peak, Anzahl Schnitte/Punch-ins/Overlays, QC-Ergebnis, Pfade der
Exportdateien (Video, SRT/TXT), offene Grenzfälle und inhaltliche Fragen. Hinweis: einmal bei 1× komplett ansehen, einmal
bei 1,25× auf Längen."""

INSTRUCTIONS = f"""{DISPLAY_NAME}: Rohschnitt für DaVinci Resolve Studio.
EIGENNAMEN: Namen von Personen, Firmen, Orten, Adressen nie raten. Meldet transcribe „Eigennamen unsicher“ oder steht ein Name
auf einer Grafik, kurz nachfragen und set_glossary aufrufen (oder glossar.txt im Material-Ordner).
EINRICHTEN: Beim ersten Kontakt und bei JEDER Frage nach Einrichtung, Installation oder Problemen zuerst check_setup
aufrufen – z. B. „einrichten“, „installieren“, „Kannst du {DISPLAY_NAME} einrichten?“, „Richte mich ein“, „funktioniert
nicht“, „verbindet nicht“, „Resolve reagiert nicht“, „Key eintragen“, „set up“, „install“, „not working“, „can't connect“.
Referenziere Material ausschließlich über IDs (Wörter c03:w0120, Segmente c03:s012, Frames c03:f0114, Standbilder i03), nie
über Timecodes – der Server rechnet selbst in Frames um. Flags und Retake-Gruppen sind Hinweise, keine Löschentscheidungen.
Leitfäden je Durchgang: get_edit_context(pass=…) oder Ressourcen schnippo://guides/<pass>.

""" + WORKFLOW

def _version() -> str:
    try:
        from importlib.metadata import version
        return version("schnippo")
    except Exception:
        return "0"


from mcp.types import ToolAnnotations  # noqa: E402
from .toolinfo import TOOLS  # noqa: E402
from . import onboarding as _onb  # noqa: E402
from . import prefs as _prefs  # noqa: E402

mcp = MCPServer(SLUG, title=DISPLAY_NAME, version=_version(), instructions=INSTRUCTIONS + _onb.instruction(_prefs.load()))
_cfg = load_config()
_ws = Workspace(_cfg)
_bridge = ResolveBridge()
from .jobs import Jobs  # noqa: E402

_jobs = Jobs(_ws.cache.root)
EXPECTED = (TranscriptionError, ResolveUnavailable, MediaError, KeyError, LookupError, FileNotFoundError, ValueError,
            BuildError, PermissionError)


CARD_URI = "ui://schnippo/card.html"
CARD_META = {"ui": {"resourceUri": CARD_URI}, "ui/resourceUri": CARD_URI}
_log = logging.getLogger("schnippo")


def _log_client(ctx) -> None:
    """Diagnostics for the cards: does the host announce MCP Apps (io.modelcontextprotocol/ui) to this server?"""
    try:
        caps = ctx.client_capabilities if ctx is not None else None
        ext = getattr(caps, "extensions", None) if caps is not None else None
        _log.info("Host-Fähigkeiten: MCP Apps %s · extensions=%s",
                  "JA" if ext and "io.modelcontextprotocol/ui" in ext else "NEIN", sorted((ext or {}).keys()))
    except Exception as e:  # never break the tool for a log line
        _log.info("Host-Fähigkeiten nicht lesbar: %s", type(e).__name__)


def _card(text: str, data: dict) -> CallToolResult:
    """Text for the model and hosts without MCP Apps + structuredContent for the card."""
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=data)


_first_call = True


def _update_note() -> str | None:
    """Once a day at most, and once per version: the first tool call says when something newer is out."""
    if not _cfg.update_check:
        return None
    from . import updates
    f = _cfg.cache_dir / "update.json"
    info = updates.check(_version(), f)
    if not info:
        return None
    updates.told(f, info["version"])
    return "Sag dem Nutzer kurz: " + updates.text(info)


def _with_hint(name: str, result):
    """Puts the onboarding note in front of a tool result, in whatever form the tool answers."""
    global _first_call
    first, _first_call = _first_call, False
    try:
        state = _prefs.load()
        note, changed = _onb.hint(state, name, first)
        if changed:
            _prefs.save(state)
        if first and not note:
            note = _update_note()
    except Exception as e:  # a damaged preferences file must never stop a tool
        _log.warning("Onboarding-Status nicht lesbar: %s", type(e).__name__)
        return result
    if not note:
        return result
    note = f"[{note}]\n"
    if isinstance(result, str):
        return note + result
    if isinstance(result, list):
        return [note] + result
    if isinstance(result, CallToolResult):
        return CallToolResult(content=[TextContent(type="text", text=note)] + list(result.content), structured_content=result.structured_content)
    return result


def tool(fn=None, **tool_kw):
    """Register a tool; expected failures reach Claude as a readable message (the SDK hides other texts).
    A parameter aliased "pass" (Python keyword) arrives as kwarg "pass" → mapped to pass_name."""
    if fn is None:
        return lambda f: tool(f, **tool_kw)

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        if "pass" in kw:
            kw["pass_name"] = kw.pop("pass")
        _log.info("Tool-Aufruf: %s", fn.__name__)  # Claude's own log does not record tools/call
        try:
            return _with_hint(fn.__name__, fn(*a, **kw))
        except ResolveUnavailable as e:  # not a technical error for the user: what is missing and how to fix it
            raise ToolError(_setup_text(f"Resolve nicht erreichbar ({e}).")) from e
        except ToolError:
            raise
        except EXPECTED as e:
            from .errors import plain
            raise ToolError(plain(e) or (e.args[0] if isinstance(e, KeyError) and e.args else str(e))) from e
        except (AttributeError, TypeError) as e:  # Resolve went away mid-call: API objects turn into None
            if "NoneType" in str(e) and not _resolve_ok():
                raise ToolError(_setup_text("Die Verbindung zu Resolve ist abgebrochen.")) from e
            raise
        except Exception as e:  # known kinds in everyday language with the next step; the rest stays as it is
            from .errors import plain
            msg = plain(e)
            if msg:
                _log.warning("Fehler %s: %s", type(e).__name__, e)
                raise ToolError(msg) from e
            raise
    title, kind = TOOLS[fn.__name__]  # no tool without title and hints
    tool_kw.update(title=title, annotations=ToolAnnotations(title=title, readOnlyHint="r" in kind, destructiveHint="d" in kind, openWorldHint="n" in kind))
    return mcp.tool(**tool_kw)(wrapper)


def _resolve_ok() -> bool:
    try:
        _bridge._resolve = None
        _bridge.resolve()
        return True
    except Exception:
        return False


def _setup_text(head: str) -> str:
    from . import setup_check
    checks = setup_check.run(_cfg, _bridge, material=_ws.folder)
    return head + "\n" + setup_check.text(checks)


@tool
def ingest_folder(path: str, import_to_resolve: bool = False, recursive: bool = False) -> str:
    """Scan a folder of takes: ffprobe metadata, VFR check, stable clip IDs (c01…). path: a folder, pasted in any form, or just a project name from the projects folder.
    A-Roll/, B-Roll/, Bilder/ and Skript/ (also Interview, Footage, Images, Script …) are read as such. Unsorted folders: show the classification briefly for confirmation.
    Optionally import all clips into a Resolve Media Pool bin named after the folder."""
    res = _ws.ingest(_project_path(path), import_to_resolve=import_to_resolve, recursive=recursive, bridge=_bridge)
    lines = [f"{len(res['clips'])} Clips, {len(res['stills'])} Standbilder aus {res['folder']}"]
    lines += [_ws.list_clips_text().split("\n", 1)[1]] if res["clips"] or res["stills"] else []
    if res["resolve"]:
        lines.append(f"Resolve: Bin „{res['resolve']['bin']}“, {res['resolve']['imported']} Clips im Media Pool")
    lines += [f"Hinweis: {n}" for n in res["notes"]]
    lines += [f"Hinweis: {n}" for n in _ws.role_notes()]
    if res["clips"]:
        lines.append(_format_line())
    from .projects import brief_text, has_structure
    if not has_structure(_ws.folder):
        lines.append("Unsortierter Ordner: Nach der Transkription zeige ich die Einordnung in A-Roll und B-Roll kurz zur Bestätigung.")
    if brief_text(_ws.folder):
        lines.append("Brief gefunden: Er steht in get_edit_context, Format, Länge und Kernbotschaft daraus übernehmen.")
    return "\n".join(lines)


def _project_path(text: str) -> str:
    """A folder or, with a projects folder set, a project name."""
    from .guard import clean_path
    p = clean_path(text)
    if p.is_dir() or "/" in str(text) or _cfg.projects_folder is None:
        return str(p)
    from .projects import find
    return str(find(str(text).strip().strip('"„“'), _cfg.projects_folder))


@tool
def create_project(name: str) -> str:
    """New project in the projects folder: <date>_<name> with A-Roll, B-Roll, Bilder, Skript, an empty glossar.txt and a brief.md template. Offer it when the user starts something new."""
    from .guard import check_write_dir
    from .projects import create
    if _cfg.projects_folder is None:
        raise ValueError("Noch kein Standardordner eingestellt. Nenne mir einen Ordner für deine Projekte, dann merke ich ihn mir.")
    p, existed = create(name, check_write_dir(_cfg.projects_folder))
    return (f"Projekt {'gab es schon' if existed else 'angelegt'}: {p}\nTakes nach A-Roll, Videos ohne Sprache nach B-Roll, Standbilder nach Bilder. glossar.txt und brief.md helfen, sind aber optional. "
            "Danach: ingest_folder mit dem Projektnamen.")


@tool
def store_api_key(service: str = "gladia") -> str:
    """Saves an API key in the system's credential store (macOS keychain, Windows Credential Manager) for hosts without a settings form (plugin, other MCP programs). A system window asks for it: never ask for a key in the chat, it must not reach the model.
    service: gladia | freesound | elevenlabs."""
    from . import keychain
    if service not in keychain.SERVICES:
        raise ValueError("service: gladia | freesound | elevenlabs")
    key = keychain.ask(keychain.SERVICES[service])
    if not key:
        return "Abgebrochen, es wurde nichts gespeichert."
    if not keychain.write(service, key):
        return f"Der Key ließ sich nicht in der {platforms.key_store()} speichern." if platforms.is_windows() else "Der Key ließ sich nicht im Schlüsselbund speichern."
    setattr(_cfg, {"gladia": "gladia_api_key", "freesound": "freesound_api_key", "elevenlabs": "elevenlabs_api_key"}[service], key)
    if service == "gladia":
        _cfg.gladia_key_source = platforms.key_store()
    return f"{keychain.SERVICES[service]}-Key in {platforms.key_store_place()} gespeichert."


@tool
def onboarding(step: str = "willkommen", answers: dict | None = None) -> str:
    """First-start tour, also for "Wie funktioniert das?", "Zeig mir, was du kannst", "Onboarding wiederholen". You lead, keep every message short, always skippable. step: willkommen → einrichtung →
    vorlieben (answers: format, style, language, graphics, sfx, projects_folder; {} = all recommendations) → tipps → test (answers: folder) → abschluss; also spaeter, kenne_mich_aus, wiederholen.
    Follow the bracket at the end of each result."""
    from . import setup_check
    state = _prefs.load()
    if step == "willkommen":
        return _onb.welcome()
    if step == "wiederholen":
        text = _onb.repeat(state)
        _prefs.save(state)
        return text
    if step == "spaeter":
        text = _onb.later(state)
        _prefs.save(state)
        return text
    if step in ("einrichtung", "kenne_mich_aus"):
        checks = setup_check.run(_cfg, _bridge, material=_ws.folder)
        missing = [f"• {c.label}" + (f": {c.fix}" if c.fix else "") for c in checks if c.ok is False]
        if step == "einrichtung":
            return _onb.setup(missing)
        text = _onb.finish(state, _cfg.projects_folder)
        _prefs.save(state)
        return (_onb.setup(missing).split("\n\n[")[0] + "\n\n" + text)
    if step == "vorlieben":
        if answers is None:
            return _onb.questions(state["preferences"])
        got, bad = _prefs.read_answers(answers)
        p = {"format": "auto", "style": "ruhig-dicht", "language": "de", "graphics": True, "sfx": "subtil", **state["preferences"], **got}
        state["preferences"] = p
        _prefs.save(state)
        _cfg.format, _cfg.style, _cfg.language, _cfg.graphics, _cfg.sfx_mode = p["format"], p["style"], p["language"], p["graphics"], p["sfx"]
        if p.get("projects_folder"):
            _cfg.projects_folder = Path(p["projects_folder"])
        return _onb.saved_text(p, bad)
    if step == "tipps":
        return _onb.tips()
    if step == "test":
        if not answers or not answers.get("folder"):
            return _onb.test_question()
        res = _ws.ingest(_project_path(answers["folder"]), import_to_resolve=False, bridge=_bridge)
        return _onb.test_estimate(_estimate_text(_ws.transcription_estimate("all")), len(res["clips"]))
    if step == "abschluss":
        text = _onb.finish(state, _cfg.projects_folder)
        _prefs.save(state)
        return text
    raise ValueError("step: willkommen | einrichtung | vorlieben | tipps | test | abschluss | spaeter | kenne_mich_aus | wiederholen")


def _mmss(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def _estimate_text(est: dict) -> str:
    new = [c for c, _, cached in est["clips"] if not cached]
    return (f"Schätzung: {_mmss(est['new_s'])} min Audio neu zu transkribieren ({len(new)} Clips) ≈ {est['cost_usd']:.2f} USD "
            f"(Annahme {est['price']:g} USD/Stunde, in der Konfiguration änderbar), Dauer ≈ {_mmss(est['eta_s'])} min; "
            f"bereits im Cache und kostenlos: {_mmss(est['cached_s'])} min "
            f"({sum(1 for *_, c in est['clips'] if c)} Clips).")


@tool
def transcribe(clip_ids: list[str] | str = "all", provider: str = "gladia", language: str | None = None,
               force: bool = False, confirm: bool = False, ctx: Context | None = None) -> str:
    """Transcribe clips (word timestamps, speaker IDs) and run base analysis. Uses the cache: nothing is transcribed twice
    unless force=True. clip_ids: "all" or e.g. ["c01","c03"]. Above the configured amount of NEW audio (default 30 min)
    it only returns an estimate (audio, cost, duration, free cached clips): show it to the user and call again with
    confirm=true after the OK."""
    est = _ws.transcription_estimate(clip_ids, provider, language, force)
    if est["needs_confirm"] and not confirm:
        return _estimate_text(est) + "\nNoch nichts transkribiert – nach Bestätigung des Nutzers transcribe(confirm=true)."
    job = _jobs.start("transcribe", {"clip_ids": clip_ids, "provider": provider, "language": language, "force": False},
                      f"{len(est['clips'])} Clip(s), {_mmss(est['new_s'])} neu", str(_ws.folder) if _ws.folder else None)
    try:
        res = _ws.transcribe(clip_ids, provider=provider, language=language, force=force,
                             progress=_progress(ctx, "Transkription", len(est["clips"])))
    except Exception as e:
        _jobs.finish(job, "fehlgeschlagen", f"{type(e).__name__}: {e}")
        raise
    failed = [r["clip"] for r in res if "error" in r]
    _jobs.finish(job, "fehlgeschlagen" if failed else "fertig", ("Clips ohne Ergebnis: " + ", ".join(failed)) if failed else None)
    lines = []
    for r in sorted(res, key=lambda r: r["clip"]):
        if "error" in r:
            lines.append(f"{r['clip']}: FEHLER {r['error']}")
            continue
        s = r["stats"]
        src = "Cache" if r["cached"] else f"neu ({r.get('wall_s')} s, abgerechnet {r.get('billing_s') or r.get('audio_s') or '?'} s Audio)"
        lines.append(f"{r['clip']}: {s['words']} Wörter, {s['fillers_asr']} Füllw. (+{s['fillers_inferred']} per Lücke), "
                     f"{s['pauses']} Pausen, {s['repeats']} Wdh., {s['restart_candidates']} Neuanfang-Kand. – {src}")
    names = _ws.unsure_names_text()
    return (_estimate_text(est) + "\n" if est["new_s"] else "") + ("\n".join(lines) or "keine Clips") + ("\n" + names if names else "")


@tool(meta=CARD_META)
def detect_format(hint: str | None = None) -> CallToolResult:
    """Which format? reel (9:16) | youtube (16:9, also interviews) | course (16:9, calmer, chapters, screen recordings)
    | commercial (scenic, short, many B-roll clips). From the main clip's aspect ratio, speech, script length, speakers,
    course vocabulary, B-roll share and take length; optional hint from the chat. Returns format, confidence and reasons;
    if unclear: ASK the user – hosts with MCP Apps show a choice card, otherwise ask in the chat; then set_format.
    The format drives pauses, runtime, punch-ins, chapters, B-roll density, safe zones and graphic sizes."""
    from .profiles import LABELS
    d = _ws.detect_format(hint)
    fmt, src = _ws.effective_format()
    out = [f"Erkannt: {d.text()}", f"Aktiv: {fmt} ({src})"]
    if d.ask and src.startswith("erkannt"):
        out.append("→ Frage den Nutzer: " + " / ".join(f"„{v}“" for v in LABELS.values()) + f" (Empfehlung: {LABELS[d.format]}), "
                   "dann set_format.")
    data = {"view": "format", "recommended": fmt if not src.startswith("erkannt") else d.format, "confidence": d.confidence,
            "ask": d.ask, "reason": ("Erkannt: " if src.startswith("erkannt") else f"Aktiv ({src}). Erkannt: ") + d.text()}
    return _card("\n".join(out), data)


@tool
def set_format(format: str | None = None, content_type: str | None = None) -> str:
    """Fix for this folder what the user said in the chat; that beats the brief, the preferences and the detection. format: reel | youtube | course | commercial | auto (back to detection).
    content_type, independent of the format (a reel can be an interview): interview | course | commercial | talking_head | auto. Stored with the workspace."""
    if format is None and content_type is None:
        raise ValueError("format oder content_type angeben")
    if format is not None:
        _ws.set_format(format.strip().lower())
    if content_type is not None:
        _ws.set_content_type(content_type.strip().lower())
    return f"Format für diesen Ordner: {_ws.effective_format()[0]} ({_ws.effective_format()[1]}) · Inhalt: {_ws.effective_content_type()[0]} ({_ws.effective_content_type()[1]})"


@tool
def set_clip_role(clip_ids: list[str] | str, role: str) -> str:
    """Override the automatic A-roll/B-roll classification: role = aroll | broll | auto. B-roll clips (no speech) are
    left out of the segment text and used as overlays (media="c05" + from_frame)."""
    return "Rolle gesetzt: " + _ws.set_clip_role(clip_ids, role.strip().lower())


@tool
def list_clips() -> str:
    """Compact overview of the ingested clips and their transcript status."""
    return _ws.list_clips_text()


@tool
def get_transcript(clip_id: str, from_word: str | None = None, to_word: str | None = None) -> str:
    """Compact transcript with word IDs, fillers, pauses and repeat/restart hints.
    Optional range from_word/to_word, e.g. "w0040".."w0080"."""
    clip = _ws.clip(clip_id)
    at = _ws.analyzed(clip)
    return format_transcript(clip, at, parse_word_ref(from_word), parse_word_ref(to_word))


@tool(meta=CARD_META)
def check_setup(ctx: Context | None = None) -> CallToolResult:
    """Call FIRST on first contact and whenever the user asks to set up/install or reports a problem – e.g. "einrichten",
    "installieren", "Kannst du Schnippo einrichten?", "Richte mich ein", "funktioniert nicht", "verbindet nicht",
    "Key eintragen", "set up", "install", "not working". Check every precondition (Resolve running, Studio, version ≥ 21.1, external scripting = Local, project open,
    Gladia key valid, ffmpeg/ffprobe, cache writable, free disk space) and explain each missing one in everyday
    language. Call on first contact or when the user says "Richte mich ein". Hosts with MCP Apps show a setup assistant
    (one missing point at a time, "Erneut prüfen" jumps on)."""
    from . import setup_check
    _log_client(ctx)
    checks = setup_check.run(_cfg, _bridge, material=_ws.folder)
    if _cfg.update_check:
        from . import updates
        info = updates.check(_version(), _cfg.cache_dir / "update.json", force=True)
        if info:
            checks.append(setup_check.Check("update", "Aktuelle Version", None, updates.text(info)))
    data = {"view": "setup", **setup_check.summary(checks),
            "example": "„Schneide den Ordner …/Aufnahmen als Reel, Name: Test1.“"}
    return _card(setup_check.text(checks), data)


@mcp.resource(CARD_URI, name="schnippo_card", description=f"Karten im Chat (MCP App) von {DISPLAY_NAME}: Setup, Review, Format, Design",
              mime_type="text/html;profile=mcp-app", meta={"ui": {"prefersBorder": False}})
def card_view() -> str:
    _log.info("UI-Karte abgerufen (MCP App wird vom Host angezeigt)")
    from .design import inject_design  # design view + fonts are added to the shared card
    html = (Path(__file__).parent / "ui" / "card.html").read_text(encoding="utf-8")
    return inject_design(html.replace("{{APP_NAME}}", DISPLAY_NAME))


@tool(meta=CARD_META)
def show_review(timeline: str, decisions: list[dict], title: str | None = None, intro: str | None = None) -> CallToolResult:
    """Review card after the rough and the fine cut: the decisions the user should confirm. decisions = [{"kind":
    "grenzfall"|"verworfen"|"widerspruch"|"take"|"schnitt"|"frage"|"reihenfolge", "question": "…", "words":
    "c01:w0129-w0133" or "segment": "c01:s014" or "frame": "c07:f0040", "recommendation": "Raus"}]. The server adds the
    spoken text, position and a thumbnail (from "frame" for scenes without speech, e.g. the order proposal of a
    commercial: one decision per scene, numbered). Buttons
    Behalten / Raus / Egal; the answers come back as a chat message (and via submit_review). Without MCP Apps: ask the
    numbered questions in the chat."""
    data = _ws.review(timeline, decisions, title, intro)
    lines = [f"{data['title']} (Review {data['review_id']}):"]
    for d in data["decisions"]:
        lines.append(f"{d['id']} [{d['kind_label']}] {d['question']}" + (f" – „{d['text'][:160]}“" if d.get("text") else "")
                     + (f" – Vorschlag: {d['recommendation']}" if d.get("recommendation") else ""))
    lines.append("Antworten je Punkt: behalten / raus / egal. Mit Karte: die Auswahl kommt als Nachricht zurück.")
    return _card("\n".join(lines), data)


def _design_frame() -> str | None:
    """A real frame of the current project (middle of the main clip) as background of the design previews."""
    import base64
    import io
    try:
        from .mg.preview import video_frame
        if not _ws.clips:
            return None
        cid = _ws.master_clip(set(_ws.clips))
        clip = _ws.clips[cid]
        fps = clip.resolve_fps or clip.fps
        im = video_frame(clip, int(clip.duration_s * fps * 0.45), 540, 960)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=78)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


@tool(meta=CARD_META)
def setup_design(brand: str | None = None) -> CallToolResult:
    """Design setup for motion graphics (optional, on first use or "Design einrichten"/"Design ändern"): card with
    style (Minimal Editorial, Bold Creator, Soft Premium, Clean Tech), font (bundled OFL fonts or own file), colours with
    contrast check, radius and a final live preview over a real frame of the project; "Übernehmen" saves a brand
    profile in the user config (several brands possible). Without MCP Apps: ask these points in the chat and show
    preview_graphic sheets. If the user names a website, suggest colours/font from it yourself and pass them via
    save_brand."""
    from . import design
    from .mg import tokens as _tok
    data = design.card_data(brand, _design_frame())
    st = ", ".join(f"{s['id']} ({s['label']})" for s in data["styles"])
    text = (f"Design-Einrichtung (Marke „{data['profile_name']}“). Stile: {st}. Schriften: {', '.join(data['fonts'])} oder eigene "
            f"Datei. Farben: Akzent {data['current']['accent']}, Text {data['current']['text']}/{data['current']['text_dark']}, "
            f"Fläche {data['current']['surface']} (Kontrast ≥ {data['min_contrast']}:1). Radius: 0 / 8 / 18 / Pille. "
            f"Gespeicherte Marken: {', '.join(data['profiles']) or 'keine'} ({_tok.brand_path()}).")
    return _card(text, data)


@tool
def design_preview(profile: dict, templates: list[str] | None = None) -> CallToolResult:
    """Live preview HTML of templates (hook_text, callout, counter) with a brand profile – used by the design card."""
    from . import design
    html = design.preview_html(profile, templates or ["callout"], _ws.effective_format()[0] if _ws.clips else "reel")
    return CallToolResult(content=[TextContent(type="text", text=f"Vorschau: {', '.join(html)}")],
                          structured_content={"html": html})


@tool
def save_brand(name: str, profile: dict) -> str:
    """Save a brand profile for motion graphics in the user config (brand.json in the settings folder, never the repo) and
    make it active. profile: style (minimal|bold|soft|tech), font_family, accent, text, text_dark, surface, radius_px."""
    from . import design
    path, warn = design.save(name, profile)
    return f"Marke „{name}“ gespeichert und aktiv ({path})." + "".join(f" Hinweis: {w}" for w in warn)


@tool
def submit_review(review_id: str, answers: list[dict]) -> str:
    """Store the user's answers of a review card: answers = [{"id": "D1", "answer": "keep"|"drop"|"any"}]. Called by the
    card; Claude then adapts the cutlist of the next pass accordingly."""
    return _ws.submit_review(review_id, answers)


@tool
def resolve_status() -> str:
    """Check the connection to DaVinci Resolve (version, open project, project frame rate)."""
    try:
        s = _bridge.status()
    except Exception as e:
        return _setup_text(f"Resolve nicht erreichbar ({e}).")
    return f"{s['product']} {s['version']} | Projekt „{s['project']}“ | {s['project_fps']} fps | {s['timelines']} Timelines"


def _cutlist(cutlist: dict | str) -> Cutlist:
    data = json.loads(cutlist) if isinstance(cutlist, str) else cutlist
    try:
        return Cutlist(**data)
    except ValidationError as e:
        raise ValueError("Cutlist-Format ungültig: " + "; ".join(
            f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())) from None


@tool
def load_script(path: str | None = None) -> str:
    """Load an optional script (.docx/.txt/.md) for the current folder; headings = sections, sentences = lines L01….
    Call without path to remove the script (then the recording order is the basis)."""
    lines = _ws.load_script(path)
    if not lines:
        return "Kein Skript aktiv – Grundlage ist die Reihenfolge der Aufnahme."
    secs = len({ln.section for ln in lines})
    return f"Skript geladen: {len(lines)} Zeilen in {secs} Abschnitt(en). Erste: {lines[0].id} \"{lines[0].text}\""


@tool
def get_edit_context(clip_ids: list[str] | str = "all", include_guide: bool = True, overview: bool = False,
                     page: int | None = None, page_size: int = 40,
                     pass_name: Annotated[str, Field(alias="pass")] = "rough") -> str:
    """Everything needed for the editorial decision, compact and text-only: segments (word ranges, pauses, {?} filler
    gaps, flags), retake candidate groups, script lines and candidates, stills – plus ONLY the guide of the current
    pass (rough | fine | broll | polish; "all" = all four). Long material: overview=True first (outline, pages, groups,
    script coverage, guide), then page=1, 2, … (page_size segments per page); combine pages with merge_cutlists."""
    return _format_line() + "\n" + _ws.edit_context(clip_ids, include_guide=include_guide, page=page, page_size=page_size,
                                                     overview=overview, pass_name=None if pass_name == "all" else pass_name)


def _format_line() -> str:
    fmt, src = _ws.effective_format()
    ct, ct_src = _ws.effective_content_type()
    line = f"Format: {fmt} ({src}) · Inhalt: {ct} ({ct_src})"
    if ct == "interview":
        line += " · Interview-Regeln gelten auch im Reel: Fragen je nach Fassung raus oder kurz behalten, Vorgespräch raus, beim Sprecherwechsel an der Satzgrenze schneiden"
    if not _cfg.graphics:
        line += " · Grafiken sind aus: Durchgang 5 nur auf Wunsch"
    if src.startswith("erkannt"):
        d = _ws.detect_format()
        line += f" – {d.text()}"
        if d.ask:
            line += " – VOR dem Schnitt fragen: detect_format zeigt die Auswahl, danach set_format"
    return line


@tool
def merge_cutlists(cutlists: list[dict | str], timeline_name: str | None = None) -> str:
    """Join per-page cutlists (in the given order) into one: items, rejected and overlays are concatenated, options and
    flags come from the first. Returns the merged cutlist as JSON plus its validation."""
    from .cutlist import merge_cutlists as _merge
    merged = _merge([_cutlist(c) for c in cutlists], timeline_name)
    return merged.model_dump_json(exclude_defaults=False) + "\n\n" + _ws.validate_text(merged)


@tool
def validate_cutlist(cutlist: dict | str) -> str:
    """Dry run without Resolve: checks IDs, order and overlaps, computes every piece in source frames and the total
    duration, and shows the spoken end result with cut marks. Call this before build_timeline."""
    return _ws.validate_text(_cutlist(cutlist))


def _sound_folder() -> Path:
    if _ws.cfg.sfx_folder is None:
        raise ValueError("Kein Sound-Ordner eingestellt: sfx_folder in den Einstellungen wählen")
    from .guard import check_write_dir
    return check_write_dir(_ws.cfg.sfx_folder)


@tool
def prepare_recordings(folder: str, category: str | None = None) -> str:
    """Own recordings (docs/AUFNAHMEN.md) → sound library: light noise reduction, split into single hits (mouse: press and release together), level. The results go to
    <sfx_folder>/Aufnahmen/<category>/, the originals stay untouched. Only for the user's own recordings, never for downloaded reference sounds."""
    from .guard import real
    from .sfx_record import prepare, recordings
    src = real(folder)
    if "pixabay" in str(src).lower():
        raise ValueError("Referenzen werden nicht verarbeitet. Fertige Downloads gehören unverändert in den Sound-Ordner (sfx_folder).")
    files = recordings(src)
    if not files:
        raise ValueError(f"Keine Audiodateien in {src}")
    return "\n".join(prepare(files, _sound_folder() / "Aufnahmen", category))


@tool
def find_sfx(category: str, query: str | None = None, license: str = "cc0", limit: int = 5) -> str:
    """Searches Freesound with the user's key (license cc0, or cc-by with automatic credits) and ranks the candidates by key figures: distance 0 = in the range of the reference group.
    Costs nothing; fetch_sfx loads one. Nothing is downloaded for keeps here."""
    from .sfx_sources import freesound_search
    if not _ws.cfg.freesound_api_key:
        raise ValueError("Kein Freesound-Key: freesound.org/apiv2/apply, dann in den Einstellungen eintragen")
    rows = freesound_search(_ws.cfg.freesound_api_key, category, query, license, limit)
    return "\n".join(f"{c['id']} · {c['name']} · {c['author']} · {c['license']} · {c['duration_s']:.1f} s · Distanz {c['distance']}" for c in rows) or "Nichts gefunden"


@tool
def fetch_sfx(sound_id: int, category: str) -> str:
    """Loads one Freesound sound (MP3 preview; the original would need OAuth2) into the user's sound folder with source, author and licence. Attribution for CC-BY goes to sfx_credits.txt
    next to the export when the sound is used."""
    from .sfx_sources import freesound_fetch
    if not _ws.cfg.freesound_api_key:
        raise ValueError("Kein Freesound-Key eingetragen")
    return f"Geladen: {freesound_fetch(_ws.cfg.freesound_api_key, sound_id, category, _sound_folder())}"


@tool
def generate_sfx(text: str, category: str, seconds: float | None = None, loop: bool = False, confirm: bool = False) -> str:
    """Generates a sound effect with ElevenLabs and the user's key from a description, e.g. "soft air swoosh, 0.5 seconds". Costs credits, so without confirm=true it only says that.
    Commercial use needs a paid plan of the user. The result lands in the sound folder and shows its distance to the reference group."""
    from .sfx_sources import elevenlabs_generate, score
    if not _ws.cfg.elevenlabs_api_key:
        raise ValueError("Kein ElevenLabs-Key eingetragen")
    if not confirm:
        return "Das kostet ElevenLabs-Credits (laut Preisseite 200 je Erzeugung). Mit confirm=true starten, nachdem der Nutzer zugestimmt hat."
    f = elevenlabs_generate(_ws.cfg.elevenlabs_api_key, text, category, _sound_folder(), seconds, loop)
    return f"Erzeugt: {f} · Distanz zur Referenzgruppe {score(f, category)}"


@tool
def list_sfx() -> str:
    """Sound effects: the shipped library and the user's sfx_folder (id, category, intensity, length, transient, licence).
    Effects are set with "sfx" in the cutlist of the broll or motion pass, rules in guides/06_sound_design.md."""
    from .sfx import CATEGORIES
    ALIGN = {"start": "beginnt auf dem Ereignis", "end": "endet auf dem Ereignis", "transient": "Transient bei"}
    lib = _ws.sfx_library()
    out = [f"Modus {_ws.cfg.sfx_mode} (off | subtil | normal; je Cutlist \"sfx\": \"off\"), {len(lib)} Effekte. Eintrag: "
           "{\"category\": \"whoosh\", \"at\": \"G1\" | \"O2\" | \"c01:w0123\", \"event\": \"in\" | \"end\", \"intensity\": 1–3, \"gain_db\": -20, \"note\": …}"]
    for cat in (*CATEGORIES, None):
        rows = [e for e in lib if e["category"] == cat]
        if rows:
            out.append(cat or "ohne Kategorie (nur über file ansprechbar)")
            out += [f"  {e['id']} · Stufe {e['intensity']} · {e['duration_ms']} ms · {e.get('type', 'oneshot')} · {ALIGN.get(e.get('event_align'), 'Transient')} {e['hit_offset_ms']} ms · {e['license']}"
                    for e in rows]
    return "\n".join(out)


def _progress(ctx: Context | None, label: str, total: float | None = None):
    """Progress for long tools: MCP progress notifications (if the client sent a progress token) and the server log
    (intermediate results stay visible there). Returns report(done | message, total=None, message=None)."""
    state = {"n": 0}

    def report(done=None, total_=None, message=None):
        if isinstance(done, str):
            message, done = done, None
        state["n"] = done if done is not None else state["n"] + 1
        msg = f"{label}: {message}" if message else label
        _log.info("Fortschritt %s", msg)
        if ctx is None:
            return
        try:
            import anyio.from_thread
            anyio.from_thread.run(ctx.report_progress, float(state["n"]), total_ or total, msg)
        except Exception:  # no progress token / not in a worker thread: the log line is enough
            pass
    return report


def _channel_plans(used: set, plan) -> dict:
    """Per clip the channel plan; with one mic per speaker additionally the channel of every piece (source start frame)."""
    plans = {cid: _ws.channel_plan(_ws.clips[cid]) for cid in used}
    if any(p and p.get("by_speaker") for p in plans.values()):
        analyzed = {c: _ws.analyzed(_ws.clips[c]) for c in {pc.clip for pc in plan.pieces}}
        from .audio import louder_channels
        louder: dict = {}
        for cid, pl in plans.items():
            if pl and pl.get("by_speaker"):
                ps = [p for p in plan.pieces if p.clip == cid]
                louder.update(zip((id(p) for p in ps), louder_channels(_ws.clips[cid].path, [(p.start_s, p.end_s) for p in ps])))
        for pc, spk in zip(plan.pieces, _ws.piece_speakers(plan.pieces, analyzed)):
            pl = plans.get(pc.clip)
            if pl and pl.get("by_speaker"):
                ch = louder.get(id(pc)) or pl["by_speaker"].get(spk, pl.get("best"))
                pl.setdefault("by_start", {})[pc.start_frame] = ch
    return plans


def _hear(timeline: str):
    """Render the timeline small, return the transcribe callback for the regions that are not cached yet."""
    import subprocess
    import tempfile

    from .delivery import ensure_check_preset
    from .media import _bin, extract_audio
    from .render import render_timeline
    from .resolve_bridge import find_timeline
    from .transcribe.base import get_provider

    r, p = _bridge.resolve(), _bridge.project()
    tl = find_timeline(p, timeline)
    work = Path(tempfile.mkdtemp(prefix="sense_", dir=_ws.cache.root))
    current = p.GetCurrentTimeline()
    try:
        mov = render_timeline(p, tl, work, "sense", video=False, audio=True, preset=ensure_check_preset(r, p))
    finally:
        if current is not None:
            p.SetCurrentTimeline(current)
    wav = extract_audio(mov, work / "cut16k.wav")
    platforms.unlink(mov)

    def transcribe(wav_path, regions):
        """Cut the regions out of the wav, join them, transcribe once, map the words back to timeline seconds."""
        joined = work / "regions.wav"
        filt = "".join(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[r{k}];" for k, (a, b) in enumerate(regions))
        filt += "".join(f"[r{k}]" for k in range(len(regions))) + f"concat=n={len(regions)}:v=0:a=1[o]"
        platforms.run([_bin("ffmpeg"), "-nostdin", "-y", "-v", "error", "-i", str(wav_path), "-filter_complex", filt, "-map", "[o]",
                        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(joined)], check=True)
        raw = get_provider("gladia", _cfg).transcribe(joined, _cfg.language, raw_out=work / "raw.json")
        out, offs, acc = [], [], 0.0
        for a, b in regions:
            offs.append((acc, acc + (b - a), a))
            acc += b - a
        for t in raw.tokens:
            mid = (t.start_s + t.end_s) / 2
            for lo, hi, a in offs:
                if lo <= mid < hi:
                    out.append({"text": t.text, "s": a + t.start_s - lo, "e": a + t.end_s - lo, "c": t.confidence})
                    break
        return out
    return wav, transcribe, work


@tool
def sense_check(timeline: str, confirm: bool = False, ctx: Context | None = None) -> str:
    """Hear the finished cut again, before the export (polish): the sound of the timeline (small check render) goes to
    Gladia. 1. Seams, automatic: heard vs. expected text ±2 words around every cut; swallowed, doubled or mangled words =
    "unsaubere Naht" with time stamp. 2. Sense, your job: read the returned text like a viewer, section by section –
    broken sentences, "das"/"er" without a referent, unfinished thoughts, abrupt jumps, contradictions – and list them
    with time stamp and proposal (bring a sentence back, other take, remove a sentence). 3. Fix with revise, build, call
    sense_check on the new version: only changed pieces are transcribed again. Unclear cases: ask the user. Cost about
    0.10 USD per 10 min, shown in the receipt. export_transcript then uses the heard word times."""
    import shutil

    say = _progress(ctx, "Gegenhören")
    est = _ws.sense_estimate(timeline)
    if est["new_s"] > _cfg.transcribe_confirm_over_min * 60 and not confirm:
        return (f"Schätzung: {_mmss(est['new_s'])} min neu zu hören ≈ {est['cost_usd']:.2f} USD. Nach OK des Nutzers "
                "sense_check(confirm=true).")
    wav = work = transcribe_fn = None
    if est["regions"]:
        say(f"Prüf-Render und {_mmss(est['new_s'])} min Ton an Gladia")
        wav, transcribe_fn, work = _hear(timeline)
    try:
        res = _ws.sense_check(timeline, wav, transcribe_fn)
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)
    st = res["stats"]
    lines = [f"Gegenhören „{timeline}“: {_mmss(res['total_s'])} min, davon {_mmss(res['new_s'])} min neu transkribiert "
             f"≈ {res['cost_usd']:.3f} USD (Rest aus dem Cache, kostenlos).",
             f"Nähte: {st['cuts']} Schnitte geprüft, {len(res['seams'])} unsaubere Naht/Nähte; {st['words']} Wörter erwartet, "
             f"{st['heard']} gehört, abseits der Nähte {st['elsewhere']} Abweichungen (Erkennungsrauschen)."]
    for h in res["seams"]:
        lines.append(f"  ⚠ {ts(h['t'])} (Schnitt {ts(h['cut'])}, #{h['item'] or 0:02d}) {h['kind']}: erwartet „{h['expected']}“, "
                     f"gehört „{h['heard']}“")
    lines += ["", "Gehörter Text – lies ihn wie ein Zuschauer (Satzbrüche, Bezüge ohne Bezugswort, unvollendete Gedanken, "
              "Themensprünge, Widersprüche) und melde je Fund Zeit + Vorschlag; beheben mit revise:"] + res["sections"]
    return "\n".join(lines)


@tool
def export_final(timeline: str, preset: str = "auto", with_transcript: bool = True, ctx: Context | None = None) -> str:
    """Render the finished timeline (normally <Name>_V4_Polish or _V5_Motion) into the export folder: preset "reel"
    (1080×1920 H.264), "youtube_1080" (1920×1080 H.264), "youtube_4k" (3840×2160, only from 4K timelines) or "auto"
    (portrait → reel, landscape → YouTube 1080p). AAC 48 kHz, loudness as set in the polish pass (no extra
    normalization). Checks the file (resolution, codec, duration, LUFS/true peak) and writes SRT/TXT (+ chapters) next to
    it. No reframing here: reels from a landscape timeline go through find_reel_candidates and export_reels."""
    import json as _json
    import subprocess

    from .audio import ebur128
    from .delivery import export_final as _export
    from .media import _bin
    from .resolve_bridge import find_timeline, read_timeline
    say = _progress(ctx, "Export")
    r, p = _bridge.resolve(), _bridge.project()
    tl = find_timeline(p, timeline)
    built = _ws.built_cutlist(timeline)
    fmt = (built.format if built and built.format else None) or _ws.effective_format()[0]
    res = _export(r, p, tl, preset, _ws.export_dir(), timeline, fmt, progress=say)
    f = Path(res["file"])
    probe = _json.loads(platforms.run([_bin("ffprobe"), "-v", "error", "-show_entries",
                                        "stream=codec_type,codec_name,width,height,sample_rate:format=duration", "-of", "json",
                                        str(f)], capture_output=True, text=True).stdout or "{}")
    v = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), {})
    dur = float(probe.get("format", {}).get("duration") or 0)
    tl_s = (tl.GetEndFrame() - tl.GetStartFrame()) / float(tl.GetSetting("timelineFrameRate") or 25)
    say("Lautheit der Exportdatei messen")
    loud = ebur128(["-i", str(f)])
    prof = _ws.profile(fmt)
    ok_size = (v.get("width"), v.get("height")) == tuple(res["size"])
    ok_dur = abs(dur - tl_s) <= 0.1
    ok_l = loud.get("lufs") is not None and prof.lufs_range[0] <= loud["lufs"] <= prof.lufs_range[1]
    ok_tp = loud.get("true_peak") is not None and loud["true_peak"] <= prof.true_peak_max
    lines = [f"Export „{res['label']}“: {f}",
             f"  {'✅' if ok_size else '❌'} Bild {v.get('codec_name')} {v.get('width')}×{v.get('height')} · Ton {a.get('codec_name')} "
             f"{a.get('sample_rate')} Hz · {f.stat().st_size / 1e6:.1f} MB",
             f"  {'✅' if ok_dur else '❌'} Dauer {ts(dur)} (Timeline {ts(tl_s)})",
             f"  {'✅' if ok_l and ok_tp else '❌'} Lautheit {loud.get('lufs')} LUFS / True Peak {loud.get('true_peak')} dBTP "
             f"(Ziel {prof.target_lufs:g}, {prof.lufs_range[0]:g} bis {prof.lufs_range[1]:g}, TP ≤ {prof.true_peak_max:g})"]
    if built is None or built.audio is None and not (built.base_cutlist or "").endswith(("_V4_Polish", "_V3_BRoll")):
        lines.append("  Hinweis: Diese Timeline hat keinen Polish-Durchgang – der Ton ist nicht auf Ziel-Lautheit gebracht.")
    if res["preset"] == "youtube_4k" and built is not None and (built.punch_in or any(i.zoom for i in built.items)):
        lines.append("  Hinweis: 4K-Export mit Zooms – gezoomte Stellen sind hochskaliert und etwas weicher als in 1080p.")
    if with_transcript:
        from .export import report_text
        tr = _ws.export_transcript(timeline=read_timeline(_bridge, timeline, _ws.clips))
        lines += report_text(tr)[:4]
        gl = tr.get("glossary") or {}
        if gl.get("applied") or gl.get("unsure"):
            lines.append(f"  Glossar: {gl.get('applied', 0)} Schreibweise(n) korrigiert" + ("; unsicher: " + "; ".join(gl["unsure"]) if gl.get("unsure") else ""))
        if tr.get("heard_timing"):
            lines.append(f"  Wortzeiten aus dem Gegenhören: {tr['heard_timing']} Wörter")
    return "\n".join(lines)


@tool
def find_reel_candidates(timeline: str, count: int = 8, min_s: float = 10.0, max_s: float = 60.0) -> str:
    """Structure of a finished long version for picking reels: blocks and sentences with speaker, time, beats, section ends and simple signals (speech rate, level, numbers, lists,
    laughter, "Bezug?"). You pick connected passages and rate them by hook, standing alone, ending and value (guide "reel"), then call show_reel_candidates."""
    from .reels import candidates_text
    return candidates_text(timeline, _ws.reel_candidates(timeline, min_s, max_s), count, min_s, max_s)


@tool
def show_reel_candidates(timeline: str, candidates: list[dict]) -> list:
    """Numbered list for the user with one sheet of 9:16 stills. candidates = [{"title", "hook", "from_word": "c01:w0100", "to_word", "duration_s", "range": "2:30–3:05", "rating"}].
    The user chooses from the text; cards are not needed."""
    text, jpg = _ws.reel_preview(timeline, candidates)
    if jpg:
        d = _ws.export_dir() / "reels"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"kandidaten_{timeline}.jpg").write_bytes(jpg)
    return [text] + ([Image(data=jpg, format="jpeg")] if jpg else [])


@tool
def reel_cutlist(timeline: str, from_word: str, to_word: str, number: int = 1, title: str = "", remove: list[str] | None = None, cold_open: dict | None = None,
                 layout: str = "full", aspect: str = "1:1") -> str:
    """Cutlist of a reel from one passage of the long version, for validate_cutlist and build_timeline: format reel, 1080×1920, punch-ins, polish level, B-roll of the passage. remove: smaller
    cuts inside the passage ("c01:w0100-w0112"); cold_open: {"from_word", "to_word"} pulls the strongest sentence of the passage to the front. layout: full (fills 9:16, the standard from 4K) | framed (video as aspect 1:1 or 4:5 in the
    middle on a calm plate, never enlarged, hook_text above it); a note says when framed should be offered. Add graphics and sfx before building."""
    cl, notes = _ws.reel_cutlist(timeline, from_word, to_word, number, title, remove, cold_open, layout, aspect)
    return "\n".join([json.dumps(cl, ensure_ascii=False)] + [f"Hinweis: {n}" for n in notes])


@tool
def reel_sheet(timeline: str) -> list:
    """Contact sheet of a built reel: rendered frames at start, middle and end with the head box (yellow) and the safe zone (cyan); looks for empty edges in the real picture."""
    import shutil
    import subprocess

    from PIL import Image as PImage

    from .media import _bin
    from .reels import sheet
    from .render import render_timeline
    from .resolve_bridge import find_timeline
    p = _bridge.project()
    tl = find_timeline(p, timeline)
    total = tl.GetEndFrame() - tl.GetStartFrame()
    fps = float(tl.GetSetting("timelineFrameRate") or 25)
    marks = [(0, "Anfang"), (total // 2, "Mitte"), (max(0, total - round(fps)), "Ende")]
    info = _ws.reel_sheet_frames(timeline, [t for t, _ in marks])
    marks = sorted(marks + info["marks"])
    work = _ws.cache.root / "reel_sheet"
    work.mkdir(parents=True, exist_ok=True)
    try:
        f = render_timeline(p, tl, work, "sheet", video=True, audio=True)
        frames = []
        for t, label in marks:
            png = work / f"{t}.png"
            platforms.run([_bin("ffmpeg"), "-y", "-v", "error", "-ss", f"{t / fps:.3f}", "-i", str(f), "-frames:v", "1", str(png)], check=True)
            frames.append((t, f"{label} {ts(t / fps)}", PImage.open(png).copy()))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    jpg, notes = sheet(frames, info)
    d = _ws.export_dir() / "reels"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"blatt_{timeline}.jpg"
    out.write_bytes(jpg)
    r = info["reframe"]
    text = [f"Kontaktblatt {out}", f"Ausschnitt: {r['pieces']} Stücke, {r['splits']} Teilung(en) wegen Bewegung, sichtbar {r['visible_source_px'][0]}×{r['visible_source_px'][1]} Quellpixel, Skalierung {r['base_scale']:g}× bis {r['worst_scale']:g}×",
            "✅ Keine leeren Ränder in den geprüften Frames" if not notes else "❌ " + "; ".join(notes)]
    return ["\n".join(text), Image(data=jpg, format="jpeg")]


@tool
def export_reels(reel_timelines: list[str], captions: dict | None = None, ctx: Context | None = None) -> str:
    """Exports reels to schnippo-export/reels/: <Projekt>_Reel_01_<titel>.mp4 (1080×1920 H.264), .srt with the heard word times, and a .txt with your caption.
    captions = {timeline: {"title", "hook", "text"}}: hook line and 1–2 sentences in the tone of the video, no hashtag lists without a connection."""
    import json as _json
    import shutil
    import subprocess

    from .audio import ebur128
    from .delivery import export_final as _export
    from .media import _bin
    from .reels import slug
    from .resolve_bridge import find_timeline, read_timeline
    say = _progress(ctx, "Export")
    r, p = _bridge.resolve(), _bridge.project()
    target = _ws.export_dir() / "reels"
    target.mkdir(parents=True, exist_ok=True)
    prof = _ws.profile("reel")
    lines, overview = [], []
    for timeline in reel_timelines:
        built = _ws.built_cutlist(timeline)
        if built is None or built.reframe is None:
            raise ValueError(f"„{timeline}“ ist kein gebautes Reel")
        cap = (captions or {}).get(timeline) or {}
        title = cap.get("title") or built.reframe.title
        name = f"{timeline.split('_Reel_')[0]}_Reel_{built.reframe.number:02d}_{slug(title)}"
        say(f"Export {name}")
        tl = find_timeline(p, timeline)
        res = _export(r, p, tl, "reel", target, name, "reel", progress=say)
        f = Path(res["file"])
        probe = _json.loads(platforms.run([_bin("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration", "-of", "json", str(f)],
                                           capture_output=True, text=True).stdout or "{}")
        v = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
        dur = float(probe.get("format", {}).get("duration") or 0)
        loud = ebur128(["-i", str(f)])
        ok = (v.get("width"), v.get("height")) == (1080, 1920) and loud.get("true_peak") is not None and loud["true_peak"] <= prof.true_peak_max and loud.get("lufs") is not None and prof.lufs_range[0] <= loud["lufs"] <= prof.lufs_range[1]
        tr = _ws.export_transcript(timeline=read_timeline(_bridge, timeline, _ws.clips))
        srt = next((Path(x) for x in (tr.get("files") or []) if str(x).endswith(".srt")), None) or (Path(str(tr["srt"])) if tr.get("srt") else None)
        if srt and srt.exists():
            platforms.copy(srt, target / f"{name}.srt")
        if cap:
            (target / f"{name}.txt").write_text("\n\n".join(x for x in (cap.get("title"), cap.get("hook"), cap.get("text")) if x) + "\n", encoding="utf-8")
        row = f"{'✅' if ok else '❌'} {f.name} · {f.stat().st_size / 1e6:.1f} MB · {ts(dur)} · {v.get('width')}×{v.get('height')} {v.get('codec_name')} · {loud.get('lufs')} LUFS / {loud.get('true_peak')} dBTP"
        lines.append(row)
        overview.append(row)
    (target / "uebersicht.txt").write_text("\n".join(overview) + "\n", encoding="utf-8")
    return f"Reels in {target}:\n" + "\n".join(lines)


@tool
def resume_job(job_id: str | None = None, keep_incomplete: bool = False) -> str:
    """Continue an interrupted or failed job (crash, Resolve closed, app quit). Without job_id: lists open jobs and
    resumes the newest. Build: rebuilt from the stored cutlist (transcripts, analysis and graphic renders come from the
    cache, so only Resolve work is repeated); the half-built "<name>_unvollstaendig" timeline of that job is removed
    afterwards unless keep_incomplete. Transcription: continues with the missing clips (Gladia jobs already started are
    fetched, not paid again)."""
    open_ = _jobs.open_jobs()
    if job_id is None:
        if not open_:
            return "Kein unterbrochener oder fehlgeschlagener Auftrag."
        job = open_[0]
    else:
        job = _jobs.load(job_id)
    lines = [f"Offene Aufträge: " + ", ".join(f"{j['id']} {j['kind']} {j['label']} ({j['status']}, Stufe "
                                              f"{j['stages'][-1] if j['stages'] else '–'})" for j in open_)] if open_ else []
    if job["status"] not in ("unterbrochen", "fehlgeschlagen"):
        return "\n".join(lines + [f"Auftrag {job['id']} ist {job['status']} – nichts fortzusetzen."])
    if job.get("folder") and (not _ws.folder or str(_ws.folder) != job["folder"]):
        _ws.ingest(job["folder"])
    lines.append(f"Setze fort: {job['id']} {job['kind']} {job['label']} (war {job['status']}"
                 + (f": {job['error']}" if job.get("error") else "") + f"; erledigt: {', '.join(job['stages']) or '–'})")
    if job["kind"] == "transcribe":
        out = transcribe(**{**job["request"], "confirm": True})
        _jobs.finish(job, "fortgesetzt")
        return "\n".join(lines + [out])
    defaults = Cutlist().model_dump(mode="json", by_alias=True, exclude_none=True)
    request = {k: v for k, v in job["request"].items() if v != defaults.get(k, object())}  # only what was asked
    out = build_timeline(request)
    tmp = job["info"].get("tmp")
    if tmp and not keep_incomplete:
        from .resolve_bridge import INCOMPLETE, find_timeline
        try:
            p = _bridge.project()
            tl = find_timeline(p, tmp)
            if tl.GetName().endswith(INCOMPLETE):  # only our own, clearly marked half-built timeline
                p.GetMediaPool().DeleteTimelines([tl])
                lines.append(f"Halbe Timeline „{tmp}“ entfernt.")
        except LookupError:
            pass
    _jobs.finish(job, "fortgesetzt")
    return "\n".join(lines + [out])


@tool
def clear_cache(older_than_days: float = 30.0, include_transcripts: bool = False, include_renders: bool = False,
                confirm: bool = False) -> str:
    """Show and free cache space (only the cache folder; material and exports are never touched). Default: removes
    entries older than older_than_days that can be regenerated – check renders, single frames/motion analysis, audio
    extracts. Transcripts (cost money again) and graphic/B-roll renders (timelines using them go offline) only with
    include_transcripts / include_renders. First call lists sizes; delete with confirm=true after the user's OK."""
    from .cache_admin import clear
    return clear(_ws.cache.root, older_than_days, include_transcripts, include_renders, confirm)[0]


@tool
def locate(timeline: str, ref: str) -> str:
    """Find what the user means in a built timeline: "#05" (the numbered marker in Resolve), a timecode of the cut
    ("0:23", "1:02.5", "00:00:23:12") or a quote ("die Firma kaufen") → item number, word IDs, timeline position
    (a timecode also gives the whole sentence; a quote gives further matches). Then use the IDs in revise."""
    return _ws.locate_text(timeline, ref)


@tool
def revise(base_timeline: str, instructions: list[dict], build: bool = True) -> str:
    """Change requests on a built timeline → a NEW version "<timeline>_r2" (r3 …), never overwriting. instructions in
    order; "#NN" always means the numbering of base_timeline; ref = "#05" | timecode | quote:
    {"op": "remove", "ref": …} (quote/timecode: exactly those words/that sentence) or {"op": "remove", "words":
    "c01:w0100-w0120"}; {"op": "trim", "ref": "#05", "from_word"?: "c01:w0130", "to_word"?: …}; {"op": "move", "ref":
    "#05", "after"|"before": "#08"}; {"op": "insert", "after"|"before": "#04", "clip": "c01", "from_word": "w0100",
    "to_word": "w0120"}; {"op": "replace", "ref": "#05", "clip", "from_word", "to_word"} (other take); {"op": "zoom",
    "ref", "zoom": 1.25}; {"op": "correct", "word": "c01:w0643", "text": "Meer"}; {"op": "beat", "after": "c01:w0330", "beat":
    "key"}; {"op": "remove_overlay", "ref": "O2"}; {"op": "add_overlay", …overlay}. Shows what changed
    (new/removed/moved/changed, duration) and builds unless build=false."""
    existing = set()
    try:
        p = _bridge.project()
        existing = {p.GetTimelineByIndex(i + 1).GetName() for i in range(p.GetTimelineCount())}
    except Exception:
        pass
    new, log = _ws.revision(base_timeline, instructions, existing)
    text = "\n".join([f"Neue Version „{new.timeline_name}“ (Basis „{base_timeline}“):"] + [f"  · {x}" for x in log]
                      + [_ws.validate_text(new)])
    if not build:
        return text + "\n\nCutlist (für build_timeline):\n" + new.model_dump_json(by_alias=True, exclude_defaults=True)
    return text + "\n\n" + build_timeline(new.model_dump(mode="json", by_alias=True, exclude_none=True))


@tool
def read_timeline_changes(timeline: str, build: bool = False) -> str:
    """Manual edits in Resolve: compares the timeline (V1) with the cutlist it was built from – unchanged, trimmed,
    moved, new, removed, unknown media – and turns it into a cutlist that reproduces the edited timeline frame-exactly
    (next version "<timeline>_r2"; later passes continue from it). Nothing is dropped silently: what cannot be expressed
    (media from outside the folder, cut-off words, changed overlays) is listed under "Unklar" – ask the user.
    build=true builds the adopted version right away."""
    from .resolve_bridge import read_timeline
    res = _ws.timeline_changes(read_timeline(_bridge, timeline, _ws.clips))
    out = list(res["lines"])
    if not res["changed"]:
        out.append("Keine Handänderungen an V1.")
    if res["unclear"]:
        out.append("Unklar (bitte beim Nutzer nachfragen):")
        out += [f"  ? {u}" for u in res["unclear"]]
    new = res["cutlist"]
    if new is not None and res["changed"]:
        out.append(f"Übernommen als „{new.timeline_name}“ – gibt die Timeline {'framegenau' if res.get('reproduces') else 'NICHT ganz'} "
                   f"wieder" + ("" if res.get("plan_ok", True) else f" (Fehler: {'; '.join(res['errors'][:3])})"))
        if build and res.get("plan_ok", True):
            out.append(build_timeline(new.model_dump(mode="json", by_alias=True, exclude_none=True)))
        else:
            out.append("Cutlist (für build_timeline; erst gebaut taugt sie als base_cutlist):\n"
                       + new.model_dump_json(by_alias=True, exclude_defaults=True))
    return "\n".join(out)


@tool
def build_timeline(cutlist: dict | str, ctx: Context | None = None) -> str:
    """Build a NEW timeline in the open Resolve project from a valid cutlist (never overwrites; name conflicts get
    _v2…). The timeline always gets the frame rate of the main clip, also in projects with another rate (own
    timeline settings or FCPXML import). Verified by reading back rates, positions and durations; markers,
    2-frame audio crossfades, optional alternates timeline."""
    say = _progress(ctx, "Bauen")
    request = _cutlist(cutlist)
    job = _jobs.start("build", request.model_dump(mode="json", by_alias=True, exclude_unset=True),
                      request.timeline_name if request.name is None else f"{request.name} ({request.pass_ or '–'})",
                      str(_ws.folder) if _ws.folder else None)
    try:
        return _build_timeline(request, say, job)
    except Exception as e:
        tmp = job["info"].get("tmp")
        _jobs.finish(job, "fehlgeschlagen", f"{type(e).__name__}: {e}")
        if tmp:  # something was already built: say so in plain words, with the way out
            raise ToolError(f"Bauen abgebrochen nach Stufe „{job['stages'][-1] if job['stages'] else '–'}“: {e}\n"
                            f"Die halbe Timeline heißt „{tmp}“ (deutlich markiert, nichts wurde überschrieben). "
                            f"Weiter mit resume_job() – dann wird sie sauber neu gebaut.") from e
        raise


def _build_timeline(request, say, job) -> str:
    cl, pass_notes = _ws.prepare(request)
    plan, analyzed, segs = _ws.plan(cl)
    if not plan.ok:
        raise ValueError("Cutlist ungültig, nichts gebaut:\n" + "\n".join(plan.errors))
    g_err, _ = _ws.glossary_check(cl, plan)
    if g_err:
        raise ValueError("Nichts gebaut:\n" + "\n".join(g_err))
    say(f"Cutlist geprüft: {len(plan.pieces)} Teilstücke, {ts(plan.total_seconds(_ws.clips))}")
    rendered, mg_info = (None, None)
    if plan.graphics:
        say(f"Grafiken rendern ({len(plan.graphics)})")
        rendered, mg_info = _ws.render_graphics(cl, plan)
    plate = _ws.framed_plate(cl, plan)
    if plate:
        say("Hintergrundfläche rendern")
        rendered = [plate] + [{**g, "track": g["track"] + 1} for g in rendered or []]
    alts = _ws.alternates(cl, plan, analyzed, segs) if cl.alternates else None
    used = {pc.clip for pc in plan.pieces} | {pc.clip for pc, _ in (alts or [])}
    master = _ws.master_clip(used)
    from .resolve_bridge import tool_bin
    rc = _build(_bridge, cl, plan.pieces, _ws.clips, alts, bin_name=tool_bin(_ws.folder.name if _ws.folder else "Material"),
                master_clip=master, plan_seconds=plan.total_seconds(_ws.clips),
                work_dir=str(_ws.cache.root / "fcpxml"), overlays=plan.overlays, stills=_ws.stills,
                audio_spectrum=(_ws.audio_report(_ws.clips[master]).get("spectrum") if cl.audio else None),
                export_dir=str(_ws.export_dir()), fmt=cl.format or _ws.effective_format()[0],
                channel_plans=_channel_plans(used, plan), graphics=rendered, progress=say, sfx=_ws.sfx_cues(plan) if plan.sfx else None,
                on_stage=lambda name, info=None: _jobs.stage(job, name, info))
    t = rc["timeline"]
    _jobs.finish(job, "fertig", final=t["name"])
    _ws.remember_build(t["name"], cl, graphics=[{k: g.get(k) for k in ("index", "template", "track", "tl_start", "frames", "stage",
                                                                       "bbox", "min_gap", "clearance", "safe_ok", "safe", "padding")}
                                                 for g in t.get("graphics", []) if g.get("index")])

    def rb_line(rb: dict) -> str:
        clipf = ", ".join(f"{c} {v}" for c, v in rb.get("clip_fps", {}).items())
        g = lambda v: "nicht gemeldet" if v is None else f"{v:g}"
        return (f"  zurückgelesen: Projekt {g(rb['project_fps'])} fps / Wiedergabe {g(rb['project_playback_fps'])} · "
                f"Timeline {g(rb.get('timeline_fps'))} / Wiedergabe {g(rb.get('timeline_playback_fps'))} · "
                f"eigene Timeline-Einstellungen: {rb.get('timeline_custom_settings') or 'nein'} · Clip-FPS {clipf}")

    lines = [f"Durchgang: {cl.pass_ or '–'}" + (f" (Basis {cl.base_cutlist})" if cl.base_cutlist else "")]
    lines += [f"Hinweis {n}" for n in pass_notes]
    lines += [f"Projekt „{rc['project']}“ · Framerate {rc['fps']:g} fps aus Hauptmaterial {rc['master_clip']}",
             f"Timeline „{t['name']}“: {t['pieces']} Teilstücke, {ts(t['seconds'])} ({t['frames']} Frames; "
             f"validate_cutlist: {ts(t['expected_seconds'])}), verifiziert: {'JA' if t['verified'] else 'NEIN'}, "
             f"Marker: {t['markers']}, Audio-Überblendungen: {t['crossfades']}/{t['cuts']}, Punch-ins: {t.get('punch_ins', 0)}",
             f"  Weg: {t['way']}" + (f" (vorher versucht: {'; '.join(t['attempts'])})" if t["attempts"] else ""),
             rb_line(t["readback"])]
    ch = t.get("audio_channels") or {}
    for cid, pl in (ch.get("plans") or {}).items():
        lines.append(f"  Tonkanäle {cid}: {pl['class']} – {pl['reason']}")
    if ch.get("tracks_before") is not None:
        lines.append(f"  Tonspuren: {ch.get('tracks_before')} → {ch.get('tracks_after')}"
                     + (f", {ch['mapped']} Clips auf einen Kanal mittig (dual mono)" if ch.get("mapped") else "")
                     + (" – je Sprecher: " + ", ".join(f"Kanal {k}: {n} Clips" for k, n in sorted(ch["per_channel"].items()))
                        if ch.get("per_channel") else ""))
    lines += [f"  FEHLER {e}" for e in t["errors"]]
    for o in t.get("overlays", []):
        if o.get("index"):
            lines.append(f"  Overlay O{o['index']} {o['media']} V{o.get('track')} ab Frame {o.get('tl_start')} · {o.get('frames')} F · "
                         f"{o.get('way')} · verifiziert: {'JA' if o['verified'] else 'NEIN'}")
    for g in t.get("graphics", []):
        if g.get("index"):
            how = "Cache" if g.get("cached") else f"Render {g.get('render_s')} s + Encode {g.get('encode_s')} s"
            lines.append(f"  Grafik G{g['index']} {g.get('template')} V{g.get('track')} ab Frame {g.get('tl_start')} · {g.get('frames')} F · "
                         f"{g.get('side')} · Abstand Kopf {g.get('min_gap')} px (≥ {g.get('clearance')}) · sichere Zone "
                         f"{'OK' if g.get('safe_ok') else 'NEIN'} · ProRes 4444 ({how}) · Alpha {g.get('alpha')} · "
                         f"verifiziert: {'JA' if g['verified'] else 'NEIN'}")
    for c in t.get("sfx", []):
        lines.append(f"  Effekt S{c['index']} {c['id']} auf {c['at']} ({c['what']}): Spur A{c.get('track')}, ab Frame {c['tl_start']}, Transient bei "
                     f"Frame {c['event_frame']}, {c['gain_db']:+g} dB zur Stimme (Clip {c['volume_db']:+.1f} dB) · "
                     f"verifiziert: {'JA' if c['verified'] else 'NEIN'}")
    if mg_info and mg_info.get("skipped"):
        lines += [f"  Grafik NICHT GESETZT: {x}" for x in mg_info["skipped"]]
    if mg_info:
        lines.append(f"  Motion Graphics: Marke „{mg_info['brand']}“, {mg_info['w']}×{mg_info['h']} @ {mg_info['fps']:g} fps"
                     + (f"; einmalig installiert ({mg_info['setup_s']} s): {', '.join(mg_info['installed'])}" if mg_info["installed"] else ""))
    if t.get("audio"):
        au = t["audio"]
        b, a_ = au["before"], au["after"]
        lines.append(f"  Audio: vorher {b.get('lufs')} LUFS / {b.get('true_peak')} dBTP → nachher {a_.get('lufs')} LUFS / "
                     f"{a_.get('true_peak')} dBTP (Render-Messung, {au['iterations']} Durchgang/Durchgänge, Kette: "
                     f"{' → '.join(au.get('chain') or []) or '–'}); Lautheit {'OK' if au['lufs_ok'] else 'NICHT ERREICHT'}, "
                     f"True Peak {'OK' if au['tp_ok'] else 'ÜBER ZIEL'}")
        lines += [f"    – {x}" for x in au["actions"]] + [f"    Hinweis: {x}" for x in au["notes"]]
        if au.get("balance") and au["balance"].get("rms_db"):
            bl = au["balance"]
            lines.append(f"    Ausgang L/R: {' / '.join(f'{v:g}' for v in bl['rms_db'])} dB RMS"
                         + (f" (Unterschied {bl['diff_db']:g} dB {'✓' if bl['diff_db'] <= 0.5 else '⚠'})" if bl.get("diff_db") is not None else ""))
        if au.get("delivery_preset"):
            lines.append(f"    Export: Deliver-Tab → „Add to Render Queue“ → „Render All“ (Ziel {_ws.export_dir()})")
    if "alternates" in rc:
        a = rc["alternates"]
        lines.append(f"Alternativen „{a['name']}“: {a['pieces']} Teilstücke, {ts(a['seconds'])}, verifiziert: "
                     f"{'JA' if a['verified'] else 'NEIN'}, Marker: {a['markers']}, Weg: {a['way']}")
        lines += [f"  FEHLER {e}" for e in a["errors"]]
    lines += [f"Hinweis: {n}" for n in rc["notes"]]
    return "\n".join(lines)


@tool
def run_qc(timeline: str | None = None, audio: bool = False) -> str:
    """Automated quality control of a Resolve timeline (guides/04_polish.md): flash frames (< 3 frames), gaps in picture
    and sound, cut-off words, zoom on every cut, frame rate, duration vs. its cutlist, A/V sync, watermark hints in the
    metadata; audio=True also renders and measures loudness/true peak (~20 s). timeline: name (default: current)."""
    from .resolve_bridge import measure_timeline_audio, read_timeline
    data = read_timeline(_bridge, timeline, _ws.clips)
    au = measure_timeline_audio(_bridge, data["name"], _ws.cache.root / "qc") if audio else None
    res = _ws.qc(data, au)
    c = res["counts"]
    head = (f"QC „{data['name']}“ ({len(data['v1'])} Stücke, Durchgang {res['pass'] or '–'}): "
            + ("BESTANDEN" if res["ok"] else "FEHLER GEFUNDEN") + f" – {c['fehler']} Fehler, {c['hinweise']} Hinweise")
    return "\n".join([head] + res["lines"])


@tool
def export_transcript(cutlist: dict | str | None = None, timeline: str | None = None, chapters: list[dict] | None = None,
                      max_words: int | None = None, max_line_chars: int | None = None) -> str:
    """Export the transcript of the FINISHED cut (word timestamps mapped to timeline time, corrections applied):
    .srt (block size from the format: reel ≤ 4 words word-by-word, youtube/course 2 lines × 42 characters ≥ 1 s;
    max_words/max_line_chars override; breaks at punctuation/pauses) and .txt (running text with paragraphs) into
    <material folder>/schnippo-export/. Give either a cutlist or the name of a Resolve timeline (reads the timeline
    back, so manual changes in Resolve count). Profile youtube (or chapters=[{"word": "c01:w0120", "title": "…"}]):
    also <name>_kapitel.txt (first chapter at 0:00, ≥ 3 chapters, each ≥ 10 s)."""
    from .export import Chapter, report_text
    from .resolve_bridge import read_timeline
    chs = [Chapter(**c) for c in chapters] if chapters else None
    if cutlist is not None:
        res = _ws.export_transcript(cl=_cutlist(cutlist), chapters=chs, max_words=max_words, max_line_chars=max_line_chars)
    else:
        res = _ws.export_transcript(timeline=read_timeline(_bridge, timeline, _ws.clips), chapters=chs, max_words=max_words,
                                    max_line_chars=max_line_chars)
    return "\n".join(report_text(res))


@tool
def preview_graphic(cutlist: dict | str, index: int | None = None, debug: bool = True) -> list:
    """Motion graphics (pass 5): contact sheet BEFORE rendering – 6 stills per graphic (in, standing, middle, out) over the
    real video frame at the planned position (punch-in included) + placement: above the head → beside → below the chin →
    not placed, with ≥ head_clearance_px to the head box of every frame of the span; debug=True draws head box, graphic box,
    clearance and safe zone. The text has the smallest clearance in px and the stage used.
    Look at it before build_timeline. First use installs Playwright + Chromium once (progress in the log)."""
    text, jpgs = _ws.preview_graphics(_cutlist(cutlist), index, debug)
    return [text] + [Image(data=j, format="jpeg") for j in jpgs]


@tool
def motion_setup() -> str:
    """Install the motion-graphics renderer now (Playwright + Chromium headless shell, once, ~1 min) instead of on first
    use; reports sizes and duration. Templates: hook_text, callout, counter, list_steps, lower_third, underline_arrow."""
    from .mg.render import ensure, status
    info = ensure(_ws.cache.root)
    st = status(_ws.cache.root)
    from .mg.templates import PARAMS, TEMPLATES
    lines = [("Installiert (" + f"{info['seconds']} s): " + ", ".join(info["installed"])) if info["installed"] else "Bereits installiert.",
             f"Renderer bereit: Paket {'✓' if st['package'] else '✗'}, Chromium {'✓' if st['browser'] else '✗'}", "Templates:"]
    lines += [f"  {k}: {v} – Parameter {PARAMS[k]}" for k, v in TEMPLATES.items()]
    return "\n".join(lines)


@tool
def get_frames(target: str, mode: str = "segment_strip", interval_s: float = 2.0, max_images: int = 1, page: int = 1,
               pad_s: float = 0.0) -> list:
    """Contact sheets (JPEG, ≤1024 px, burned-in frame IDs like c01:f0123 + time) – only when visual information is
    needed (close take decisions, B-roll). target: c01 | c01:s003-s007 | c01:w0010-w0050 | stills | i01,i03 |
    broll (scene frames of every B-roll clip, to pick from_frame) | clips (one middle frame per clip, to group scenes and
    propose an order). mode: segment_strip (start/middle/end per segment) | interval (every interval_s) | scenes | stills.
    pad_s widens interval/scenes before and after the target (e.g. frames before the first word to pick start_frame).
    Reference frames only by their IDs."""
    text, jpgs = _ws.get_frames(target, mode=mode, interval_s=interval_s, max_images=max(1, max_images), page=page, pad_s=pad_s)
    return [text] + [Image(data=j, format="jpeg") for j in jpgs]


@tool
def get_take_frames(group: str, max_images: int = 1, page: int = 1) -> list:
    """Visual comparison of the attempts of a retake group (e.g. "c01:G03" from get_edit_context, or
    "c01:s022,s026,s028"): one row per attempt with start/middle/end frames. Use only for close decisions."""
    text, jpgs = _ws.take_frames(group, max_images=max(1, max_images), page=page)
    return [text] + [Image(data=j, format="jpeg") for j in jpgs]


@tool
def set_word_text(word: str, text: str | None = None) -> str:
    """Correct the text of one word (recognition error, e.g. c01:w0113 → "dranbleiben."); the word ID stays the same.
    Used for export_transcript and the spoken end text. Without text the correction is removed. Do not rephrase."""
    return _ws.set_word_text(word, text)


@tool
def suggest_corrections(clip_id: str) -> str:
    """Correction proposals for a clip: spots that look like a glossary term but are spelled differently (glossar.txt /
    set_glossary), and with a loaded script where the transcript differs 1:1 from the matched line. Apply with set_word_text."""
    return _ws.suggestions_text(clip_id)


@tool
def set_glossary(terms: list[str]) -> str:
    """Project glossary: names of people, companies, brands, places, technical terms, e-mail and web addresses in correct
    spelling, e.g. ["MOC AG = Moz AG, CU", "support@mondoria.de"] (after = known mis-hearings). Adds to glossar.txt in the
    material folder. Ask for them at the start of a job when the recognition varies – do not guess. Used as Gladia vocabulary for
    NEW transcriptions (existing word IDs stay), for correction proposals, the subtitle export and to release lower thirds."""
    return _ws.set_glossary(terms)


@tool
def analyze_audio(clip_ids: list[str] | str = "all", target_lufs: float = -14.0) -> str:
    """Measure loudness (LUFS, true peak, LRA), noise floor and the speech spectrum (rumble, boxy, sibilance vs a neutral
    speech reference) and recommend measures. Apply them with the cutlist section "audio" in build_timeline."""
    return _ws.audio_text(clip_ids, target_lufs)


@tool
def preview_cuts(cutlist: dict | str, top_n: int = 8, max_images: int = 1, page: int = 1) -> list:
    """Contact sheet with 'last frame before | first frame after' for the most conspicuous cuts (image difference +
    motion), to spot hard jumps, half gestures, blinks, looking away. top_n=0 → all cuts."""
    text, jpgs = _ws.preview_cuts(_ws.prepare(_cutlist(cutlist))[0], max_images=max(1, max_images), top_n=top_n, page=page)
    return [text] + [Image(data=j, format="jpeg") for j in jpgs]


@mcp.prompt(name="einrichten", title="Einrichten", description=f"{DISPLAY_NAME} einrichten und prüfen (Resolve, Gladia-Key, ffmpeg)")
def einrichten_prompt() -> str:
    return (f"Richte {DISPLAY_NAME} für mich ein: Rufe check_setup auf und führe mich Punkt für Punkt durch alles, was noch "
            "fehlt (kurze Anleitung in Alltagssprache). Wenn alles bereit ist, sag mir in einem Satz, wie ich den ersten "
            "Schnitt starte.")


@mcp.prompt(name="onboarding", title="Onboarding", description=f"{DISPLAY_NAME} kennenlernen und einrichten, 2–3 Minuten")
def onboarding_prompt() -> str:
    return "Führe mich kurz durch das Onboarding: Rufe onboarding(step=\"willkommen\") auf und folge den Hinweisen darin."


@mcp.prompt(name="hilfe", title="Hilfe", description="Spickzettel: So sprichst du mit dem Tool, so legst du ein Projekt an")
def hilfe_prompt() -> str:
    return "Zeige mir diesen Spickzettel kurz und sage nichts weiter dazu:\n\n" + _onb.cheat_sheet(_cfg.projects_folder)


@mcp.prompt(name="rohschnitt", title="Rohschnitt starten",
            description="Video in vier Durchgängen schneiden (Rough → Fine → B-Roll → Polish → Export, optional Motion Graphics)")
def rohschnitt_prompt(folder: str = "", name: str = "") -> str:
    from .guides import guide as _guide
    from .profiles import profile_text
    head = f"Schneide das Material aus dem Ordner {folder or '(bitte nachfragen)'}"
    head += f" unter dem Namen „{name}“." if name else ". Frage nach einem kurzen Projektnamen für die Timelines."
    return "\n\n".join([head, f"Profil: {profile_text(_ws.profile())}", WORKFLOW,
                         "Leitfaden für den ersten Durchgang (die weiteren liefert get_edit_context(pass=…)):",
                         _guide(_cfg.guides_dir, "rough")])


@mcp.resource("schnippo://guides/{name}", name="guide", description="Schnitt-Leitfaden: rough | fine | broll | polish | technik",
              mime_type="text/markdown")
def guide_resource(name: str) -> str:
    from .guides import FILES
    f = _cfg.guides_dir / (FILES.get(name) or f"{name}.md")
    if name not in FILES and name != "technik" or not f.exists():
        raise ValueError(f"unbekannter Leitfaden {name!r} (rough | fine | broll | polish | technik)")
    return f.read_text(encoding="utf-8")


def main() -> None:
    if platforms.is_windows() and hasattr(sys.stderr, "reconfigure"):  # the log, with umlauts; stdout belongs to the MCP protocol and the SDK writes UTF-8 there itself
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    # diagnostics for the Claude log (never the key): does a restart after changing the extension settings deliver it?
    logging.getLogger("schnippo").info(
        "Start %s · Gladia-Key: %s · Format: %s · Python %s", _version(),
        f"vorhanden ({_cfg.gladia_key_source})" if _cfg.gladia_api_key else "fehlt", _cfg.format, sys.version.split()[0])
    mcp.run("stdio")


if __name__ == "__main__":
    main()
