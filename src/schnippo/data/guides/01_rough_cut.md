# Durchgang 1: Rough Cut

**Einziger Job dieses Durchgangs:** Inhalt, Reihenfolge, Take-Wahl, Laufzeit. Nur harte Schnitte. Keine Zooms, keine B-Roll, keine Feinarbeit an Pausen.

Kennzeichnung: **[E]** belegt · **[P]** Profi-Praxis · **[S]** Default/Synthese (konfigurierbar). Format-Profile: `reel` (9:16, 30–90 s), `youtube` (16:9, 8–15 min, auch Interviews), `course` (16:9, ruhiger, Kapitel je Lektion) und `commercial` (Werbespot, 15–60 s, viel Bild).

## Vorgehen
1. `get_edit_context` (bei langen Videos: Übersicht, dann seitenweise).
2. Retake-Gruppen prüfen und korrigieren. Umformulierungen desselben Inhalts gehören in dieselbe Gruppe, auch wenn der Server sie nicht gruppiert hat.
3. Pro Gruppe genau einen Versuch wählen (Regeln unten).
4. Hook und Ende festlegen.
5. `validate_cutlist` → den gesprochenen Endtext laut „mitlesen": Ist jeder Satz nötig? Ist der rote Faden klar?
6. Im Komplett-Schnitt weiter mit dem Fine Cut, nichts bauen. Im Durchgangs-Modus: `build_timeline` baut `<Name>_Schnippo`.

## Eigennamen zuerst klären
Namen von Personen, Firmen, Marken, Orten und Adressen nie raten. Liegt ein `glossar.txt` im Material-Ordner, gilt es; sonst kurz fragen, wenn `transcribe` „Eigennamen unsicher“ meldet (nur echte Namen, Fachwörter und Beugungen in der Liste übergehen), und `set_glossary` aufrufen. `suggest_corrections` zeigt dann die Stellen. Bauchbinden werden erst mit bestätigtem Namen gerendert.

## Take-Auswahl
- **Rangfolge** [P]: 1. inhaltlich korrekt → 2. vollständig und verständlich → 3. glaubwürdig/energisch vorgetragen → 4. passt an Vorgänger und Nachfolger → 5. Kontinuität (Haltung, Hände, Blick).
- Takes **nie nur nach Transkript** bewerten [P]. Bei knappen Entscheidungen `get_take_frames` anfordern (Gesicht, Energie, Blick in die Kamera).
- Der **letzte vollständige Versuch ist nur Tie-Breaker** [S], keine Regel.
- Ein zusammenhängender Take mit kleinem Fehler schlägt ein Komposit [P]. Höchstens **eine Naht pro Satz**, und nur an einer echten Pause.
- Erkennungsfehler im Transkript (Konfidenz 0,0, unsinnige Wörter) sind kein Grund, einen Take zu verwerfen. Im Zweifel Frames ansehen.

## Hook (Anfang)
- **Sprache und Gesicht ab dem ersten Frame** [E: Sprache in den ersten 3 s ≈ +25 % 10-s-Retention, frühes Gesicht ≈ +10 %]. Gesicht mindestens 1 s in den ersten 3 s.
- Erster Frame = kurz vor dem ersten Wort des Hooks (`start_frame`, Vorlauf ≤ 2–4 Frames) [S]. Keine Begrüßung, kein „Hallo, heute…", kein Hereinkommen ins Bild.
- Stärkste Aussage (Ergebnis, Zahl, Gegenthese) darf als **Cold Open nach vorn**, wenn sie später im Take liegt [S]. Nicht identisch wiederholen.
- Thema verbal klar: Reel ≤ 2 s (Kontext bis ~5 s), YouTube Versprechen ≤ 15 s, Agenda/Open Loop ≤ 30 s [E/S].
- Nicht mit B-Roll beginnen, außer die B-Roll ist selbst der Hook.

## Inhalt verdichten
- Jeden Satz ohne neue Information streichen; Abschweifungen vom roten Faden streichen [P].
- Ad-libs behalten, wenn sie ein konkretes Beispiel, Humor oder Emotion liefern und allein verständlich sind; sonst streichen. Grenzfälle als `note: "Grenzfall: …"` markieren [S].
- Mit Skript: Skriptreihenfolge. Fehlende Skriptzeilen im Ergebnis melden. Ohne Skript: Aufnahmereihenfolge, Inhalte nicht umstellen (Ausnahme: Cold Open).
- Inhaltliche Widersprüche (z. B. „zwei Phasen" vs. „drei Phasen") nicht still auflösen, sondern dem Nutzer melden.

## Laufzeit
- Reel: 30–60 s für eine These, 60–90 s nur für Listen/Schritte [S, Daten widersprüchlich]. Empfehlung nach Instagram: ≤ 3 min, sonst keine Empfehlung im Feed [E].
- YouTube: Re-Hook (neue offene Frage, Reveal) an jeder Kapitelgrenze, etwa alle 2–3 min [S].

## Ende
- Kein Ankündigen des Endes, kein Outro, kein „Danke fürs Zuschauen" [P].
- CTA höchstens ein Satz, bevorzugt auf Teilen/Speichern [E: Sends/Saves sind starke Signale]. Reel-CTA ~2–3 s.
- Reel-Loop: Wenn möglich leitet der letzte Satz in den Hook über; kein Fade, kein Schwarzbild [S].

## Interview (mehrere Sprecher)
- Segmente tragen `S1`/`S2` (Sprechererkennung). S1 ist der Sprecher mit den meisten Wörtern, meist der Gast [S].
- **Fragen des Interviewers** sind eine redaktionelle Entscheidung. Defaults [S]: Social-Clip/Reel → Fragen **raus**, die Antwort muss allein verständlich sein (sonst einen Satz der Antwort davor nehmen, der die Frage wiederholt). Langfassung (YouTube) → Fragen **kurz behalten** (nur der Kern der Frage, ohne „Ähm, und sag mal…“).
- Ist unklar, welche Fassung gewünscht ist, oder steht eine Frage für ein ganzes Kapitel: im Review als `kind: "frage"` nachfragen.
- Vorgespräch, Technik-Absprachen („Schau zu mir“, „Läuft?“) und Zwischenrufe immer raus.
- Antworten nicht umstellen, außer für den Cold Open. Mehrere Antworten auf dieselbe Frage: wie Retakes behandeln.
- Dauerhaft ins Wort fallen: Überlappungen nicht schneiden, sondern den Satz des Gastes vollständig lassen.

## Kursvideo (course)
- Ruhiger als YouTube: Pausen dürfen bleiben (Denkpausen zum Mitschreiben), wenige Punch-ins [S].
- Begrüßung **einmal** am Anfang des Kurses/der Lektion ist erlaubt, kurz. Jede Lektion bekommt ein Kapitel (`chapters`).
- Mehrere Takes je Abschnitt: einen wählen; abgebrochene Erklärungen und Versprecher-Anläufe raus.
- Bildschirmaufnahmen dürfen lange stehen; Schnitt dort, wo der Sprecher den nächsten Schritt ansagt.

## Werbespot (commercial) – Szenen ohne Skript
- Claude gruppiert die Clips nach **Bild, Ort und Dialog** zu Szenen: `get_frames("clips")` (ein Mittelbild je Clip) und `get_edit_context` (gesprochene Takes).
- Claude schlägt eine **Reihenfolge der Szenen** vor und lässt sie **vor dem Rohschnitt bestätigen**: nummerierte Liste, je Szene ein Vorschaubild – mit Karte über `show_review(timeline="Szenenfolge", decisions=[{kind: "reihenfolge", question: "1. Szene …", frame: "c07:f0040"}, …])`, sonst als Liste im Chat. **Nie eigenmächtig umstellen.**
- Ein Storyboard oder eine Shotlist gilt wie ein Skript (`load_script`): dann deren Reihenfolge.
- Der gesprochene Text kommt meist aus wenigen kurzen Retakes. Den besten vollständigen Take wählen; B-Roll trägt den Rest.
- Laufzeit 15–60 s; Hook in den ersten 3 s (Bild oder Satz).

## Nicht in diesem Durchgang
Split-Edits, Punch-ins, B-Roll, Musik, Ton-Bearbeitung.
