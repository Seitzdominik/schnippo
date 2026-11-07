# Changelog

Format: neueste zuerst. Versionen vor 0.11.0 hießen intern „Resolve Cut“ und waren nicht öffentlich.

## 0.10.1 – Onboarding (Phase 10b, 2026-11-06)

- **Onboarding im Chat:** `onboarding(step, answers)`, Prompts „Onboarding“ und „Hilfe“. Erster Start wird angeboten, „Später“ erinnert höchstens einmal, „Ich kenne mich aus“ springt zu Prüfung und Spickzettel. Spätere Versionen können Neues kurz vorstellen.
- **Vorlieben:** Format, Tempo, Sprache, Grafiken, Sound-Effekte und Standardordner in `preferences.json` neben der Config, Defaults für alle Jobs.
- **Projekte:** `create_project`, Projekte per Name, Ordnernamen als Signal (A-Roll, B-Roll, Bilder, Skript, auch englisch), `brief.md` vor dem Rough Cut. B-Roll aus dem Ordner wird nicht transkribiert.
- Pfade werden robust eingelesen: Anführungszeichen, `~`, `file://`, abschließender `/`, Umlaute in beiden Unicode-Formen.

## 0.10.0 – Reels aus dem langen Video (Phase 10, 2026-11-06)

- **Kandidaten:** `find_reel_candidates` liefert Sätze, Blöcke und Signale, `show_reel_candidates` eine nummerierte Liste mit 9:16-Vorschau. Leitfaden `guides/07_reels.md`.
- **Reel-Cutlist:** `reel_cutlist` nimmt nur Wörter aus einer Stelle der langen Fassung, mit kleinen Kürzungen und Cold Open.
- **Reframing:** 1080×1920 mit `Scaling = Fill`, Ausschnitt am Gesicht, Punch-ins neu, Augen im oberen Drittel. Ohne Keyframes in der API wird bei Bewegung an einer Wortlücke geteilt. B-Roll wird auf den Bildinhalt zugeschnitten.
- **Prüfungen:** `run_qc` je Reel (Ausschnitt, leere Ränder, Gesicht, Auflösung, Dauer, Hook), `reel_sheet` als Kontaktblatt aus echten Render-Frames.
- **Export:** `export_reels` schreibt MP4, SRT und Caption nach `schnippo-export/reels/`.
- **Stabilität:** `build_timeline` verweigert unbenannte Projekte, wechselt zuerst auf die Edit-Seite und importiert alle Medien vor dem ersten Timeline-Item.
- **Sound:** Vinyl-Scratch nur auf Wunsch oder bei Bold Creator; echte Klingel als `ding_real` und `alarm_real`.

## 0.9.2 – Echte Aufnahmen (2026-11-06)

- Maus, Tastatur, Uhr und Vinyl-Scratch sind jetzt echte CC0-Aufnahmen von Freesound statt Synthese, geschnitten mit `sfx/recorded.py`; Lizenzen je Datei geprüft (`sfx/LICENSES.md`).
- Die Uhr-Ausschnitte haben ganze Sekunden und loopen im Takt. Alte Effekt-Namen in Cutlists funktionieren weiter.
- `build_timeline` verweigert ein unbenanntes Projekt: Dort stürzte Resolve beim Render-Preset ab.

## 0.9.1 – Sound-Effekte nach Referenzen (Phase 9b, 2026-11-06)

- **Analyse:** Kennwerte aus 32 Referenzen (nur Zahlen, kein Audio).
- **Generator neu:** 37 Effekte aus Schichten, eigenem Hall (Freeverb-Prinzip), Modalsynthese, Stereo-Bewegung und Mikro-Variation; neu Klick, Tippen, Uhr, Wecker, Downer, Impact.
- **Platzierung:** `event_align` (start, transient, end) und `type` (oneshot, bed, sequence). Riser enden auf dem Ereignis; Betten und Sequenzen in passender Länge. Neue Regeln aus dem Leitfaden.
- **Aufnahmen:** `docs/AUFNAHMEN.md`, `prepare_recordings`.
- **Eigene Keys:** Freesound (`find_sfx`, `fetch_sfx`, Credits-Datei für CC-BY), ElevenLabs (`generate_sfx`).
- Effekt-Kopien tragen einen Inhalts-Hash im Namen: Eine neue Bibliothek ändert fertige Timelines nicht.
- **Korrektur:** Die WAV-Dateien aus Phase 9 fehlten im Repo (`.gitignore`), das Paket war vollständig.

## 0.9.0 – Sound-Effekte (Phase 9, 2026-11-05)

- **Bibliothek:** 20 selbst erzeugte Effekte in 7 Kategorien (`sfx/generate.py`, numpy, feste Seeds, MIT), 48 kHz/24 Bit, 3,3 MB. Der Transient
  jeder Datei ist gemessen (`hit_offset_ms`); Lizenzliste in `sfx/LICENSES.md`.
- **Cutlist:** `sfx: [{category | file, at, event, intensity, gain_db, deliberate, note}]` im B-Roll- und Motion-Durchgang, `at` ist Grafik, Overlay
  oder Wort. Der Server richtet den Transient aus, legt die Effekte auf die Spur „SFX“ und setzt den Pegel relativ zur Stimme (−18 bis −24 dB).
- **Option:** `sfx: "off" | "subtil" | "normal"` (Standard subtil), gekoppelt an die Designsprache. Eigene Sounds über `sfx_folder`.
- **Prüfungen:** `validate_cutlist` und `run_qc`: Anzahl je Format, 3 s Abstand, nicht im Hook-Satz oder CTA, nicht auf jedem Schnitt, Ausklingen.
- **Glossar:** `glossar.txt` und `set_glossary`, Gladia-Vokabular nur mit Eigennamen, `suggest_corrections`, Untertitel-Export, Bauchbinden erst mit
  bestätigtem Namen.
- Neue Werkzeuge: `list_sfx`, `set_glossary`, `suggest_corrections`; `revise` kann `add_sfx` und `remove_sfx`.

## 0.8.5 – Schnittgefühl (Phase 8.5, 2026-11-05)

Aus dem Praxistest des Nutzers an den drei Testprojekten.

- **Zoom:** 100 ↔ 120 % statt 112 %, jede dritte Stufe 112 oder 125 %, Akzent 132 %; Grenze nach Quellauflösung (1080p 125 %,
  4K 200 %), Warnung darüber.
- **Atempausen:** Restpause am Satzende auch an Item-Grenzen (vorher immer nur 200 ms), lange Formate 350–400 ms. Neu: Beats
  `key`/`section`, dahinter bleibt die natürliche Pause stehen (nie künstliche Stille); in langen Formaten Pflicht.
- **Wortenden:** Ausklang und Konsonanten-Einsatz aus dem Signal statt aus Gladias Wortgrenzen; gedehnte Wörter werden nicht
  mehr als Füllwort geschnitten; Laute direkt nach dem Satzende bleiben; Kantenprüfung an jedem Schnitt, „harte Kanten“ in
  `validate_cutlist` und `run_qc`.
- Wortgrenzen, die die Analyse bei leisen Aufnahmen fälschlich kürzte (46 von 63), werden im Schnitt am Signal wiederhergestellt;
  Schnitte, die unter 0,25 s Stille sparen, unterbleiben; Kanal je Teilstück nach dem lauteren Mikro; Callouts in 16:9 auch neben dem Kopf.
- **`sense_check`:** fertigen Schnitt gegenhören: unsaubere Nähte automatisch, Sinnprüfung durch Claude, Beheben per `revise`;
  nur Geändertes kostet erneut; `export_transcript` nutzt die gehörten Wortzeiten.
- **Grafiken:** Innenabstand als Tokens relativ zur Versalhöhe (Bauchbinde klebte am Rand, weil ihr Abstand auf 16 px
  Basisschrift rechnete), Boxbreite folgt dem Text, Eckenradius skaliert mit der Auflösung, Messung im gerenderten Frame,
  Hilfslinien in `preview_graphic`, Prüfung in `run_qc`.

## 0.8.0 – Praxistauglichkeit (Phase 8, 2026-11-05)

Getestet mit drei echten Projekten ohne Skript: Interview (1 Take, 2 Sprecher, 50p-B-Roll), Kursvideo (6 Takes),
Werbespot (6 Sprech-Takes, 12 stumme Szenen).

**Neu**
- Formate `course` und `commercial` mit eigenen Profilen; Erkennung nach Inhalt (Sprecher, Kurs-Wörter, B-Roll-Anteil,
  Take-Länge); Auswahlkarte mit vier Formaten.
- Video-B-Roll: Clips ohne Sprache werden automatisch B-Roll (`set_clip_role` korrigiert), Kontaktabzug
  `get_frames("broll")`, Overlays mit `from_frame`/`to_frame`, stumm oder leise Atmo, Zeitlupe 50 % nur am
  Timeline-Item (`broll_slowmo`), gemischte Framerates für B-Roll, Option `tail` für Schluss-Szenen.
- Werbespot ohne Skript: Clip-Übersicht `get_frames("clips")`, Szenenfolge per `show_review` mit Vorschaubild
  bestätigen lassen – nie eigenmächtig umstellen.
- Interviews: Sprechererkennung S1/S2, Regeln für Interviewer-Fragen, ein Mikro pro Person → jedes Teilstück bekommt
  den Kanal seines Sprechers.
- Korrekturschleife: `locate` (Marker „#05“, Zeit, Zitat), `revise` (neue Version `…_r2` mit Unterschieden),
  `read_timeline_changes` (Handänderungen in Resolve framegenau übernehmen, Unklares melden).
- Lange Videos: Schätzung vor der Transkription (Audio, Kosten, Dauer; Bestätigung ab 30 min), MCP-Fortschritt,
  `clear_cache`.
- Robustheit: Aufträge mit `resume_job`, halbe Timelines heißen `…_unvollstaendig`, Gladia-Aufträge werden nach einem
  Abbruch abgeholt statt neu bezahlt, eigene Bins `Schnippo/…`, Pfadschutz, Fehler in Alltagssprache.
- Aufnahmehilfen: gesprochene Retake-Marker („nochmal“, „Cut“ …) und Klatscher markieren den Satz davor; README
  „So nimmst du für Schnippo auf“.
- `export_final`: Reel 1080×1920, YouTube 1080p oder 4K (H.264/AAC), geprüft (Auflösung, Dauer, Lautheit), SRT/TXT
  daneben.

**Geändert / behoben**
- Deutsches „um“ (und „eh“) ist kein Füllwort mehr (wurde in „um zu“ herausgeschnitten).
- Gesichts-Aussetzer ≤ 0,5 s gelten nicht als Unruhe (falsche Bewegungswarnungen 17 → 3).
- Zoomstufen stehen mindestens 0,6–1,5 s (je Format) – kein Aufblitzen auf kurzen Teilstücken.
- SRT je Format: YouTube/Kurs 2 × 42 Zeichen, mind. 1 s (682 → 281 Blöcke im Interview).
- Sicherheitsspur (−6 dB): der laute Hauptkanal wird genommen, außer er übersteuert.
- Prüf-Renders nur noch 640 px breit und nach der Messung gelöscht (vorher 9,6 GB je Render, 148 GB im Cache).
- Transkriptionsdauer-Schätzung neu kalibriert; CTA-Prüfung nimmt den letzten Satz statt des ganzen Items.

## 0.7.0 – Overlays an Schnitten, Abstand zum Kopf (Phase 7)
Overlay- und Grafikkanten rasten an Schnitten ein; Grafiken halten über die ganze Dauer ≥ 48 px Abstand zum Kopf
(über → ohne Zusatzzeile → verkleinert → neben → unter); Kartendiagnose; Auslöser-Sätze und Prompts; zentraler Name.

## 0.6.0 – Format, Karten, Motion Graphics (Phase 6)
Automatische Formaterkennung (Reel/YouTube), Karten im Chat (Einrichtung, Review, Format, Design), Motion-Graphics-
Durchgang mit deterministischem Render als ProRes 4444 mit Alpha, Markenprofile, eine Tonspur mit bestem Kanal.

## 0.5.0 – Durchgänge und Erweiterung (Phase 5)
Vier Durchgänge (rough/fine/broll/polish) mit Profilen und `run_qc`, `export_transcript` statt Untertiteln in Resolve,
True Peak ≤ −1 dBTP, `check_setup`, Ein-Klick-Erweiterung (.mcpb) mit mitgeliefertem ffmpeg.

## 0.4.0 – Feinschliff (Phase 4)
Explizite Start-/End-Frames, bewegungsbewusste Schnitte, Punch-ins gegen Jump-Cuts, Tonanalyse und nicht-destruktive
Lautheit, robuste Prüf-Renders.

## 0.3.0 – Bilder (Phase 3)
Einzelbild-Cache und Kontaktabzüge, bewegungsbewusste Schnittpunkte, `preview_cuts`, `get_take_frames`, Standbild-
Overlays mit Ken Burns, seitenweiser Edit-Kontext für lange Videos.

## 0.1.0 – Grundlage (Phase 0–2)
MCP-Server, Gladia-Transkription mit Wort-IDs, Analyse (Füllwörter, Pausen, Neuanfänge), Retake-Gruppen, Skript-
Abgleich, Cutlist → Resolve-Timeline mit Framerate des Materials.
