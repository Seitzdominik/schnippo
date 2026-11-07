---
name: reels
description: "Reels aus einem fertigen langen Video finden, bauen und exportieren. Nutzen bei Wünschen wie „Mach aus dem Video 3 Reels“ oder Hochformat aus 16:9."
---

# Reels aus dem langen Video

**Grundhaltung:** Ein Reel ist kein Ausschnitt, sondern eine eigene kleine Geschichte. Es muss ohne die lange Fassung funktionieren. Lieber drei gute als acht mittelmäßige.

## Stellen wählen
`find_reel_candidates` liefert Sätze und Blöcke. Du entscheidest. Bewerte jede zusammenhängende Stelle nach:
1. **Hook:** Der erste Satz zieht sofort rein: These, Zahl, Frage, Überraschung. Kein Bezug auf Vorheriges („wie gesagt“, „das“ ohne Bezug).
2. **Für sich verständlich:** ohne Kontext klar. Namen und Begriffe erklären sich selbst oder kommen nicht vor.
3. **Abschluss:** endet mit Pointe, Erkenntnis oder klarem Satzende, nicht mitten im Gedanken.
4. **Wert:** Tipp, Einsicht, Emotion, Humor, zitierfähiger Satz.

Länge 10–60 s. Richtwert ist eine Aussage je Reel.

**Erlaubt:** kleine Kürzungen innerhalb der Stelle (Füller, Nebensätze, Interviewer-Frage) und den stärksten Satz der Stelle als Cold Open nach vorn ziehen.
**Nicht erlaubt:** Aussagen aus verschiedenen Stellen so zusammensetzen, dass ein neuer Sinn entsteht. `reel_cutlist` nimmt darum nur Wörter aus einer Stelle.

Dem Nutzer zeigst du mit `show_reel_candidates` eine nummerierte Liste mit Titel, Hook-Satz, Dauer, Zeitbereich und Bewertung in einem Satz. Er wählt aus.

## Bauen
`reel_cutlist` → ergänzen → `validate_cutlist` → `build_timeline` → `reel_sheet` → `run_qc(audio=true)` → `sense_check` → `export_reels`.

- **Ausschnitt:** rechnet der Server aus der Kopfbox. Bei wandernder Person teilt er an einer Wortlücke. Mehrere Personen in einem Bild: `reframe.speaker_x` setzen, zum Beispiel `{"0": 0.3, "1": 0.7}`, der Wechsel kommt am Satzanfang.
- **B-Roll:** Die Überlagerungen aus der langen Fassung werden übernommen. Prüfe den Ausschnitt in `reel_sheet`, korrigiere mit `focus_x` (0–1). Im Hook und im letzten Satz Gesicht statt B-Roll.
- **Grafiken:** nie aus der langen Fassung übernehmen, neu setzen. Eine Bauchbinde wird zum kurzen Namens-Callout oder entfällt; im Reel kennt niemand den Sprecher, wichtig ist er nur, wenn der Name zur Aussage gehört. `hook_text` nur, wenn das Reel ihn braucht: eine Zeile, ab Frame 1.
- **Sound:** nach dem Leitfaden Sound-Effekte neu setzen, 2–5 je Reel.

## Prüfen
`sense_check` liest du wie jemand, der die lange Fassung nie gesehen hat: Versteht man es? Bezüge ins Leere? Endet es sauber? Sprache in den ersten 0,5 s, Gesicht im ersten Frame.

Die Caption schreibst du im Ton des Videos: Hook-Zeile, 1–2 Sätze Beschreibung, keine Hashtag-Listen ohne Bezug.
