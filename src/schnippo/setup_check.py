"""check_setup: every precondition with a short fix in everyday language. Used by the tool, the setup card (MCP App)
and by other tools when Resolve is not reachable (they return this instead of a technical error)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass

from . import platforms
from .branding import DISPLAY_NAME, SUPPORT_URL
from pathlib import Path

MIN_VERSION = (21, 1)
FREE_WARN_GB, FREE_FAIL_GB = 10.0, 2.0
RESTART = "dann Resolve einmal neu starten"
RESTART_CLAUDE = ("Falls du den Key gerade eingetragen hast: Claude vollständig beenden und neu öffnen. Mac: oben in der "
                  "Menüleiste auf das Claude-Symbol klicken (Rechtsklick) → Beenden. Windows: unten rechts im Infobereich "
                  "(System Tray) auf das Claude-Symbol klicken → Beenden. Danach Claude neu starten und „Erneut prüfen“.")
KEY_MISSING = ("Den Gladia-API-Key in den Einstellungen der Erweiterung eintragen und SPEICHERN (Claude → Einstellungen → "
               "Erweiterungen → " + DISPLAY_NAME + " → Konfigurieren). Key gibt es unter app.gladia.io → API Keys. "
               "Ohne Speichern kommt der Key nicht an – ein Neustart allein hilft nicht. "
               "Gibt es keine Einstellungen (Plugin, andere Programme): store_api_key öffnet ein Fenster und legt den Key sicher im System ab (Schlüsselbund bzw. Anmeldeinformationsverwaltung).")


@dataclass
class Check:
    id: str
    label: str
    ok: bool | None  # True ✅, False ❌, None = not checked (depends on an earlier ❌) / only a hint
    detail: str = ""
    fix: str = ""

    def icon(self) -> str:
        return "✅" if self.ok else ("❌" if self.ok is False else "⚪")


def _resolve_running() -> bool:
    return platforms.resolve_running()


def _gladia(key: str | None, timeout: float = 8.0) -> tuple[bool | None, str]:
    """Cheapest possible validity check: list one pre-recorded job (no upload, no transcription, not billed)."""
    if not key:
        return False, "kein Key eingetragen"
    import httpx
    try:
        r = httpx.get("https://api.gladia.io/v2/pre-recorded", params={"limit": 1}, headers={"x-gladia-key": key},
                      timeout=timeout)
    except httpx.HTTPError as e:
        return None, f"Gladia nicht erreichbar ({type(e).__name__}) – Internetverbindung?"
    if r.status_code == 200:
        return True, "Key gültig"
    if r.status_code in (401, 403):
        return False, "Key abgelehnt"
    return None, f"Gladia antwortet mit Status {r.status_code}"


def run(cfg, bridge=None, gladia=None, running=None, which=None, material: Path | None = None) -> list[Check]:
    from . import media
    from .resolve_bridge import LIB, MODULES

    gladia = gladia or _gladia
    running = running or _resolve_running
    which = which or media.find_tool
    out: list[Check] = []
    installed = Path(LIB).exists() and Path(MODULES).exists()
    out.append(Check("installed", "DaVinci Resolve installiert", installed,
                     "Scripting-Modul gefunden" if installed else f"nicht gefunden unter {LIB}",
                     "" if installed else "DaVinci Resolve Studio 21.1 oder neuer installieren (blackmagicdesign.com)."))
    is_running = installed and running()
    out.append(Check("running", "Resolve läuft", is_running if installed else None,
                     "" if is_running else "Resolve ist nicht geöffnet",
                     "" if is_running else "DaVinci Resolve öffnen und ein Projekt laden, dann „Erneut prüfen“."))
    r = None
    if is_running and bridge is not None:
        try:
            r = bridge.resolve()
        except Exception:
            r = None
    if is_running:
        out.append(Check("scripting", "Verbindung zu Resolve (External scripting = Local)", r is not None,
                         "verbunden" if r is not None else "Resolve läuft, lässt aber keine Verbindung zu",
                         "" if r is not None else f"{platforms.resolve_scripting_steps()}, {RESTART}."))
    else:
        out.append(Check("scripting", "Verbindung zu Resolve (External scripting = Local)", None,
                         "wird geprüft, sobald Resolve läuft"))
    if r is not None:
        product = r.GetProductName() or ""
        studio = "Studio" in product
        out.append(Check("studio", "Resolve Studio (nicht die kostenlose Version)", studio, product,
                         "" if studio else "Die kostenlose Version erlaubt keine externe Steuerung. DaVinci Resolve Studio "
                         "installieren und aktivieren."))
        ver = tuple(int(x) for x in (r.GetVersion() or [0, 0])[:2] if isinstance(x, int) or str(x).isdigit())
        ok_v = ver >= MIN_VERSION
        out.append(Check("version", f"Version ≥ {MIN_VERSION[0]}.{MIN_VERSION[1]}", ok_v, r.GetVersionString() or "",
                         "" if ok_v else "Resolve aktualisieren: DaVinci Resolve → Nach Updates suchen."))
        p = r.GetProjectManager().GetCurrentProject()
        name = p.GetName() if p else None
        out.append(Check("project", "Projekt geöffnet", bool(p),
                         f"„{name}“" + (" (unbenanntes Projekt – besser ein eigenes anlegen)" if name == "Untitled Project" else "")
                         if p else "kein Projekt offen",
                         "" if p else "In Resolve ein Projekt öffnen oder neu anlegen (Projektmanager)."))
    else:
        for cid, label in (("studio", "Resolve Studio (nicht die kostenlose Version)"),
                           ("version", f"Version ≥ {MIN_VERSION[0]}.{MIN_VERSION[1]}"), ("project", "Projekt geöffnet")):
            out.append(Check(cid, label, None, "wird geprüft, sobald die Verbindung steht"))
    ok_k, detail = gladia(cfg.gladia_api_key)
    src = getattr(cfg, "gladia_key_source", None)
    if cfg.gladia_api_key and src:
        detail += f" · gelesen aus: {src}"
    if not cfg.gladia_api_key:
        fix = KEY_MISSING
    elif ok_k is False:
        fix = ("Der Key wird von Gladia abgelehnt: in den Einstellungen der Erweiterung prüfen bzw. neu eintragen "
               "(app.gladia.io → API Keys). " + RESTART_CLAUDE)
    else:
        fix = "Internetverbindung prüfen, dann erneut prüfen."
    out.append(Check("gladia", "Gladia-Key gültig", ok_k, detail, "" if ok_k else fix))
    for problem in getattr(cfg, "setting_problems", []):
        out.append(Check("settings", "Einstellung prüfen", False, problem, "In den Einstellungen der Erweiterung korrigieren und Claude neu starten."))
    if platforms.is_windows():
        import struct
        bits = struct.calcsize("P") * 8
        out.append(Check("python", "Python für fusionscript.dll", bits == 64, f"Python {sys.version_info.major}.{sys.version_info.minor}, {bits} bit",
                         "" if bits == 64 else "Resolve braucht ein 64-bit-Python. uv installiert es automatisch, die Erweiterung neu installieren."))
    for tool in ("ffmpeg", "ffprobe"):
        path, source = which(tool)
        out.append(Check(tool, f"{tool} gefunden", bool(path), f"{source}: {path}" if path else "nicht gefunden",
                         "" if path else platforms.install_ffmpeg_hint()))
    cache = Path(cfg.cache_dir)
    try:
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=cache, prefix=".write_test_", delete=True):
            pass
        out.append(Check("cache", "Cache-Ordner beschreibbar", True, str(cache)))
    except OSError as e:
        out.append(Check("cache", "Cache-Ordner beschreibbar", False, f"{cache}: {e.strerror}",
                         "Speicherort prüfen (externe Platte angeschlossen? Schreibrechte?)."))
    targets = {"Cache": cache}
    if material:
        targets["Material"] = Path(material)
    for label, path in targets.items():
        try:
            free = shutil.disk_usage(path if path.exists() else path.parent).free / 1e9
        except OSError:
            continue
        ok = free >= FREE_WARN_GB
        out.append(Check(f"disk_{label.lower()}", f"Freier Speicher ({label})", True if ok else (None if free >= FREE_FAIL_GB else False),
                         f"{free:.0f} GB frei auf {_volume(path)}",
                         "" if ok else f"Platz schaffen: Prüf-Renders und Frames liegen im Cache ({cfg.cache_dir}), "
                         "sie dürfen gelöscht werden."))
    return out


def _volume(p: Path) -> str:
    resolved = Path(p).resolve()
    if platforms.is_windows():
        return f"Laufwerk {resolved.anchor}"
    parts = resolved.parts
    return f"/Volumes/{parts[2]}" if len(parts) > 2 and parts[1] == "Volumes" else "dem Startvolume"


def summary(checks: list[Check]) -> dict:
    bad = [c for c in checks if c.ok is False]
    return {"ready": not bad and all(c.ok is not None for c in checks if c.id in ("running", "scripting", "studio",
                                                                                   "version", "project", "gladia")),
            "failed": len(bad), "checks": [asdict(c) | {"icon": c.icon()} for c in checks]}


def text(checks: list[Check]) -> str:
    s = summary(checks)
    head = "Einrichtung: alles bereit ✅" if s["ready"] else f"Einrichtung: {s['failed']} Punkt(e) offen"
    lines = [head]
    for c in checks:
        lines.append(f"{c.icon()} {c.label}" + (f" – {c.detail}" if c.detail else ""))
        if c.fix and c.ok is not True:
            lines.append(f"    → {c.fix}")
    if not s["ready"]:
        lines.append(f"Hilfe: {SUPPORT_URL}")
    return "\n".join(lines)


def env_hint() -> dict:  # for debugging in the card (no secrets)
    return {"python": os.sys.version.split()[0], "bundle": bool(os.environ.get("SCHNIPPO_BUNDLE"))}
