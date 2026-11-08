# Schnippo

KI-Rohschnitt für DaVinci Resolve. Schnippo baut aus deinen Takes per Chat einen Rohschnitt in DaVinci Resolve Studio, mit Ton, Zooms, B-Roll, Grafiken und Reels. Deine Originaldateien bleiben unverändert. DaVinci Resolve ist eine Marke von Blackmagic Design, Schnippo ist ein unabhängiges Projekt.

## Einrichtung

Du brauchst einen Mac oder Windows 10/11 (64 bit, Beta), DaVinci Resolve Studio 21.1 oder neuer mit „External scripting using = Local“, [uv](https://docs.astral.sh/uv/) und einen eigenen [Gladia-Key](https://app.gladia.io). Nach der Installation fragt das Plugin nach dem Key. Gibt es keine Abfrage, sag im Chat „Richte mich ein“: Das Tool `store_api_key` öffnet ein Systemfenster und legt den Key im Schlüsselbund ab. Der Key läuft nie durch den Chat.

## Installation

`/plugin install schnippo --marketplace Seitzdominik/schnippo`

## Nutzung

Sag zum Beispiel „Schneide den Ordner … als Reel“ oder „Mach aus dem Video 3 Reels“. Beim ersten Start führt ein kurzes Onboarding durch alles.

## Was das Plugin startet und wohin es Daten schickt

Das Plugin startet den lokalen MCP-Server mit `uvx schnippo@0.13.0` von PyPI. Quellcode: https://github.com/Seitzdominik/schnippo

| Ziel | Wann | Was |
|---|---|---|
| Gladia (api.gladia.io) | beim Transkribieren | Tonspur der Clips |
| GitHub (api.github.com) | höchstens einmal täglich, abschaltbar | Abfrage der neuesten Version, keine Daten |
| Freesound, ElevenLabs | nur mit eigenem Key und auf Wunsch | Suchbegriff oder Beschreibung |
| PyPI, GitHub (Playwright, ffmpeg) | bei Installation und beim ersten Grafik-Render | Download von Abhängigkeiten |

Transkripte und Kontaktabzüge sieht das KI-Modell deines Claude-Kontos. Es gibt keine Telemetrie.

## Privacy Policy

Vollständig unter https://schnippo.com/en/privacy/.

- **Datenerhebung:** Schnippo selbst erhebt keine Daten und betreibt keinen Server.
- **Nutzung und Speicherung:** Transkripte, Analysen und Einstellungen bleiben lokal: am Mac in `~/Library/Caches/schnippo` und `~/.config/schnippo`, unter Windows in `%LOCALAPPDATA%\\schnippo\\Cache` und `%APPDATA%\\schnippo`.
- **Weitergabe an Dritte:** nur an die Dienste aus der Tabelle oben, mit deinem eigenen Konto.
- **Aufbewahrung:** Du löschst lokale Daten jederzeit mit `clear_cache` oder im Finder. Für Gladia gelten deren Bedingungen.
- **Kontakt:** Seitz Dominik Visuals, https://sdv.design

## Lizenz

MIT. Hinweise zu Dritten: https://github.com/Seitzdominik/schnippo/blob/main/THIRD_PARTY_NOTICES.md
