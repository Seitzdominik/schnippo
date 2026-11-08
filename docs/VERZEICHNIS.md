# Anthropic-Verzeichnis: Stand und Checkliste

Schnippo geht als **Plugin** ins Verzeichnis, nicht als `.mcpb`. Der Ordner [`plugin/`](../plugin/) wird von `tools/build_plugin.py` erzeugt. **Noch nicht eingereicht.**

## Pre-Submission-Checklist

| Punkt | Stand | Beleg |
|---|---|---|
| `.claude-plugin/plugin.json`, Server-Eintrag, README, LICENSE | ✅ | `plugin/` |
| Server startet lokal über Launcher, Version exakt angeheftet | ✅ | `.mcp.json`: `uvx schnippo@<version>`, setzt die PyPI-Veröffentlichung voraus |
| Jedes Tool mit `title` | ✅ | `src/schnippo/toolinfo.py`, Test bricht bei fehlendem Eintrag |
| `readOnlyHint` bzw. `destructiveHint` je Tool | ✅ | Timelines bauen und Dateien schreiben sind nicht read-only, Löschungen nur mit Bestätigung |
| Tool-Namen höchstens 64 Zeichen | ✅ | Test |
| Datenschutz in der README als „Privacy Policy“ | ✅ | README, `plugin/README.md` |
| Datenschutz als HTTPS-URL | ✅ | https://schnippo.com/en/privacy/ und https://schnippo.com/datenschutz/ |
| Inhalt: Erhebung, Nutzung und Speicherung, Dritte, Aufbewahrung, Kontakt | ✅ | `docs/PRIVACY.md` |
| Setup- und Nutzungsdoku | ✅ | README, `docs/REFERENZ.md` |
| `claude plugin validate ./plugin` ohne Befunde | ✅ | siehe unten |
| Netzwerkziele vollständig dokumentiert | ✅ | Tabelle unten |
| `privacy_policies` im `.mcpb`-Manifest | ✅ | `packaging/manifest.template.json` |

## Netzwerkziele für den Security-Scan

| Ziel | Zweck | Auslöser | Daten |
|---|---|---|---|
| `api.gladia.io` | Transkription | `transcribe`, Key-Prüfung in `check_setup` | Tonspur, Glossar |
| `api.github.com` | Update-Hinweis | `check_setup`, täglich beim ersten Tool-Aufruf, abschaltbar | keine |
| `freesound.org` | Sound-Suche | `find_sfx`, `fetch_sfx`, eigener Key | Suchbegriff |
| `api.elevenlabs.io` | Sound-Erzeugung | nur auf Wunsch, eigener Key | Beschreibung |
| `pypi.org`, `files.pythonhosted.org` | Abhängigkeiten | Installation, erstes Einlesen (ffmpeg, Bildanalyse), `motion_setup` | keine |
| `github.com` | Python-Laufzeit über uv, Download-Links | Installation | keine |
| Playwright-CDN | Chromium für Grafiken | `motion_setup` | keine |

Das Rendern von Grafiken läuft ohne Netzwerkzugriff. Lokal spricht Schnippo mit DaVinci Resolve über dessen Scripting-Schnittstelle. Es startet als Unterprozesse `ffmpeg`, `ffprobe`, sowie für das Eingabefenster von Keys `osascript` (Mac) bzw. `powershell` (Windows). Keys speichert `keyring` im System. Telemetrie gibt es nicht.

## Key und Einstellungen im Plugin

Das Plugin fragt den Gladia-Key über `userConfig` (`sensitive`) ab. Ob Claude Desktop das bei diesem Plugin unterstützt, ist nicht getestet: Die Meldung „user_config_unsupported“ steht in keiner Dokumentation, die ich gefunden habe. Falls das Feld leer bleibt, greift der Rückfallweg: `store_api_key` öffnet ein verdecktes Eingabefenster und legt den Key im macOS-Schlüsselbund ab, `check_setup` weist darauf hin.

## Key beim Update der `.mcpb`

Claude Desktop legt Key und Einstellungen unter der Kennung der Erweiterung ab, gebildet aus Autor und Name: `Claude Extensions Settings/local.mcpb.<autor>.<name>.json`. Autor und Name bleiben ab 0.11.0 gleich, deshalb sollte alles erhalten bleiben.

- **Beobachtet:** Bei der Vorversion lagen nach der Installation von 0.10.1 über die älteren Versionen Key und Einstellungen unter dieser Kennung vor. Das ist ein Indiz, kein Test.
- **Offen:** Der echte Test braucht einen Doppelklick in Claude Desktop und zwei Schnippo-Versionen. Ablauf unten.
- **Einmalig:** Der Wechsel von „Resolve Cut“ zu Schnippo ändert die Kennung. Den Key einmal neu eintragen und die alte Erweiterung entfernen.

Test: 0.11.0 installieren, Key eintragen, Einstellung ändern. Eine `.mcpb` mit höherer Version per Doppelklick darüber installieren, Claude neu starten, `check_setup` aufrufen. Der Gladia-Key muss als gesetzt gelten, die geänderte Einstellung muss stehen.

## Was du selbst tun musst

1. Repository öffentlich schalten (Settings → General → Danger Zone → Change visibility).
2. Social-Preview hochladen: Settings → General → Social preview → `assets/brand/social-preview.png`.
3. GitHub auf claude.ai verbinden.
4. Im Portal claude.ai/directory/manage: Submit new → „Plugin bundle“, Plugin-Pfad `plugin`, verfolgter Branch `stable` (eigener Branch, der nur freigegebene Stände bekommt). Dann die Schritte Source, Validate, Listing, Data handling, Compliance (vier Bestätigungen, Kontakt-E-Mail) und Review.
5. Bei jeder neuen Version `version` erhöhen. Neue Versionen prüft Anthropic standardmäßig vor der Veröffentlichung.
