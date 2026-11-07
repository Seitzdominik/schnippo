# Referenz

Alle Tools und Einstellungen im Detail. Einstieg: [README](../README.md).

## Tools

| Tool | Zweck |
|---|---|
| `ingest_folder(path, import_to_resolve=False, recursive=False)` | Clips und Standbilder finden, ffprobe, VFR-Check, IDs `c01…`/`i01…`, optional Import in einen Bin |
| `transcribe(clip_ids="all")` | Transkription (Gladia, 3 parallel) + Analyse, gecacht; vorher Schätzung (Audio, Kosten, Dauer), ab 30 min neuem Audio erst nach Bestätigung |
| `list_clips()` | Übersicht |
| `get_transcript(clip_id, from_word=None, to_word=None)` | kompaktes Transkript mit Wort-IDs |
| `load_script(path=None)` | optionales Skript (.docx/.txt/.md) → Zeilen `L01…` |
| `get_edit_context(…, pass="rough")` | Segmente, Retake-Gruppen, Skript-Kandidaten, Standbilder + nur der Leitfaden des Durchgangs; lange Videos: `overview=True`, dann `page=N` |
| `get_frames(target, mode)` | Kontaktabzüge (Bild-IDs `c01:f0123`) von Segmenten, Intervallen, Szenen oder Standbildern – nur bei Bedarf |
| `get_take_frames(group)` | Versuche einer Retake-Gruppe nebeneinander (knappe Take-Wahl) |
| `validate_cutlist(cutlist)` | Trockenlauf: Teilstücke in Frames, Bewegungswerte je Schnitt, Overlays, gesprochener Endtext |
| `preview_cuts(cutlist)` | Bildpaare „vor \| nach“ für die auffälligsten Schnitte |
| `analyze_audio(clip_ids)` | Lautheit, True Peak, Rauschboden, Sprachspektrum mit Empfehlungen |
| `set_word_text(word, text)` / `suggest_corrections(clip)` | Erkennungsfehler korrigieren (IDs bleiben; gilt für Endtext und Export) |
| `export_transcript(cutlist \| timeline)` | SRT, TXT (und bei YouTube Kapitel) des fertigen Schnitts nach `schnippo-export/` |
| `merge_cutlists(cutlists)` | Teil-Cutlists (seitenweise Entscheidungen) zusammenführen |
| `build_timeline(cutlist)` | neue Timeline bauen (Framerate des Hauptmaterials), Punch-ins, B-Roll auf V2, Audio-Lautheit (True Peak ≤ −1 dBTP), Export-Preset, verifizieren |
| `locate(timeline, ref)` | „#05“ (Marker), Zeit „0:23“ oder Zitat → Item, Wort-IDs, Position |
| `revise(base_timeline, instructions)` | Änderungswünsche (entfernen, trimmen, verschieben, einfügen, Take tauschen, Zoom, Overlays) → neue Version `…_r2` mit Unterschieden |
| `read_timeline_changes(timeline)` | Handänderungen in Resolve erkennen und framegenau als neue Version übernehmen; Unklares wird gemeldet |
| `set_glossary(terms)` / `glossar.txt` | Namen, Marken, Orte, Adressen in richtiger Schreibweise: Gladia-Vokabular für neue Clips, Korrekturvorschläge, Untertitel, Freigabe für Bauchbinden |
| `set_clip_role(clips, role)` | Clip von Hand als A-Roll oder B-Roll festlegen |
| `resume_job(job_id=None)` | abgebrochenen Auftrag fortsetzen (Bauen: neu aus der gespeicherten Cutlist, halbe Timeline `…_unvollstaendig` wird entfernt; Transkription: fehlende Clips, laufende Gladia-Aufträge werden abgeholt) |
| `clear_cache(older_than_days=30)` | Cache-Größe je Kategorie zeigen und Altes löschen (Transkripte und verwendete Renders nur auf Wunsch) |
| `sense_check(timeline)` | fertigen Schnitt gegenhören (Gladia, etwa 0,10 USD je 10 min): unsaubere Nähte automatisch, der gehörte Text zur Sinnprüfung; nach `revise` kostet nur Geändertes |
| `export_final(timeline, preset="auto")` | fertiges Video rendern: Reel 1080×1920 oder YouTube 1080p/4K (H.264/AAC, Lautheit aus Polish), Datei geprüft, SRT/TXT daneben |
| `run_qc(timeline, audio=False)` | QC: Flash-Frames, Lücken, angeschnittene Wörter, Zoom auf jedem Schnitt, Framerate, Dauer, Sync, Wasserzeichen-Hinweise, optional Lautheit |
| `check_setup()` | Einrichtungs-Assistent (Karte im Chat): Resolve, Studio, Version, Scripting, Projekt, Gladia-Key, ffmpeg, Speicher |
| `detect_format(hint)` / `set_format(format)` | Reel, YouTube, Kurs oder Werbespot aus dem Material erkennen (Auswahlkarte bei Unklarheit) |
| `show_review(timeline, decisions)` / `submit_review` | Review-Karte nach Rough/Fine: Behalten / Raus / Egal, Antwort kommt als Chat-Nachricht |
| `preview_graphic(cutlist)` | Motion Graphics: 6 Standbilder je Grafik über dem echten Frame + Prüfungen, vor dem Rendern |
| `motion_setup()` | Grafik-Renderer (Playwright + Chromium) vorab installieren; sonst beim ersten Gebrauch |
| `setup_design(brand)` / `save_brand` | Design-Einrichtung (Karte): Stil, Schrift, Farben mit Kontrastprüfung, Radius, Vorschau |
| `list_sfx()` | Sound-Effekte: Bibliothek und eigener Ordner (Kategorie, Stufe, Länge, Transient, Lizenz) |
| `prepare_recordings(folder, category=None)` | Eigene Aufnahmen aufbereiten und in den Sound-Ordner legen |
| `find_sfx(category, …)` / `fetch_sfx(sound_id, category)` | Freesound mit eigenem Key: Suche mit Lizenzfilter, Rangfolge nach Kennwerten, Download |
| `generate_sfx(text, category, …)` | ElevenLabs mit eigenem Key: Effekt aus einer Beschreibung, kostet Credits |
| `find_reel_candidates(timeline, …)` / `show_reel_candidates` | Reel-Kandidaten aus der langen Fassung, nummerierte Liste mit Vorschau |
| `reel_cutlist(timeline, from_word, to_word, …)` | Cutlist eines Reels aus einer Stelle, mit Kürzungen und Cold Open |
| `reel_sheet(timeline)` | Kontaktblatt mit Kopfbox und Safe Zone aus echten Frames |
| `export_reels(reel_timelines, captions)` | MP4, SRT und Caption je Reel |
| `onboarding(step, answers)` | Erster Start: Einrichtung, Vorlieben, Tipps, Test, Spickzettel |
| `create_project(name)` | Projektordner im Standardordner anlegen |
| `resolve_status()` | Verbindungscheck |

Prompt: `rohschnitt` (Ablauf der vier Durchgänge). Ressourcen: `schnippo://guides/rough|fine|broll|polish|technik`.

## Vier Durchgänge

Jeder Durchgang hat genau einen Job und baut eine eigene Timeline (`<Name>_V1_Rough`, `_V2_Fine`, `_V3_BRoll`,
`_V4_Polish`). Die Cutlist trägt `"pass"`; spätere Durchgänge geben `"base_cutlist": "<Timeline davor>"` an, der Server
übernimmt alles daraus und ignoriert mit Warnung, was der Durchgang nicht ändern darf. Leitfäden: [guides/](guides/).

| Durchgang | Job | darf setzen |
|---|---|---|
| `rough` | Inhalt, Reihenfolge, Take-Wahl, Laufzeit; nur harte Schnitte | `items`, `rejected`, `corrections` |
| `fine` | Pausen/Füller nach Profil, Schnittpunkte, Punch-ins | `options`, `punch_in`, `item_changes`, `items` (gemeldet) |
| `broll` | Standbilder und Video-B-Roll (stumm, optional Atmo/Zeitlupe) über passende Wortbereiche | `overlays` |
| `polish` | Ton, QC, Export | `audio`, `item_changes` (nur nach QC-Fehler) |
| `motion` (optional) | Motion Graphics als ProRes 4444 mit Alpha auf V3 | `graphics`, `brand` |

Profile in `~/.config/schnippo/config.toml`: `format = "auto" | "reel" | "youtube" | "course" | "commercial"`,
`style = "ruhig" | "ruhig-dicht" | "dicht"`, einzelne Werte unter `[profile]` bzw. `[profile.<format>]` (z. B.
`keep_pause_ms`, `punch_in_scale`, `max_unchanged_s`; vollständige Liste in `src/schnippo/profiles.py`).

| Format | Bild | Laufzeit | Eigenheiten |
|---|---|---|---|
| `reel` | 9:16 | 30–90 s | dichte Pausen, Wort-für-Wort-Untertitel |
| `youtube` | 16:9 | 8–15 min | Kapitel, Interviews (Fragen kurz behalten), SRT 2 × 42 Zeichen |
| `course` | 16:9 | 2–30 min | ruhiger (Restpause 350 ms, wenige Punch-ins), Kapitel je Lektion |
| `commercial` | wie das Material | 15–60 s | viel B-Roll, Szenenfolge wird vor dem Rohschnitt bestätigt |

Material mit mehreren Clips: Clips ohne Sprache (keine Wörter oder Ø-Konfidenz < 0,25) gelten automatisch als
**B-Roll** (`set_clip_role` korrigiert). Interviews: Sprechererkennung (S1/S2); bei einem Mikro pro Person nimmt jedes
Teilstück den Kanal seines Sprechers.

## So legst du ein Projekt an

Im Chat: „Leg ein Projekt Kunde Thema an.“ Das geht, sobald ein Standardordner eingestellt ist (Onboarding oder Einstellungen der Erweiterung). Dann reicht später der Name: „Schneide Kunde Thema.“

```
<Standardordner>/
  2026-11-06_Kunde_Thema/
    A-Roll/        Sprecher-Takes (bei mehreren Sprechern optional Unterordner je Person)
    B-Roll/        Videos ohne Sprache
    Bilder/        Standbilder, Logos
    Skript/        .docx, .txt, .md (optional)
    glossar.txt    Namen, Firmen, Orte, Adressen in richtiger Schreibweise (optional)
    brief.md       Kurz-Briefing, Stichworte reichen (optional)
    schnippo-export/   entsteht automatisch: Exporte, Transkripte, Reels
```

Je strukturierter, desto besser der Schnitt. Die Ordnernamen gelten direkt als Einordnung, auch `Interview`, `Footage`, `Images`, `Script` und Ähnliche. B-Roll aus dem Ordner wird nicht transkribiert, das spart Kosten. Klingt ein Clip dort nach Sprache, kommt ein Hinweis. Ein unsortierter Ordner funktioniert auch, dann zeigt Claude die Einordnung kurz zur Bestätigung. Dateien werden nie verschoben oder umbenannt.

Einen Pfad kannst du immer in den Chat kopieren. Am Mac: Rechtsklick auf den Ordner, Wahltaste (⌥) halten, „… als Pfadname kopieren“ (oder ⌥⌘C im Finder).

## Sound-Effekte

38 Effekte liegen bei (`sfx/`, auch kommerziell frei): 28 selbst erzeugt (MIT), Maus, Tastatur, Uhr, Klingel und Vinyl-Scratch als echte Aufnahmen unter CC0. Der Vinyl-Scratch kommt nur auf Wunsch oder bei Bold Creator. Kategorien: whoosh, swish, pop, tick, click, ding, impact_soft, impact, riser, downer, typing, clock, alarm. Atmo und Applaus lassen sich nicht echt rechnen, sie kommen aus deinem Sound-Ordner. Claude schlägt die Effekte im B-Roll- oder Motion-Durchgang nach `guides/06_sound_design.md` vor. Der Server richtet den Transient auf das Ereignis aus (Box geht auf, Bildwechsel, Zähler-Endwert) und legt die Effekte auf eine eigene Spur „SFX“. Dort kannst du sie in Resolve einzeln verschieben, leiser machen oder löschen.

| Einstellung | Wirkung |
|---|---|
| `sfx: "off"` | keine Effekte |
| `sfx: "subtil"` (Standard) | leise: Akzente −20 dB, Whooshes −22 dB unter der Stimme |
| `sfx: "normal"` | 2 dB präsenter, eine Intensitätsstufe höher |

Die Designsprache verschiebt das: Minimal Editorial nimmt wenige und sehr leise Effekte, Bold Creator präsentere, Soft Premium keine harten Impacts, Clean Tech Ticks statt Whooshes.

Riser enden auf dem Ereignis. Atmo, Ticken und Tippen beginnen darauf und laufen so lange wie das Element oder `duration_ms`; der Server legt dafür eine passend lange Kopie an.

Eigene Aufnahmen: Anleitung in [docs/AUFNAHMEN.md](docs/AUFNAHMEN.md), `prepare_recordings` schneidet und pegelt sie. Freesound (`find_sfx`, `fetch_sfx`) und ElevenLabs (`generate_sfx`) gehen mit deinem eigenen Key, geladen wird in deinen Sound-Ordner. Die Pixabay-API bietet kein Audio; deine Pixabay-Downloads legst du einfach selbst in den Sound-Ordner, sie gehören nie ins Repo.

Eigene Sounds: `sfx_folder` in den Einstellungen (oder `[sfx] folder` in der Config). Die Kategorie kommt aus dem Ordner- oder Dateinamen, der Transient wird gemessen. Für die Lizenz eigener Sounds bist du selbst verantwortlich. Mitgelieferte Effekte kopiert der Server beim Bauen in `schnippo-export/sfx/`, damit ein Projekt nach einem Update der Erweiterung nicht offline geht.

## Reels aus dem langen Video

Aus einer fertigen 16:9-Timeline entstehen eigene Timelines `<Name>_Reel_01` in 1080×1920, die lange Fassung bleibt unangetastet. Claude schlägt zusammenhängende Stellen von 10–60 s vor, du wählst aus. Der Ausschnitt folgt dem Gesicht und bleibt eine Eigenschaft der Timeline-Items, du kannst ihn in Resolve nachstellen. Grafiken und Sound-Effekte werden für das Hochformat neu gesetzt.

Aus 4K bleibt das Bild scharf. Aus 1080p wird es rund 1,8-fach hochskaliert und sichtbar weicher; das meldet die Prüfung mit der effektiven Auflösung. Die fertigen Dateien liegen in `schnippo-export/reels/`: MP4, SRT, Caption und Kontaktblatt.

## Sicherheit und Ordnung

- Gelesen wird nur im angegebenen Material-Ordner (und im Export-Ordner); Pfade werden vorher aufgelöst, Verknüpfungen
  nach außerhalb werden übersprungen und gemeldet. Zu allgemeine Ordner (`/`, Benutzerordner, Schreibtisch, Dokumente …)
  werden abgelehnt.
- Geschrieben wird nur in den Export-Ordner (`schnippo-export/` neben dem Material oder der eingestellte Ordner) und
  in den Cache. Originalmedien werden nie verändert, verschoben oder gelöscht.
- In Resolve legt das Werkzeug alles unter dem Bin **„Schnippo“** ab (`<Ordnername>`, `Standbilder`, `Grafiken`,
  `Audio-Extrakte`). Clips, die schon in eigenen Bins liegen, werden nur benutzt, nie verschoben oder doppelt importiert.
  Timelines werden nie überschrieben; während des Bauens heißen sie `…_unvollstaendig`.
- Grafiken werden in einer Browser-Sandbox ohne Netzwerkzugriff gerendert; eigene Schriften nur als Schriftdatei aus den
  Schriftordnern oder dem Material-Ordner.

## Karten im Chat

Die Tools liefern zusätzlich interaktive Karten (MCP Apps: Einrichtungs-Assistent, Review, Formatwahl, Design). **Claude
Desktop zeigt Karten lokaler Erweiterungen derzeit nicht an** – auch das offizielle MCP-Apps-Beispiel erscheint dort nur als
Text (Gegenprobe Phase 7). Standard ist deshalb der Text-Assistent; der Karten-Code bleibt für Hosts, die MCP Apps
unterstützen.

## So nimmst du für Schnippo auf

**Ordner:** ein Ordner pro Projekt, alle Takes hinein – B-Roll-Clips und Fotos dürfen mit hinein (Clips ohne Sprache
werden als B-Roll erkannt). Skript als `.docx` dazulegen; beim Werbespot gilt ein Storyboard oder eine Shotlist als
Skript. Dateinamen sind egal, Kamera-Timecode hilft.

**Versprecher:** kurz stoppen, deutlich **„nochmal“** sagen (oder einmal in die Hände klatschen) und den **ganzen Satz**
neu beginnen – nicht mitten im Satz weitermachen. Der Satz davor wird dann als „vermutlich verworfen“ markiert (nur ein
Hinweis, Claude entscheidet). Marker-Wörter sind einstellbar (`[analysis] retake_words`, Standard: nochmal, noch mal,
nochmals, noch einmal, Cut, Schnitt, Stopp, von vorne, neu). Ein Marker zählt nur als eigene kurze Äußerung zwischen
Pausen, nicht mitten im Satz.

**Bild:** 1 Sekunde ruhig in die Kamera schauen, bevor du sprichst (ruhiger erster Frame für den Hook). Alle Takes mit
derselben Framerate; B-Roll gern mit doppelter Rate (50p bei 25p), dann ist Zeitlupe möglich.

**Ton:** Ansteckmikro auf einen Kanal, ein zweites Mikro auf den anderen ist in Ordnung – der Server wählt den besseren.
Interview: ein Mikro pro Person auf eigenem Kanal, dann bekommt jeder Satz das Mikro seines Sprechers. Eine
Sicherheitsspur (−6 dB) wird erkannt. Ruhiger Raum, Lüftung/Kühlschrank aus, 2–3 Sekunden Raumton am Anfang.

**Namen:** Lege eine `glossar.txt` in den Ordner, eine Schreibweise pro Zeile, nach `=` bekannte Verhörer:
`MOC AG = Moz AG, CU`, `Raum Inn-Isar`, `support@mondoria.de`.

**Interview:** Fragen deutlich stellen; Vorgespräch und Technik-Absprachen stören nicht, sie werden erkannt und
entfernt. Ob die Fragen im Video bleiben, entscheidet die Fassung (Social-Clip: raus, Langfassung: kurz drin).

## Installation als Erweiterung (.mcpb)

`uv run python packaging/build_mcpb.py` baut `dist/schnippo-<version>.mcpb` (MCP Bundle, `server.type = "uv"`).
Doppelklick → Claude Desktop installiert die Erweiterung und fragt Gladia-Key (Schlüsselbund), Sprache, Format und
optional einen Export-Ordner ab. Beim ersten Start lädt Claude Desktop über uv Python 3.14 und alle Abhängigkeiten
(gemessen: ~1 min bei leerem Cache, danach < 1 s). Kein Terminal, kein Homebrew, kein eigenes Python nötig.
ffmpeg/ffprobe: vorhandenes System-ffmpeg, sonst das PyPI-Paket `portable-ffmpeg-full` (GPL-Build, siehe
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
