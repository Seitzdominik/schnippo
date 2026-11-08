<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/logo-dark.svg">
    <img src="assets/brand/logo.svg" alt="Schnippo" width="180">
  </picture>
</p>

# Schnippo

*AI rough cuts for DaVinci Resolve: cut by chat, with audio, zooms, B-roll, graphics and reels.*
*German is the main language of this project. Read the [English summary](#english-summary).*

**KI-Rohschnitt für DaVinci Resolve.** Beta für Mac, Windows als frische Beta: Rückmeldungen willkommen.

<!-- Bild oder GIF mit freigegebenem Material folgt: docs/bilder/schnippo.gif -->

## Was ist Schnippo?

Schnippo baut per Chat aus deinen Takes einen Rohschnitt in DaVinci Resolve Studio: Du sagst Claude, welchen Ordner es schneiden soll, und bekommst eine fertige Timeline aus deinen Originalclips. Schnippo misst Sprache, Pausen, Versprecher und Ton, Claude trifft die redaktionellen Entscheidungen, und du behältst in Resolve das letzte Wort. Auf Wunsch kommen B-Roll, Zooms, Grafiken, Sound-Effekte und Reels aus dem langen Video dazu, alles nicht-destruktiv.

## Voraussetzungen

- Mac mit Apple Silicon oder Windows 10/11, 64 bit (Windows: Beta, Rückmeldungen willkommen)
- DaVinci Resolve Studio 21.1 oder neuer, unter DaVinci Resolve → Preferences → System → General „External scripting using“ auf **Local** (die kostenlose Version kann kein externes Scripting)
- Claude Desktop
- Eigener [Gladia-Key](https://www.gladia.io) für die Transkription

**Kosten:** Schnippo ist kostenlos. Gladia rechnet direkt mit dir ab, grob 0,61 USD je Stunde Audio. Vor jeder Transkription nennt Schnippo die Schätzung. Dazu kommt dein Claude-Abo.

## Installation in 4 Schritten

1. **Download:** Lade die neueste `schnippo-<version>.mcpb` von der [Releases-Seite](https://github.com/Seitzdominik/schnippo/releases).
2. **Doppelklick:** Die Datei öffnet sich in Claude Desktop. Bestätige die Installation.
3. **Key:** Trage deinen Gladia-Key in den Einstellungen der Erweiterung ein.
4. **Claude vollständig neu starten:** Das Fenster zu schließen reicht nicht. Mac: Menüleiste → Claude → Beenden. Windows: unten rechts im Infobereich (System Tray) Rechtsklick auf Claude → Beenden.

Pfad eines Ordners kopieren: am Mac Rechtsklick, Wahltaste halten, „als Pfadname kopieren“. Unter Windows im Explorer Umschalt halten, Rechtsklick, „Als Pfad kopieren“. Die Anführungszeichen dürfen mit in den Chat.

**Erster Start:** Beim allerersten Start richtet Claude Desktop Python und die Grundausstattung ein (etwa 70 MB), solange steht der Fortschrittsbalken still. Unter Windows dauert das zu Hause 1 bis 3 Minuten, auf einem Testserver mit schneller Leitung und ohne Virenscanner 12 Sekunden. Beim ersten Einlesen lädt Schnippo einmalig ffmpeg und die Bildanalyse nach (unter Windows etwa 100 MB) und zeigt den Fortschritt. Ein Virenscanner verlängert beides.

Neue Versionen installierst du genauso. Schnippo weist dich darauf hin und aktualisiert sich nie selbst.

## Erster Schnitt

Starte einen neuen Chat und schreibe **„Richte mich ein“**. Das Onboarding prüft Resolve und den Key, fragt deine Vorlieben ab und legt auf Wunsch einen Projektordner an:

```text
2026-11-07_Mein_Film/
├── A-Roll/      Takes mit Sprache
├── B-Roll/      Bildmaterial ohne Sprache
├── Bilder/      Standbilder, Logos
├── Skript/      Skript, falls vorhanden
├── brief.md     Worum es geht, Format, Länge, Zielgruppe
└── glossar.txt  Namen in richtiger Schreibweise
```

Spickzettel für den Chat:

| Du schreibst | Schnippo macht |
|---|---|
| „Schneide Mein_Film“ | Kompletter Schnitt in einem Rutsch: eine Timeline `Mein_Film_Schnippo` und ein kurzer Bericht |
| „Ohne Grafiken“, „Ohne Sound-Effekte“, „Nur Rohschnitt“ | Dieser Auftrag ohne den genannten Teil |
| „Bei 0:23 den anderen Take“ | Änderung direkt auf der Timeline |
| „Mach nur noch den Ton“ | Lautheit und Limiter auf das, was in der Timeline liegt, auch auf von Hand Eingefügtes |
| „Hol die Fassung von vorhin zurück“ | Eine Sicherung wird wieder zur Arbeits-Timeline |
| „Mach eine Variante als neue Timeline“ | Nur dann entsteht eine zweite Timeline |
| „Mach aus dem Video 3 Reels“ | Hochformat-Reels aus den stärksten Stellen |
| „Füge dezente Sound-Effekte hinzu“ | Eigene Spur mit Effekten |
| „Hilfe“ | Überblick über alles Weitere |

Schnippo arbeitet auf einer Timeline pro Projekt. Vor jeder Änderung legt es eine Sicherung im Bin `Schnippo/Versionen` an (die letzten 5 bleiben). Was du in Resolve von Hand änderst, bleibt erhalten, auch Clips ohne gesprochene Wörter. Deine Originaldateien verändert Schnippo nie. Wer lieber nach jedem Schritt gefragt werden will, sagt im Chat „Rückfragen nach jedem Schritt“. Alle Tools stehen in der [Referenz](docs/REFERENZ.md).

## Aufnahme-Tipps

- **Für Reels in 4K filmen:** Dann bleibt beim Zuschnitt von 16:9 auf 9:16 genug Auflösung. Aus HD wird das Vollbild weich, dann schlägt Schnippo das Layout `framed` vor: das Video als Quadrat mittig auf ruhiger Fläche, ohne Hochskalieren.
- **Versprecher:** Kurz stoppen, deutlich „nochmal“ sagen oder einmal klatschen und den ganzen Satz neu beginnen.
- **Bild:** Vor dem Sprechen 1 Sekunde ruhig in die Kamera schauen. Alle Takes mit derselben Framerate. B-Roll gern mit doppelter Rate, dann ist Zeitlupe möglich.
- **Ton:** Ruhiger Raum, 2–3 Sekunden Raumton am Anfang. Im Interview ein Mikro pro Person auf eigenem Kanal.
- **Namen:** Schreibweisen in die `glossar.txt`, dann stimmen sie schon im Transkript.

Mehr dazu in der [Referenz](docs/REFERENZ.md#so-nimmst-du-für-schnippo-auf), eigene Sound-Effekte aufnehmen: [docs/AUFNAHMEN.md](docs/AUFNAHMEN.md).

## Bekannte Grenzen

- **Speichern-Dialog unter Windows:** Claude Desktop zeigt in „Diese Einstellungen … speichern?“ um Namen und Werte Kästchen mit FSI, PDI oder LRI. Das sind unsichtbare Steuerzeichen, die Claude Desktop selbst setzt und die die Windows-Dialogschrift als Kästchen darstellt. Schnippos Texte enthalten keine; speichern funktioniert trotzdem.
- **Neubau und Farbkorrektur:** Reihenfolge ändern oder neue Tonkanäle zuordnen baut die Timeline neu. Handänderungen an Clips kommen zurück, eine Farbkorrektur auf den neu gebauten Clips nicht. Sie bleibt in der Sicherung.
- **Windows ist Beta:** Automatische Tests laufen auf Windows, mit echtem Resolve ist es noch nicht bestätigt. Rückmeldungen bitte als [Issue](https://github.com/Seitzdominik/schnippo/issues/new/choose). Material gehört lokal auf die Platte, Dateien, die nur in OneDrive liegen, überspringt Schnippo mit Hinweis.
- **Karten in Claude Desktop:** Claude Desktop zeigt die interaktiven Karten lokaler Erweiterungen derzeit nicht an. Schnippo fragt deshalb als Text im Chat.
- **Gemischte Framerates in der A-Roll:** Die Timeline übernimmt die Rate des Hauptmaterials, Takes mit anderer Rate sind nicht erprobt. B-Roll darf abweichen.
- **Lange Videos und kleine Claude-Abos:** Ein Interview mit gut 10 Minuten Sprache braucht etwa 9.200 Token für den ganzen Text, die Übersicht etwa 620. Hochgerechnet sind das bei einer Stunde Sprache rund 50.000 Token je Durchgang, dazu kommen Kontaktabzüge. Schnippo liest lange Takes deshalb seitenweise. Bei kleinen Abos kann die Nutzungsgrenze trotzdem mitten im Schnitt erreicht werden. Die Token sind gemessen, wie schnell ein bestimmtes Abo an seine Grenze kommt, ist nicht gemessen.
- **Noch nicht mit echtem Material erprobt:** Dreh nach Skript, Rohmaterial über 30 Minuten, sehr leise Aufnahmen. Hochformat-Quellen sind nur mit einem einzelnen Clip erprobt.
- **Seltener Resolve-Absturz:** Beim Einfügen von Grafiken ist Resolve 21.1.2 in Tests mehrfach abgestürzt. Die Ursache ist nicht geklärt. Die Reihenfolge beim Bau wurde angepasst, seitdem trat der Fehler in Tests nicht mehr auf. Speichere dein Projekt vor dem Bau.
- **Andere KI-Modelle:** Die Schnittqualität hängt vom Modell ab. Erprobt ist Schnippo nur mit Claude, das Modell braucht Bildverständnis.

## Andere Programme

Für Claude Desktop ist die `.mcpb` der einfachste Weg. Andere MCP-fähige Programme starten Schnippo über [uv](https://docs.astral.sh/uv/) mit `uvx schnippo`. Du brauchst nur den Startbefehl und deinen `GLADIA_API_KEY`.

**Claude Code**

```bash
claude mcp add schnippo -e GLADIA_API_KEY=dein-key -- uvx schnippo
```

**Cursor** (`~/.cursor/mcp.json`)

```json
{"mcpServers": {"schnippo": {"command": "uvx", "args": ["schnippo"], "env": {"GLADIA_API_KEY": "dein-key"}}}}
```

**OpenAI Codex** (`~/.codex/config.toml`)

```toml
[mcp_servers.schnippo]
command = "uvx"
args = ["schnippo"]
env = { GLADIA_API_KEY = "dein-key" }
```

**VS Code mit Copilot** (`.vscode/mcp.json`)

```json
{
  "inputs": [{"type": "promptString", "id": "gladia", "description": "Gladia-Key", "password": true}],
  "servers": {"schnippo": {"type": "stdio", "command": "uvx", "args": ["schnippo"], "env": {"GLADIA_API_KEY": "${input:gladia}"}}}
}
```

Den Key kannst du stattdessen sicher im System ablegen (macOS-Schlüsselbund, Windows-Anmeldeinformationsverwaltung): Sag im Chat „Speichere meinen Gladia-Key“, dann öffnet sich ein Eingabefenster und der Key läuft nicht durch den Chat. Plugin für Claude: [plugin/](plugin/).

## FAQ

**Verändert Schnippo meine Dateien?** Nein. Timelines verweisen auf deine Originalclips, nichts wird neu gerendert oder gelöscht.

**Geht das mit der kostenlosen Resolve-Version?** Nein, sie unterstützt kein externes Scripting.

**Bleibt mein Key beim Update erhalten?** Ja, Claude Desktop speichert Key und Einstellungen pro Erweiterung, und die Kennung bleibt von Version zu Version gleich. Von der internen Vorversion „Resolve Cut“ musst du den Key einmal neu eintragen.

**Ich kannte Resolve Cut. Was passiert mit meinen Daten?** Schnippo übernimmt beim ersten Start Einstellungen, Glossare und Cache aus den alten Ordnern. Alte `resolve-cut-export/`-Ordner liest es weiter.

**Wie schalte ich den Update-Hinweis ab?** In den Einstellungen der Erweiterung, oder mit `SCHNIPPO_UPDATE_CHECK=0`.

## Datenschutz

Keine Telemetrie, kein Schnippo-Server. Schnippo läuft auf deinem Rechner.

| Daten | Wohin | Wann |
|---|---|---|
| Originalmedien, Cache, Einstellungen | bleiben lokal | immer |
| Tonspur (16 kHz, mono, ohne Metadaten) | Gladia, `api.gladia.io` | beim Transkribieren |
| Transkripte, Schnittkontext, Einzelbilder und Kontaktabzüge | das KI-Modell deines Chats, zum Beispiel Claude | während des Schnitts |
| Suchbegriff oder Beschreibung | Freesound, ElevenLabs | nur mit eigenem Key und auf Wunsch |
| Keine Daten, nur die Abfrage der neuesten Version | GitHub, `api.github.com` | höchstens einmal am Tag, abschaltbar |

Nutze Schnippo nur mit Material, das du diesen Diensten geben darfst.

### Privacy Policy

Maßgeblich ist die Website: [Datenschutzerklärung (Deutsch)](https://schnippo.com/datenschutz/) · [Privacy Policy (English)](https://schnippo.com/en/privacy/). Zusammenfassung im Repository: [docs/PRIVACY.md](docs/PRIVACY.md).

- **Datenerhebung:** Schnippo erhebt keine Daten und betreibt keinen eigenen Server.
- **Nutzung und Speicherung:** Transkripte, Analysen und Einstellungen liegen lokal, am Mac in `~/Library/Caches/schnippo` und `~/.config/schnippo`, unter Windows in `%LOCALAPPDATA%\\schnippo\\Cache` und `%APPDATA%\\schnippo`.
- **Weitergabe an Dritte:** nur an die Dienste aus der Tabelle, mit deinem eigenen Konto.
- **Aufbewahrung:** Lokale Daten löschst du jederzeit mit `clear_cache` oder im Finder. Bei Gladia und deinem KI-Anbieter gelten deren Bedingungen.
- **Kontakt:** Seitz Dominik Visuals, https://sdv.design

## Lizenzen

Schnippo steht unter der [MIT-Lizenz](LICENSE), © Seitz Dominik Visuals. Fremde Bestandteile: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

### Marke

Die MIT-Lizenz gilt für den Code. Name, Logo und Icon von Schnippo sind Eigentum von Seitz Dominik Visuals und von der Lizenz ausgenommen: Forks und abgeleitete Projekte dürfen den Code nutzen, aber nicht Namen oder Logo. Details: [assets/brand/README.md](assets/brand/README.md).

DaVinci Resolve ist eine Marke von Blackmagic Design. Schnippo ist ein unabhängiges Projekt und nicht mit Blackmagic Design verbunden.

## Mitmachen

Fehler und Wünsche gern als [Issue](https://github.com/Seitzdominik/schnippo/issues/new/choose). Bitte hänge nie echtes Material oder Keys an.

```bash
uv sync
uv run pytest
git config core.hooksPath .githooks
```

Der Hook startet `tools/check_public.py`. Technische Erkenntnisse stehen in [docs/ENTWICKLUNG.md](docs/ENTWICKLUNG.md).

---

## English summary

**Schnippo** is an AI rough-cut assistant for DaVinci Resolve Studio. Tell Claude which folder to cut and get a non-destructive timeline built from your original clips, with audio mastering, zooms, B-roll, graphics, sound effects and reels. Before every change it saves a backup timeline, and manual edits in Resolve are kept. The messages and guides are in German; English footage works too.

**Requirements:** Apple Silicon Mac or 64-bit Windows 10/11 (beta), DaVinci Resolve Studio 21.1+ with Preferences → System → General → External scripting using = Local, and your own [Gladia key](https://app.gladia.io) (roughly USD 0.61 per hour of audio).

**Install:**

- *Chat in Claude Desktop:* download the `.mcpb` from [Releases](https://github.com/Seitzdominik/schnippo/releases), double-click it, enter your key, then fully quit and reopen Claude from the menu bar (Windows: system tray). The first start takes 1–3 minutes on Windows.
- *Claude Code, the Code tab of Claude Desktop, Cowork on your computer:* install the plugin with `/plugin marketplace add Seitzdominik/schnippo` and `/plugin install schnippo@schnippo`. You need [uv](https://docs.astral.sh/uv/).
- *Other MCP clients:* run `uvx schnippo` with `GLADIA_API_KEY` set.

**First cut:** say "Set me up", then "Cut the folder /path/to/takes as a YouTube video". You get one timeline named `<name>_Schnippo` and a short report. Corrections work in plain words, for example "Remove #05" or "Make 3 reels from the finished video".

**Privacy:** no telemetry and no Schnippo server. Audio goes to Gladia, transcripts and frames go to your AI model, and the update check asks GitHub once a day (optional). Read the [Privacy Policy](https://schnippo.com/en/privacy/).

**Licence and trademark:** MIT, © Seitz Dominik Visuals. DaVinci Resolve is a trademark of Blackmagic Design. Schnippo is an independent project and is not affiliated with Blackmagic Design.
