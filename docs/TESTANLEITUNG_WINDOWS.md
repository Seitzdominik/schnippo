# Testanleitung Windows

Dauer: etwa 45 bis 60 Minuten. Du prüfst, ob Schnippo auf einem echten Windows-PC mit DaVinci Resolve läuft. Das geht nur dort, die automatischen Tests kennen kein Resolve.

Hake ab, was klappt, und notiere bei allem anderen, was stattdessen passiert ist. Klemmt es: [WINDOWS_DEBUG_PROMPT.md](WINDOWS_DEBUG_PROMPT.md).

## 1. Voraussetzungen

- [ ] Windows 10 oder 11, 64 bit
- [ ] DaVinci Resolve Studio 21.1 oder neuer
- [ ] Claude Desktop in der aktuellen Version
- [ ] Dein Gladia-Key
- [ ] Testmaterial: ein Testprojekt per USB oder Netzlaufwerk auf den PC kopieren, etwa ein Take von 1 bis 3 Minuten

**Wichtig:** Das Material muss wirklich lokal liegen. Dateien, die OneDrive nur als Platzhalter führt (Wolken-Symbol), überspringt Schnippo. Am einfachsten ein Ordner wie `C:\Schnitt\Test`.

## 2. Resolve vorbereiten

- [ ] Resolve öffnen
- [ ] DaVinci Resolve → Preferences → System → General → „External scripting using“ auf **Local** stellen, Resolve neu starten
- [ ] Ein eigenes Testprojekt öffnen

## 3. Schnippo installieren

- [ ] Die `.mcpb` von der [Releases-Seite](https://github.com/Seitzdominik/schnippo/releases) laden
- [ ] Doppelklick, in Claude Desktop bestätigen
- [ ] Gladia-Key eintragen und speichern
- [ ] Claude vollständig beenden: unten rechts im Infobereich (System Tray) Rechtsklick auf Claude → Beenden. Dann neu starten

Beim ersten Start lädt uv Python und ffmpeg nach (etwa 100 MB), das kann ein paar Minuten dauern.

## 4. Einrichtung prüfen

- [ ] Neuer Chat: „Richte mich ein“
- [ ] Alle Punkte grün? **Screenshot machen**

Achte besonders auf „DaVinci Resolve installiert“, „Verbindung zu Resolve“ und „Python für fusionscript.dll“.

## 5. Onboarding

- [ ] Einmal komplett durchlaufen, inklusive Projektordner anlegen
- [ ] Stimmt der Tipp zum Pfad-Kopieren (Umschalt + Rechtsklick → „Als Pfad kopieren“)?

## 6. Kurzer Schnitt

Sag zum Beispiel: „Schneide `C:\Schnitt\Test` als Reel, mit Grafik und Sound-Effekt“. Lass alle Durchgänge laufen. Der erste Grafik-Render lädt Chromium (etwa 90 MB).

In Resolve prüfen:

- [ ] Timeline ist da, Framerate stimmt
- [ ] Ton auf beiden Seiten
- [ ] Grafik hat Transparenz, kein schwarzer Kasten
- [ ] Schnitte sind sauber, keine Sprünge
- [ ] Sound-Effekt liegt auf der eigenen Spur
- [ ] Optional bei HD-Material: Reel mit Layout `framed` bauen lassen

## 7. Export

- [ ] „Exportiere das Reel“
- [ ] Reel-Datei und SRT liegen in `schnippo-export` neben dem Material
- [ ] Die Datei spielt ab, Bild und Ton stimmen

## 8. Fehlerfälle

- [ ] **Resolve schließen**, dann „Erneut prüfen“: Schnippo meldet das verständlich, nach dem Öffnen läuft es weiter
- [ ] **Pfad mit Leerzeichen und Umlauten:** Ordner `C:\Schnitt\Mein Bäcker Film`, Pfad aus dem Explorer mit Anführungszeichen einfügen
- [ ] **Netzlaufwerk:** Material auf einem verbundenen Laufwerk (`Z:\...`) oder unter `\\server\freigabe\...` einlesen, Timeline bauen
- [ ] **Geöffnete Datei:** Eine Export-Datei im Player offen lassen und erneut exportieren: Kommt eine verständliche Meldung?

## 9. Was du zurückmeldest

- Screenshots aus Schritt 4 und von allem, was nicht geklappt hat
- Die Log-Datei `%APPDATA%\Claude\logs\mcp-server-Schnippo.log` (vorher durchsehen, sie enthält Dateinamen, aber nie den Key)
- Windows-Version (`winver`), Resolve-Version, Claude-Desktop-Version
- Die angehakte Liste

Bitte kein Testmaterial und keinen Key an ein öffentliches Issue hängen.
