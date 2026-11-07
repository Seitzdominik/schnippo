# Geräusche selbst aufnehmen

Selbst aufgenommene Geräusche klingen echt, und du hast alle Rechte daran. Am meisten lohnt es sich bei Mausklicks, Tastatur und Wanduhr. Vögel und Applaus lassen sich nicht überzeugend rechnen, die nimmst du am besten draußen oder bei einer echten Gelegenheit auf.

## Was du brauchst
Dein Handy mit einer Sprachmemo-App, die WAV aufnimmt, oder ein Ansteckmikro. Besser als jedes Mikro ist ein ruhiger Raum: Fenster zu, Lüfter und Kühlschrank möglichst aus, Handy nicht auf den Tisch legen, sonst nimmt es den Tisch mit auf.

## Ablauf
- **Abstand:** 15–30 cm vom Geräusch, Mikro leicht schräg.
- **Pegel:** Das lauteste Geräusch soll kräftig sein, aber nie an die rote Marke stoßen.
- **Länge:** etwa 30 s je Geräusch.
- **Stille:** vorher 3 Sekunden nichts tun. Daran misst das Werkzeug das Grundrauschen.

| Geräusch | So geht's | Dateiname |
|---|---|---|
| Mausklick | 10–12 Klicks, je 2 s Pause, normal fest | `mausklick.wav` |
| Tastatur | 30 s normal tippen, mit Wörtern und Leertaste, dazwischen kurz stocken | `tastatur.wav` |
| Wanduhr | Mikro 20 cm vor die Uhr, 30 s laufen lassen | `wanduhr.wav` |
| Wecker | einmal ausgiebig klingeln lassen | `wecker.wav` |
| Vögel | morgens draußen, 60 s, ohne Straße im Hintergrund | `voegel.wav` |
| Applaus | echter Applaus, 15–20 s | `applaus.wav` |

Der Dateiname legt die Kategorie fest.

## Aufbereiten
Lege die Dateien in einen Ordner und sag im Chat: „Bereite meine Aufnahmen aus dem Ordner … auf.“ Vorher muss in den Einstellungen ein Sound-Ordner gewählt sein.

Das Werkzeug `prepare_recordings` mindert das Rauschen leicht (höchstens 9 dB), schneidet Klicks in Einzelanschläge (Drücken und Loslassen bleiben zusammen), lässt Tastatur, Uhr, Atmo und Applaus am Stück und bringt alles auf −3 dBFS. Die Ergebnisse landen in `<Sound-Ordner>/Aufnahmen/<Kategorie>/`, der Transient wird beim Einlesen gemessen. Deine Originale bleiben unverändert.

Sollen deine Aufnahmen fest ins Paket, sag Bescheid: Dann kommen sie mit Eintrag in `sfx/LICENSES.md` ins Repo.
