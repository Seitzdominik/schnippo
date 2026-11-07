"""Errors in everyday language: what happened, in one sentence, and the next step. Technical detail stays short at
the end (for support), never a traceback."""

from __future__ import annotations

import errno
import re


def _short(e: BaseException, n: int = 160) -> str:
    t = str(e).strip().replace("\n", " ")
    return (t[:n] + "…") if len(t) > n else t


def plain(e: BaseException) -> str | None:
    """Plain-language text for known failure kinds; None = keep the tool's own (already readable) message."""
    from .delivery import PresetError
    from .media import MediaError
    from .render import RenderError
    from .transcribe.base import TranscriptionError

    if isinstance(e, OSError) and e.errno == errno.ENOSPC:
        return ("Kein Speicherplatz mehr frei. Nächster Schritt: Platz schaffen – clear_cache() zeigt, was der Cache "
                "belegt – und dann erneut versuchen; Fertiges bleibt erhalten (resume_job).")
    if isinstance(e, PermissionError) or (isinstance(e, OSError) and e.errno in (errno.EACCES, errno.EPERM)):
        where = getattr(e, "filename", None)
        return (f"Kein Zugriff auf {where or 'eine Datei'}. Nächster Schritt: macOS → Systemeinstellungen → Datenschutz & "
                "Sicherheit → Festplattenvollzugriff (oder „Dateien und Ordner“) für Claude erlauben, oder das Material an "
                "einen Ort ohne Sperre legen.")
    if isinstance(e, TranscriptionError):
        t = str(e)
        if "nicht erreichbar" in t:
            return ("Keine Verbindung zu Gladia. Nächster Schritt: Internetverbindung prüfen und transcribe erneut "
                    "aufrufen – fertige Clips sind gespeichert und kosten nichts mehr.")
        m = re.search(r"HTTP (\d{3})", t)
        code = int(m.group(1)) if m else None
        if code in (401, 403):
            return ("Gladia lehnt den API-Key ab. Nächster Schritt: Key in den Einstellungen der Erweiterung prüfen und "
                    "SPEICHERN (app.gladia.io → API Keys), dann check_setup.")
        if code in (402,):
            return "Das Gladia-Guthaben ist aufgebraucht. Nächster Schritt: unter app.gladia.io aufladen, dann erneut."
        if code == 429:
            return ("Gladia meldet zu viele Anfragen auf einmal. Nächster Schritt: eine Minute warten und transcribe "
                    "erneut aufrufen – fertige Clips bleiben gespeichert.")
        if code and code >= 500:
            return (f"Gladia hat gerade eine Störung (HTTP {code}). Nächster Schritt: in ein paar Minuten erneut versuchen "
                    "(resume_job) – es wurde nichts doppelt abgerechnet.")
        if "serverseitig weiter" in t:
            return ("Gladia ist noch nicht fertig. Nächster Schritt: später resume_job() aufrufen – der laufende Auftrag wird "
                    "abgeholt, nicht neu bezahlt.")
        return None
    if isinstance(e, RenderError):
        return ("Resolve hat einen Prüf-Render nicht ausgeführt. Nächster Schritt: in Resolve offene Dialoge schließen, auf "
                f"der Deliver-Seite die Render-Warteschlange leeren, dann resume_job(). ({_short(e)})")
    if isinstance(e, PresetError):
        return ("Die Export-Voreinstellung ließ sich in Resolve nicht anlegen. Nächster Schritt: Resolve einmal neu starten "
                f"und erneut bauen (resume_job). ({_short(e)})")
    if isinstance(e, MediaError):
        return ("Eine Datei lässt sich nicht lesen (beschädigt, unvollständig kopiert oder kein Video). Nächster Schritt: "
                f"die Datei in QuickTime öffnen; geht das nicht, aus dem Ordner nehmen und erneut einlesen. ({_short(e)})")
    if isinstance(e, TimeoutError):
        return f"Ein Schritt hat zu lange gedauert. Nächster Schritt: resume_job() – Fertiges wird übernommen. ({_short(e)})"
    return None
