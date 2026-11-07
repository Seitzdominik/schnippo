# Schnippo – Entwicklerdokumentation

Schnippo ist ein lokaler MCP-Server, der Video in DaVinci Resolve Studio schneidet. Dieses Dokument beschreibt den Aufbau und hält fest, was an der Resolve-Scripting-API gemessen wurde. Die Doku von Blackmagic deckt vieles davon nicht ab oder sagt etwas anderes.

Getestet mit: DaVinci Resolve Studio 21.1.2.10, macOS arm64, ffmpeg 9.0.2, uv 0.13.7, mcp 2.3.0, Python 3.14. Alle Zahlen sind Messwerte aus dieser Umgebung, andere Versionen können abweichen. Testmaterial: synthetische Clips, ein Handy-Take im Hochformat, ein Testinterview (16:9, 4K, zwei Sprecher), ein Kursvideo (1080p, sechs Takes) und ein Werbespot (4K, Sprech-Takes und stumme B-Roll).

## Architektur

### Überblick

- Ablauf: Ordner einlesen → transkribieren → Analyse (Segmente, Retakes, Akustik, Bewegung) → Cutlist (JSON) → `validate_cutlist` → `build_timeline` → Rücklesen und Prüfen.
- Das Modell verweist nur auf IDs, nie auf Timecodes. Flags und Retake-Gruppen sind Hinweise, die Auswahl trifft das Modell.
- Jede Timeline wird nach dem Bau aus Resolve zurückgelesen und gegen die Cutlist geprüft: Position, Dauer, Quell-Offset, Framerate, verlinkter Ton, Marker.
- Paket `schnippo`, Umgebungsvariablen `SCHNIPPO_*`, Konfiguration in `~/.config/schnippo` (`config.toml`, `preferences.json`, `brand.json`), Exporte im Material-Ordner unter `schnippo-export/`.

### Module

- Server und Einrichtung: `server`, `setup_check`, `onboarding`, `prefs`, `config`, `branding`, `errors` (Fehler in Alltagssprache), `guard` (Pfadregeln).
- Material und Transkript: `media`, `transcribe/` (Provider-Schnittstelle), `workspace`, `cache`, `cache_admin`, `glossary`.
- Analyse: `acoustic`, `analysis`, `segments`, `retakes`, `script`, `edges` (Wortkanten), `frames`, `framing`.
- Schnittplanung: `cutlist`, `passes`, `profiles`, `formats`, `snap` (Overlay-Kanten), `markers`, `revise`, `reels`, `reframe`.
- Resolve und Ausgabe: `resolve_bridge`, `fcpxml`, `kenburns`, `render`, `audio`, `delivery`, `export`, `subtitles`, `qc`, `sense` (Sinnprüfung), `jobs`.
- Grafik und Ton: `mg/` (Motion Graphics), `design`, `ui/` (Karten), `sfx`, `sfx_profile`, `sfx_record`, `sfx_sources`.

### Durchgänge

Jeder Durchgang hat genau einen Job und erzeugt eine eigene Timeline. Nichts wird überschrieben.

- Rough (`<Name>_V1_Rough`): Inhalt, Reihenfolge, Take-Wahl. Füllwörter bleiben, nur Löcher > 1,5 s werden auf 0,4 s gekürzt. Nur hier entsteht zusätzlich `_Alternativen`. Fine (`_V2_Fine`): Rhythmus, Punch-ins, Beats. Nimmt die Profilwerte, nicht die Rough-Optionen.
- B-Roll (`_V3_BRoll`): nur Bilder ergänzen. Polish (`_V4_Polish`): Ton, QC, Export-Preset. Motion (`_V5_Motion`): Grafiken auf eigener Spur.
- `passes.resolve` baut die effektive Cutlist aus Anfrage, Basis (gespeicherte Cutlist der Vorgänger-Timeline, `builds` im Workspace) und Profil. Nicht erlaubte Felder ergeben eine Warnung, keinen Fehler.
- Korrekturen: `locate` findet Stellen über `#05`, Zeit oder Zitat. `revise` erzeugt `<Timeline>_r2`, `_r3` usw., `#NN` meint immer die Nummerierung der Basis.
- `read_timeline_changes` vergleicht V1 in Resolve mit der gebauten Cutlist und übernimmt Handänderungen als neue Version. Unklares wird gemeldet, nicht still verworfen.

### IDs

- Wörter `c01:w0001`, nur für ASR-Tokens. Lücken erben die Nummer des vorherigen Wortes (`p0005` Pause, `u0005` Sprache ohne Wort), geänderte Schwellen nummerieren also nie um.
- Segmente `c01:s012`, Frames `c01:f0123` (Quell-Frame auf Resolves Raster), Standbilder `i03`, Teilstücke in Markern `#05 <Satzanfang>`.
- Transkriptformat: Zahl vor jedem Wort = Wort-ID, Zeitstempel nur am Zeilenanfang. Das kostet etwa 1 Token pro Wort statt etwa 3 für `[w0005 00:01.30]`.
- Ein Clip behält sein Transkript, sonst wären Wort-IDs fertiger Cutlists ungültig. Ein neues Glossar gilt deshalb nur für neu transkribierte Clips.

### Caches

- Cache-Key = sha256(Größe + erstes MiB + letztes MiB), ohne mtime. Kopieren auf ein anderes Laufwerk löst keine neue, kostenpflichtige Transkription aus.
- Transkript: `tokens.<provider>.<sprache>.<hash(Modell, Vocabulary)>.json`. Gelesen wird nur die passende Datei, sonst Fehler mit Liste der anderen Varianten.
- Rohantwort in `raw.gladia.*.json`. Ein gestarteter Auftrag steht in `raw….pending` und wird später abgeholt statt neu bezahlt.
- Bewegung in `motion.npy`, Einzelbilder als JPEG 480 px. Ein 17-min-Clip belegt etwa 35 MB, fast alles Ton-Auszug.
- `clear_cache(older_than_days=30)` löscht erst mit `confirm=true`, Transkripte und verwendete Renders nur auf ausdrücklichen Wunsch.

### Auftragsdateien

- `<Cache>/jobs/<id>.json` hält Anfrage (nur gesetzte Felder), erledigte Stufen und Status.
- Die Timeline entsteht als `<Name>_unvollstaendig` und wird erst umbenannt, wenn alle Stufen (Timeline, Overlays, Grafiken, Ton) durch sind.
- `resume_job()`: Ein Auftrag mit Status „läuft“ ohne laufenden Thread gilt als unterbrochen. Er wird neu aufgebaut, weil halbe Zustände in Resolve nicht sicher fortsetzbar sind. Getestet mit hartem `os._exit`: Neuaufbau in 50 s.

### Media Pool und Pfade

- Bins: `Schnippo/<Ordnername>`, `Schnippo/Standbilder`, `Schnippo/Grafiken`. Der Import sucht vorher im ganzen Media Pool, Clips in eigenen Bins werden benutzt, nicht doppelt importiert und nicht verschoben.
- `guard`: Verknüpfungen nach außen werden gemeldet und übersprungen. Geschrieben wird nur in Export-Ordner, Cache und `~/.config/schnippo`.

## Resolve-Anbindung

- `import DaVinciResolveScript` funktioniert mit Homebrew-Python 3.15, uv-Python 3.14 und dem mitgelieferten ResolvePython 3.14.4 (kein `pip`). `fusionscript.so` ist universal, die alte Einschränkung auf 3.10/3.11 gilt nicht mehr.
- `resolve.GetProduct()` existiert nicht, es heißt `GetProductName()`.
- `MediaPool.ImportMedia([{"FilePath": p}])`, laut README die kanonische Form, gibt für Videodateien `None` zurück. Die als deprecated markierte Form `ImportMedia([p, ...])` funktioniert.
- Timelines erscheinen in `Folder.GetClipList()` als Clips mit `Type == "Timeline"`. `MediaPool.AddSubFolder` erlaubt doppelte Namen.
- `GetIsTrackEnabled` ist nur für die aktuelle Timeline verlässlich. Nach `SetTrackEnable("audio", 2, False)` las es trotzdem True.
- `Timeline.ExportFrame(offset, {...})`: `offset` ist 0-basiert ab Timeline-Start, jenseits des Endes kommt `success: False`. Die Untertitelspur wird nicht mitgerendert.

## AppendToTimeline

Messmethode: Synthetische Clips tragen ihre Frame-Nummer als 14-Bit-Streifenmuster im Bild. `ExportFrame` holt den ersten und letzten Frame jedes Items, das Muster wird dekodiert. So sieht man den wirklich liegenden Quellframe, unabhängig von den API-Rückgaben.

- `endFrame` ist exklusiv: `[100:145]` ergibt Dauer 45, sichtbar sind die Quellframes 100…144.
- `startFrame`/`endFrame` sind Quell-Clip-Frames, 0-basiert ab Clip-Anfang, auch bei Clips mit eingebettetem Timecode.
- `recordFrame` ist absolut inklusive Timeline-Start (108000 + n). Ein relativer Wert legt das Item ohne Fehler vor den Timeline-Start.
- `GetStart`, `GetEnd`, `GetDuration`, `GetLeftOffset` und `Timeline.GetEndFrame()` stimmen exakt, Enden sind exklusiv. `GetLeftOffset` ist bei gleicher fps der Quell-Startframe, bei Mischraten in Timeline-Frames.
- `GetSourceStartFrame()` ist unzuverlässig: Bei Drop-Frame-Clips meldet es 99 statt 100, das Bild zeigt korrekt 100.
- Ohne `mediaType` wird nur das Video-Item zurückgegeben. Der Ton landet trotzdem verlinkt auf A1, auch bei `trackIndex=2`.
- `trackIndex` über den vorhandenen Spuren: Ohne `mediaType` wird die V-Spur angelegt. Mit `mediaType` 1 oder 2 schlägt es fehl, vorher `AddTrack("video")` bzw. `AddTrack("audio","stereo")` aufrufen.
- `mediaType` 1 und 2 getrennt: Items sind nicht verlinkt, `Timeline.SetClipsLinked([v,a], True)` funktioniert. Batch: 24 Stücke in einem Aufruf dauern 0,03 s, die Rückgabe folgt der Eingabereihenfolge, 0 Abweichungen.
- Überlappung im Bild wird nicht abgelehnt, sondern still am Kopf getrimmt: `[300:330]@210` über einem Item 200–230 landet als `[320:330]@230`. Platzierung vor bestehende Items ist erlaubt.
- Überlappung auf einer Tonspur: Resolve schiebt den Clip ohne Meldung nach hinten (im Test 17 Frames). Darum verteilt `lanes` Effekte auf `SFX`, `SFX 2` usw.
- Fehlschlag liefert ein Item-Objekt, dessen Methoden `None` zurückgeben, also immer auf `GetStart() is None` prüfen. Float-Frames werden gerundet (10.5 → 11), nur Ints verwenden.
- WAV im Media Pool: `Frames` leer, FPS = Projektrate. Mit `mediaType: 2` ohne start/end liegt die ganze Datei exakt an `recordFrame`. Mit start/end zählen die Werte in der Clip-Rate, nicht in der Timeline-Rate. Darum immer ganze Dateien einfügen.

## Framerate

### Timeline-Rate

- `GetStartFrame()` für 01:00:00:00: 86400 @24, 90000 @25, 108000 @29.97 NDF und @30 (Nominalrate 30).
- Gleiche fps von Clip und Timeline: framegenau.
- Mischraten: start/end bleiben Quellframes, die Timeline-Dauer wird abgerundet, also ±1 Frame pro Schnitt. 25p `[100:150]` in 29.97 → 59 Frames, sichtbar 100…148. 29.97 `[300:360]` in 25 → 50 Frames, sichtbar 300…358. 23.976 `[240:288]` in 25 → 50 Frames, sichtbar 240…286. 23.976 `[48:96]` in 29.97 → 60 Frames, sichtbar 48…95.
- `Timeline.SetSettings({"useCustomSettings":"1","timelineFrameRate":…})` akzeptiert nur ganze Raten (24/25/30/50). `"29.97"`, `"23.976"`, `"59.94"`, `"29.97 DF"` ergeben `False`.
- Bruchraten gehen per Settings nur auf Projektebene (`Project.SetSettings`), und die ist gesperrt, sobald eine Timeline existiert.
- Eine Timeline mit Untertitelspur akzeptiert keine eigene Framerate mehr.

### Wiedergabe-Rate

- Neue Projekte starten mit 24/24. Die API setzt nur `timelineFrameRate`, `timelinePlaybackFrameRate` zieht anders als in der Oberfläche nicht mit. Folge im Test: 1823 Frames laufen 75,96 s statt 60,77 s.
- `timelinePlaybackFrameRate` ist laut pyi read-only. `SetSettings`/`SetSetting` mit "30", "30.0", 30 und "30 fps" ergeben False, vor und nach der ersten Timeline. `videoMonitorFormat` sowie Speichern und Neuladen ändern nichts. Projekt-Presets (`.preset`) sind proprietär binär.
- Timelines mit eigenen Einstellungen melden diesen Schlüssel nicht. Per Hörtest bestätigt: Sie spielen mit ihrer eigenen Rate, unabhängig vom Projekt (30 im 24p-Projekt, 29,97 im 25p-Projekt).
- Die Prüfung darf nie nur `timelineFrameRate` lesen, sondern Projekt-, Timeline-, Wiedergabe- und Clip-FPS sowie Sekunden je Stück gegen die Quelle (±1 Frame).
- `GetCurrentTimecode()` taugt nicht zum Messen der Abspielrate: Der Wert springt beim Start und wird danach nicht zuverlässig aktualisiert.

### Kaskade in `build_timeline`

Timeline-Rate = Resolve-FPS des Hauptmaterials. Alle Wege sind getestet: Timeline-Dauer = `validate_cutlist` = Render-WAV, Ton ±0,06 ms.

1. Projekt-Einstellungen, nur wenn Projekt-Framerate und Projekt-Wiedergabe passen.
2. Eigene Timeline-Einstellungen für ganze Raten: erst `useCustomSettings`, dann `timelineFrameRate`.
3. FCPXML-Import, auch für Bruchraten.
4. Sonst `BuildError` mit Anleitung. Fehlgeschlagene Versuche hinterlassen keine Timelines.

### FCPXML

- `MediaPool.ImportTimelineFromFile` mit `importSourceClips: False` und `sourceClipsFolders`: Resolve übernimmt das Format der Datei (eigene Timeline-Einstellungen, 30 bzw. 29,97 fps). Clips landen framegenau, der Quell-Timecode wird korrekt umgerechnet.
- Bild und Ton liegen auf V1/A1, sind aber nicht verlinkt.
- Marker aus der Datei kommen nicht mit (nachsetzen per `AddMarker`), `<caption>` wird ignoriert.

### VFR und Handyclips

- Synthetischer VFR-Clip (270 Frames, nominal 30 fps, 12 s real): ffprobe zeigt `r_frame_rate=30/1`, `avg_frame_rate=45/2`. `media.detect_vfr` prüft zusätzlich die Paket-Zeitstempel.
- Resolve meldet FPS 30 und 360 Frames. Es konformiert zeitbasiert: Frame k zeigt das Bild zur Zeit k/30, alle 8 Stichproben exakt.
- Konsequenz: `frame = round(t_sekunden × Resolve-FPS)`, nicht der ffprobe-Index. Der Ingest speichert `resolve_fps` und `resolve_frames` je Clip. Ein Transcode war nicht nötig.
- Edit-Lists: Audio `media_time 960` Samples = 20 ms AAC-Priming. ffmpeg und Resolve wenden es identisch an (Korrelation 1,000, 22/22 Stücke 0,00 ms ±0,06 ms). Wort-Zeitstempel passen 1:1 auf die Timeline.
- Rotation (Display-Matrix 90°) wendet Resolve selbst an. Eine Timecode-Spur wird Start TC, für `startFrame` irrelevant.
- Zeitstempel-Jitter (27 von 6704 Abständen ±1,7 ms, ffprobe-avg 29,998): Resolve meldet FPS 30, Frames = Paketanzahl.

## Bild

### Standbilder und Scaling

- Standbilder: `Frames` = 1. `AppendToTimeline` ignoriert `endFrame`, die Dauer ist immer 150 Frames (5 s), LeftOffset ist unsinnig (108000). Lösung: einzeln in Zeitreihenfolge anhängen und sofort mit `SetRightOffset(aktuell + Überschuss)` trimmen.
- `Scaling = resolve.SCALE_FILL` füllt das Format mittig, das Ergebnis entspricht einem ffmpeg-Cover-Crop (Abweichung 0,4).
- Ohne Fill liegt ein 16:9-Clip im Hochformat eingepasst mit schwarzen Balken. `timelineInputResMismatchBehavior = scaleToCrop` wird angenommen und ignoriert.

### Pan, Tilt, Zoom

- Video in Timeline-Auflösung: 1 px je Einheit. Tilt + heißt nach oben. Unabhängig vom Zoom (gemessen bei 1,12 und 1,3).
- Die Pan-Einheit skaliert mit der angezeigten Breite. Gefülltes Standbild: 1,19–1,2 px je Einheit (25/50/75 → 30/60/90 px).
- 16:9-Clip mit Fill in 9:16: Pan 3,16 px je Einheit, Tilt 1 px, Zoom um die Mitte. 3,16 entspricht rechnerisch (16/9)².
- Keine Keyframes per API. Für bewegte Ausschnitte teilt `reframe` an Wortlücken. In vier Test-Reels gab es 0 Teilungen, das Teilen ist also nur mit Unit-Tests belegt.
- Punch-ins liegen am V1-Item. Stufen: Hauptstufe 120 %, jede dritte 112 % oder 125 %, jede zweite 100 %, Akzent 132 %. Grenze nach Quelle: kurze Seite / 1080, mindestens 125 %, höchstens 200 %.
- Mindeststandzeit je Zoomstufe: YouTube und Kurs 1,5 s, Reel 0,8 s, Werbespot 0,6 s. Ohne sie blitzen kurze Teilstücke auf.

### Fusion, Generatoren, Ken Burns

- Text+-Titel übernehmen statische Werte (Text, Size, Center) zuverlässig.
- `AddFusionComp` mit Transform und `BezierSpline`-Keyframes setzt sich, wirkt aber weder in `ExportFrame` noch im Render. Das gilt auch für statische Werte und nach `LoadFusionCompByName`.
- Generatoren und Titel (auch Adjustment Clips) werden am Playhead mit Ripple eingefügt und haben feste 150 Frames, nicht kürzbar. `SetPosition` auf eine belegte Stelle ripplet. Adjustment Clips lehnen Zoom-Properties ab.
- Dynamic Zoom geht per API, aber fest heraus von 1,24 auf 1,0 (nur an/aus und Ease). `slow_zoom_in`, Schwenks und abweichender Fokus laufen darum über ffmpeg `zoompan` als ProRes 422 (2× Oversampling, etwa 1,3 s je Clip).

### Marker, Übergänge, Untertitel

- `Timeline.AddMarker(frameId, …)`: `frameId` ist relativ zum Timeline-Start. Ein absoluter Wert landet weit hinter dem Ende.
- `TimelineItem.AddTransition({"type": "Cross Fade 0 dB", "category": "audio", "position": "end", "alignment": "center", "duration": 2})` ergibt einen 2-Frame-Übergang zentriert auf dem Schnitt. Video analog (`Cross Dissolve`, `simple`).
- SRT per `ImportMedia` wird ein Element „Subtitle“. `AppendToTimeline` platziert es nicht (`None`). `CreateTimelineFromClips(name, [{mediaPoolItem: srt}])` legt eine Timeline mit Untertitelspur framegenau an (68/68, Timing ±1 Frame).
- Schnippo legt keine Untertitel in Resolve an, sondern exportiert `.srt` und `.txt`.

## Ton

### Kanäle

- `MediaPoolItem.GetAudioMapping()` liefert `{"embedded_audio_channels":2,"track_mapping":{"1":{"channel_idx":[1],"type":"mono"},"2":{"channel_idx":[2],"type":"mono"}}}`. `AppendToTimeline` legt Track 1 auf A1 (stereo) und Track 2 auf A2 (mono). Zwei bit-identische Mono-Spuren liefen so doppelt (+4,7 LU).
- Lösung: pro A1-Item `SetSourceAudioChannelMapping` auf `track_mapping {"1": {channel_idx: [bester], type: mono}}`, dann `DeleteTrack("audio", 2)`. Die V1-Verlinkung bleibt, das Mapping im Media Pool bleibt unverändert.
- Mono-Zuordnung auf Stereo-Spur A1 spielt L und R gleich laut (−16,97 / −16,97 dB RMS). Der Render ist etwa 3 dB lauter als die Mono-Quelle.
- Spur aus reicht nicht: Mit geladenem Render-Preset wurde eine deaktivierte A2 mitgerendert (−23,1 statt −27,7 LUFS).
- `audio.channel_analysis`: Korrelation als Maximum über ±2 ms Versatz, weil 1 ms Laufzeit zwischen zwei Mikros sie sonst drückt. Klassen: identisch (≥ 0,999, < 0,1 dB), unausgewogen (> 3 dB, Korrelation ≥ 0,5), verschieden (< 0,5), stereo.
- Kanalwahl: Unter 1,5 dB Unterschied im Rauschabstand gewinnt der lautere Hauptkanal, sonst springt die Wahl pro Clip. Bei zwei Mikros je Teilstück das tatsächlich lautere, nicht nach Sprechererkennung (Testinterview: 15 dB Unterschied).

### Lautheit

- `AudioVolume` ist die Clip-Lautstärke und wirkt vor Clip-FX. Trifft das Ziel in einem Durchgang (±0,1–0,4 LU). Für Spur- und Bus-Lautstärke gibt es keine API.
- `NormalizeAudioLevel` (Modi u. a. EBU R128, ITU-R BS.1770-4, YouTube): „relative“ hebt den lautesten Clip, nicht das Programm (−20,5 statt −14 LUFS).
- `AddEffect("audio", Limiter)` funktioniert. Effekt-Parameter sind per API nicht setzbar, das Standard-Ceiling liegt bei etwa −0,2 dBTP. Dialogue Leveler (Item-Property) senkt LRA von 7,6 auf 4,6.
- Lösung für True Peak: Limiter → Multiband Compressor, beide mit Standardwerten. Der Kompressor senkt den Pegel hinter der Ceiling. Ergebnis −14,5 LUFS / −2,8 dBTP mit +19,7 dB Clip-Gain in einem Durchgang.
- Preis dieser Kette: Pausen und Raumton relativ zur Sprache etwa +5 dB, Höhen > 5 kHz +3–5 dB, < 125 Hz +3–4 dB. `audio.tp_strategy: "limiter_only"` ergibt −0,2 dBTP.
- Andere Ketten: Limiter + Gain oder + Soft Clipper −0,2 dBTP, Soft Clipper allein +0,3, Multiband Compressor allein +0,5, Limiter + AUDynamicsProcessor erreicht −14 nicht (−17,0 LUFS bei +28 dB).
- Blenden müssen „Cross Fade 0 dB“ sein. Mit „+3 dB“ addieren sich zwei begrenzte Clips an den Schnitten, True Peak −0,7 statt −2,8 dBTP.
- Render-Normalisierung wirkt ebenfalls vor den Clip-FX: Timeline −11,2 LUFS / +0,1 dBTP mit gefahrenem Limiter ergibt −14,0 LUFS / −0,3 dBTP, nicht −2,7. Für True Peak nutzlos.
- Export-Ergebnisse (LUFS / dBTP): Testinterview −14,5 / −2,6, Kursvideo −14,4 / −2,4, Werbespot −13,6 / −3,3.
- Beispielquelle Handy-Take: −31,0 LUFS, −2,9 dBTP, LRA 13,5, Rauschboden −79 dBFS, Rumpeln −5,2 dB, Boxy +0,4 dB, Zischlaute −11,3 dB gegen LTASS. Kein EQ, Hochpass oder De-Esser begründet. Atmo wird gemessen eingepegelt (Ziel −20 LU unter Programm). Eine Windspur lag roh bei −14,8 LUFS.

## Rendern

- Rendern ist seit 21.1.1 nicht blockierend. `IsRenderingInProgress()` ist direkt nach `StartRendering` noch `False`, also `GetRenderJobStatus(job)` pollen.
- Render direkt nach einem Bau startet teils nicht (`StartRendering` → False, auch nach 10 Versuchen, oder Job bleibt auf „Ready“). Ein zweiter Anlauf geht.
- Audio-only-Renders startet Resolve gar nicht. Darum immer Bild + Ton, für Messungen ProRes Proxy + PCM in 640 px Breite, danach Auflösung zurücksetzen und Datei löschen.
- Nach einem Render mit `ExportVideo: False` rendert Resolve trotz `ExportVideo: True` weiter nur Ton. `{ExportVideo: True, ExportAudio: False}` vorab setzen löst das.
- Relativer `TargetDir`: modaler Dialog „Pfad nicht gültig“, danach liefert die API `None`. Das wirkt wie „Resolve reagiert nicht“. Immer absolute Pfade.
- Render-Format `unknown`: `AddRenderJob` gibt `''` zurück, Format also explizit setzen. Hängende Alt-Aufträge nach einem Absturz vorher löschen.
- Prüf-Render in 4K-ProRes: 9,6 GB je Render, bei 640 px Spitze etwa 1,6 GB. Die Zeit geht ins Decodieren der 4K-Quellen (Polish-Build für 11 min: etwa 5 min). Ohne Aufräumen sammelten sich in Testläufen rund 148 GB an.

### Render-Presets

- `SetRenderSettings` kennt keinen Normalisierungs-Schlüssel, die Script-Schlüsselliste im Binary endet bei `DataBurnIn`.
- Weg über ein Preset: `SaveAsNewRenderPreset` → `ExportRenderPreset` (XML, 21.1.2 legt einen Ordner an) → Felder in `<FieldsBlob>` setzen (Hex eines Qt-QDataStream-QVariantMap) → `ImportRenderPreset` → `LoadRenderPreset`.
- Felder aus dem Binary: `RecordNormalizeAudio`, `RecordAudioNormalizationMethod` (0–2), `…Mode` (0/1 = Peak mit `…TargetLevel`, 2 = Lautheit mit `…TargetLoudness`). Standardwerte werden beim Import verworfen.
- Mode 2, Ziel −16: Render −16,0 LUFS. Mode 1 + TargetLevel −1: keine Wirkung. Gespeicherte Presets übernehmen den Render-Zustand des Projekts, auch eine Normalisierung. Eigene Presets setzen `RecordNormalizeAudio` deshalb ausdrücklich auf aus.
- Eigene Presets: „Schnippo Prüfrender“ (ProRes Proxy) und „Schnippo Export Reel/YouTube (H.264)“ (Ziel `schnippo-export/`, Dateiname = Timeline).
- `export_final` lehnt ein falsches Seitenverhältnis ab und prüft Codec, Größe, Dauer ±0,1 s, LUFS und True Peak. 11 min in 4K: 4:43 min, 3,9 GB (etwa 47 Mbit/s).

## Abstürze und ihre Auslöser

Auswertung über `logs/LogArchive/ResolveDebug_C*.txt` im Resolve-Protokollordner. Nach einem Absturz zuerst das Protokoll lesen und das Projekt prüfen, nicht einfach wiederholen.

- SRT-Element per `AppendToTimeline` mit startFrame/endFrame: Resolve stürzte ab. Diesen Aufruf nicht verwenden.
- `RecordAudioNormalizationMethod` = 3 im Preset: zweimal Absturz. Der Wert wird nie geschrieben.
- Bau in einem unbenannten Projekt: Nach dem Aufwachen des Macs stand Resolve ohne Projekt da, beim ersten Skript-Zugriff entstand „Untitled Project <Zeit>“. Beim Render-Preset endete es mit `Assertion failed: (pCurProject->GetUseProjectTimelineFilter()) … UiDeliverPanelTimelineController.cpp:355`. `build_timeline` verweigert jetzt unbenannte Projekte.
- Timeline löschen, während Resolve auf der Deliver-Seite steht: Absturz in `UiTimelineListContextMenuActionMediator`. Jeder Bau wechselt zuerst auf die Edit-Seite.
- `std::out_of_range: vector`, Stack `UiMpController::*(bool)` aus einem Skript-Aufruf (`Fusion::HandleUIEX`), also ein Media-Pool-Befehl: viermal in oder direkt nach der Overlay-Stufe, beim Import oder Einfügen einer Grafik bzw. eines Standbilds. Ursache offen.
  - Widerlegt: `DeleteClips` zuvor in derselben Sitzung, zu schnelles Umschalten der Timeline, Grafik ab Frame 0, Zeitlupe, Atmo-Spur.
  - Verdacht, nicht bewiesen: erster `ImportMedia`, nachdem schon ein Overlay auf der Timeline liegt. Seitdem wird alles vor dem ersten Timeline-Item importiert.

## Gladia

- Ablauf: `POST /v2/upload` (multipart `audio`, Header `x-gladia-key`) → `POST /v2/pre-recorded` → Poll `GET /v2/pre-recorded/{id}` (`queued|processing|done|error`).
- Wörter unter `result.transcription.utterances[].words[]` mit `word` (führendes Leerzeichen), `start`, `end`, `confidence`. Kosten in `result.metadata.billing_time`.
- `solaria-3`: nur EN/FR/DE/ES/IT, eine Sprache. Preisannahme im Code: 0,61 USD je Stunde Audio.
- Key-Prüfung ohne Kosten: `GET /v2/pre-recorded?limit=1`, 200 gültig, 401/403 abgelehnt.
- Job-POST nie automatisch wiederholen, Gladia dedupliziert nicht und jeder POST kostet. Upload und Poll mit Backoff bei 429/5xx, Poll-Timeout 900 s. Paid-Plan 25 parallele Jobs, Free 3, Schnippo nutzt 3.
- Dauer: Gladia-Verarbeitung 1,6–9 s, fast konstant. Schätzmodell: 6 s + 0,018 s je Audiosekunde pro Clip. Ab 30 min neuem Audio (`[gladia] confirm_over_min`) startet es erst mit `transcribe(confirm=true)`.
- Füllwörter: `solaria-3` lieferte 0, mit und ohne Vokabular. Eine Verbatim-Option ist nicht dokumentiert, der akustische Lücken-Fallback ist die einzige Quelle. Wiederholungen und Neuanfänge bleiben erhalten, Satz-Retakes werden nicht geglättet.
- Custom Vocabulary mit Füllwörtern schadet: keine Füllwörter, dafür ein geändertes Inhaltswort und verschobene Wort-IDs.
- Custom Vocabulary mit Eigennamen nützt: 8 von 274 Wörtern anders, kein Schaden an Inhaltswörtern, ein Eigenname in 3 von 3 Takes richtig. Einträge ohne Zusatzwörter schreiben, Adressen erkennt es nicht.
- Zeitstempel liegen auf dem stimmhaften Teil. Atmer und Plosiv-Ansätze liegen 30–90 ms davor, Atmer bis 300 ms. In klarer Sprache ±30–60 ms (1–2 Frames @30).
- Ausreißer: Gedehnte Wortenden werden abgeschnitten, ein Wort enthielt 1,88 s Stille im Zeitstempel. Schnittpunkte brauchen Padding und Snapping an echte Stille.
- Konfidenz ist kein Qualitätssignal: 132 von 332 Wörtern lagen unter 0,5, gerade in akustisch sauberen Sätzen. Atmo ergibt Halluzinationen mit Konfidenz 0,04–0,14, echte Sprache ≥ 0,35. Regel für B-Roll: 0 Wörter oder Ø-Konfidenz < 0,25.
- Unsichere Eigennamen: Großschreibung sagt im Deutschen wenig. Signale sind schwankende Schreibweise und sehr niedrige Konfidenz im Satz. Daraus wird nur eine Rückfrage-Liste (höchstens 8 Einträge).

## Akustik und Schnittpunkte

- `acoustic`: RMS-Hüllkurve 10 ms, Rauschboden = p10, Schwelle = Boden + 25 dB (geklemmt −60…−30 dB), Stimmhaftigkeit = Autokorrelationsmaximum 75–400 Hz im 40-ms-Fenster. Eine feste Schwelle `max(−35, Mittel−18)` versagt bei leisen Aufnahmen: 48 % der Frames in Wörtern galten als Stille.
- Lückenklassen: `voiced` (≥ 0,15 s, ≥ 60 % stimmhaft) = `{?}`, `breath`, `click` verworfen.
- Hauptbefund: 90 von 143 `{?}` hingen ohne Lücke und Pegeldelle am Wort (0,2–0,35 s). Das sind gedehnte Wortenden. Laute bis 0,28 s gehören jetzt zum Wort, längere bleiben Füllwort, das Wort behält 100 ms.
- `edges`: Ausklang bis Rauschboden + 6 dB (max. 350/200 ms, 20 ms vor dem nächsten Wort), Einsatz bis 120 ms zurück, Kantenprüfung der letzten/ersten 10 ms (Rauschboden + 12 dB). Rest = „harte Kante“ in `validate_cutlist` und `run_qc`.
- Falle: Wortenden „über Stille“ zu kürzen schnitt bei leiser Aufnahme (−32 LUFS) in echten Ton. 46 von 63 Grenzen lagen in hörbaren Silben, zusammen fast 18 s. Für den Schnitt werden sie am Signal wiederhergestellt.
- Die Kantensuche darf nur bis zum echten Ausklang oder Einsatz gehen, nicht bis zur Gladia-Wortgrenze. Ein Schnitt, der unter 0,25 s Stille spart, unterbleibt.
- Maßgeblich ist das Gegenhören: `sense_check` (Prüf-Render → 16-kHz-Ton → Gladia) fand diese Ursachen, die Kantenmessung nicht. Ähnlichkeit ≥ 0,72 gilt als gleiches Wort, geprüft wird ±2 Wörter um jeden Schnitt.
- Restpause am Satzende: Reel 150, YouTube 350, Kurs 400 ms. Beats lassen das Original bis zur Zielpause stehen (key 400–900 ms, section 1000–1100 ms), nie künstliche Stille.
- Segmente an Pausen ≥ 0,7 s oder Satzzeichen. Retakes: LCS der normalisierten Wörter ≥ 3 und ≥ 0,5 der kürzeren Länge, Fenster 90 s. Ohne Skript Recall 0,85 / Precision 0,92 (13 bekannte Beziehungen), ein reiner n-Gramm-Detektor fand 3 von 13.
- Harte Füllwörter Deutsch nur äh/ähm/öh/hm-Varianten. „um“, „eh“, „em“ sind im Deutschen echte Wörter.
- Bewegung: mittlere Luma-Differenz auf 64 px Breite. Schnitt nur verschieben, wenn die Frames > 4 × Median liegen, dann nächster Frame ≤ 2,5 × Median, `max_motion_shift_ms` 200.
- Gesicht: OpenCV-Haar (opencv 4.x, 5.0 hat die Kaskaden entfernt), etwa 27 s für 3:43. Aussetzer bis 12 Frames überbrücken, sonst falsche Warnungen im Dreiviertelprofil (733 Aussetzer, Median 2 Frames).
- Klatscher: Sprung ≥ 25 dB über dem Median der halben Sekunde davor, Spitze ≥ −24 dBFS, ≤ 60 ms laut, nicht stimmhaft. 0 Fehlalarme in 30 Clips, echte Treffer nur synthetisch belegt.

## ffmpeg

- Frame-Extraktion: `-ss t -i` mit t = idx/fps liefert in 5/5 Stichproben denselben Frame wie `select=eq(n,…)` und damit wie Resolve, etwa 0,1 s je Frame.
- Das gebündelte ffmpeg hat kein `drawtext`, Kontaktabzüge laufen über Pillow.
- Mitgeliefert: `portable-ffmpeg-full==0.5.0`, das einzige PyPI-Paket mit nativen arm64/x86_64-Wheels, die ffmpeg und ffprobe enthalten. Reihenfolge: System → mitgeliefert, `SCHNIPPO_FFMPEG=bundled` erzwingt es.
- Falle: `get_ffmpeg()` druckt beim ersten Entpacken nach stdout und zerstört den MCP-stdio-Kanal. Auf stderr umleiten.
- ProRes 4444 mit Alpha: `prores_ks` Profil 4, `yuva444p10le`, `alpha_bits 16`, BT.709.
- Identische Spuren erkennen: ffmpeg-Differenz < −80 dB. Fallback für driftende VFR-Clips: CFR-Mezzanine mit `-fps_mode cfr -r <nominal>`, bisher nicht nötig.

## Motion Graphics

- Nur freie Lizenzen: Playwright (Apache-2.0), Chromium Headless Shell (BSD), Web Animations API, Schriften OFL als WOFF2.
- Seek-Vertrag: `__seek(t)`, `__duration_ms`, `__ready`, pro Frame `t = n·1000/fps`, vorher `document.fonts.ready`. Screenshot mit `omit_background`, Netzwerk gesperrt. Gleiches t ergibt bitgleiche PNGs.
- Alpha: Resolve 21.1.2 liest ProRes 4444 als Straight. Kantentest: Abweichung zum Straight-Modell 2,3/2,7 Grauwerte, zum Premultiplied-Modell 9,4/9,5.
- WAAPI-Falle: Ausgänge mit `fill: both` setzen ihren ersten Keyframe schon während der Verzögerung und überdecken den Eingang. Ausgänge brauchen `fill: forwards`.
- Clip-Path-Ausgang mit `round` lässt einen Rest stehen, die letzten 25 % zusätzlich ausblenden. SVG-Linie mit `non-scaling-stroke` und `pathLength` zerfällt in Striche, Unterstreichung als Balken mit `scaleX`.
- `padding` in em auf einer Box ohne eigene Schriftgröße bezieht sich auf 16 px. Die Box braucht immer eine Schriftgröße, dann skaliert alles einschließlich Eckenradius.
- Abstände zählen an sichtbaren Pixeln (Alpha-Bounding-Box). Mindestabstand `layout.head_clearance_px` = 48 (bei 1080 Breite), Mindestgröße `type.reel.min_cap_height_px` = 48.
- Kopfbox aus der Haar-Gesichtsbox: oben +0,6 h, seitlich je +0,25 w, unten +0,05 h, mit dem Punch-in transformiert. Für den Reframe-Ausschnitt ist das zu groß, darum eigener Wert `reframe.HEAD`.
- Platzierung: über dem Kopf → ohne Zusatzzeile → verkleinert → neben dem Kopf (≥ 300 px) → unter dem Kinn → weglassen und melden. Overlay-Kanten (`snap`): Standbilder Schwelle 0,6 s, Grafiken 0,34 s, keine Splitter < 0,5 s an Schnitten.
- Renderzeit 1080×1920 @ 30 fps: 0,5–1,1 s pro Sekunde Grafik + 0,4 s Encoding, Browser-Start etwa 1,5 s. Nachinstallation 63,5 s: Playwright 140 MB per `uv pip install --target` nach `<Cache>/motion-lib` (übersteht den uv-Abgleich der Erweiterung), Chromium 216 MB nach `<Cache>/playwright`. Ein leeres `PLAYWRIGHT_BROWSERS_PATH` lädt in den Standardordner.

## Sound-Effekte

- Synthese: Rauschen im Frequenzbereich mit wanderndem Gaußband formen (kein Filterklingeln, kein Pfeifen), Schlagklänge als gedämpfte Teiltöne mit weichem Einsatz, feste Seeds.
- Format: 48 kHz/24 Bit stereo, Spitze −3 dBFS, True Peak höchstens −2,2 dBTP, Anfang und Ende auf null. Tieftöne brauchen die Oktave darüber, sonst sind sie auf Handy-Lautsprechern unhörbar.
- Metadaten: `hit_offset_ms`, `audible_ms` (bis −30 dB unter der Spitze), `peak_rms_db` (lauteste 100 ms, daran hängt der Pegel).
- Warum Synthese künstlich klang, gemessen gegen Referenzaufnahmen: Whooshes lagen bei rund 1600 Hz, Referenzen A-bewertet bei rund 560 Hz mit dem Großteil der Energie unter 250 Hz. Dings lagen bei 660–1175 Hz mit 0,3 s, Referenzen bei 2,6–3 kHz mit 1–2 s Nachhall. Impacts waren halb so lang, schmal und ohne Hall.
- Messfallen: Leistungs-Schwerpunkte zeigen bei Whooshes nur den Subbass, darum A-bewertet. Ein Klick am Dateianfang verschwindet unter dem STFT-Fenster, darum polstern. Unter 10 ms sagt eine Hüllkurve mit 5-ms-Schritten nichts. Bei Ticken und Tippen sehen die nächsten Anschläge wie Nachhall aus.
- Transient: Bei Schlägen zählt der Einsatz, nicht die lauteste Stelle, sonst liegt ein Impact 200 ms vor dem Bild. Bei `riser_impact` markiert die kurze Lücke davor die Stelle.
- Aufnahmen (CC0, Lizenz je Datei geprüft): Eine gegenphasige Aufnahme (L/R-Korrelation −0,2) löscht sich in der Mono-Summe teilweise aus, darum nur ein Kanal auf beide Seiten. Loops auf ganze Sekunden strecken.
- Effekt-Kopien tragen einen Inhalts-Hash im Namen, sonst ändert eine neue Bibliothek den Klang fertiger Timelines. Betten werden als eigene Kopie auf Länge geschnitten oder überblendet geloopt.
- Pegel: Clip-Lautstärke = Stimme + Abstand − `peak_rms_db`. Effekte liegen außerhalb von Limiter und Programm-Verstärkung, die Erkennung „identische Tonspur“ darf SFX-Spuren nicht mitzählen.
- Nulltest: Kopie mit und ohne Effekte rendern und abziehen. Transient 0 bis −23 ms zum Plan (ein Frame sind 33–40 ms), Pegel −19,5 bis −21,7 dB zur Stimme bei Soll −20/−22, außerhalb der Effekte −138 dBFS. Lautheit und True Peak unverändert.
- Quellen laut Doku, nicht live getestet: Freesound liefert Suche und Vorschau mit Token (MP3 128 kBit/s), Original nur mit OAuth2. ElevenLabs `POST /v1/sound-generation`, 0,5–30 s.

## Paket und MCP

- `mcp` 2.x: `FastMCP` heißt `MCPServer` (`mcp.server.mcpserver`). Erwartete Fehler als `ToolError` durchreichen, sonst zeigt das SDK nur „Error executing tool“. Bilder über `mcp.server.mcpserver.utilities.types.Image`.
- Tool-Parameter `pass` ist ein Python-Schlüsselwort: Alias im Schema, der Wrapper übersetzt auf `pass_name`. Ohne UTF-8-Locale (Start aus Claude Desktop) scheitert das Lesen von Umlauten, darum überall `encoding="utf-8"`.
- MCPB 0.4, `server.type = "uv"`, Start über `uv run --directory ${__dirname} --frozen --no-dev bundle_main.py`. `mcp_config` ist trotz Doku Pflicht, `mcpb init` schreibt noch 0.3 und bietet „uv“ nicht an. Erster Start 59 s bis `initialize` (Python 3.14 + Abhängigkeiten), Warmstart 0,4–0,5 s.
- Mit lauter optionalen Feldern zeigt Claude Desktop beim Installieren keinen Einstellungsdialog, der Gladia-Key ist darum Pflichtfeld. Unbelegte optionale Felder kommen evtl. als leerer String oder wörtlich `${user_config.x}`.
- Die Erweiterung schickt ihre Einstellungen immer als Umgebungsvariablen, auch unberührte Standardwerte. Darum gewinnt die Onboarding-Antwort, außer der Wert weicht vom Standard ab.
- MCP Apps: Tool-`_meta` `ui.resourceUri` (+ veraltetes `ui/resourceUri`), Ressource `ui://schnippo/card.html` mit `text/html;profile=mcp-app`, Ergebnis = Text + `structuredContent`. Im getesteten Stand fordert Claude Desktop die Ressource bei lokalen Erweiterungen nicht an, auch nicht beim offiziellen Beispiel `qr-server`. Der Text-Assistent ist deshalb Standard.
- Kontext-Token: Interview mit 245 Segmenten: Übersicht etwa 620, Seiten zu 60 Segmenten 2 100–2 400, alles etwa 9 200. Kontaktabzüge etwa B·H/750 Token.

## Offene Punkte

- Skriptmodus ist nur mit synthetischen Tests geprüft. Nicht abgedeckt: ≥ 30 min Rohmaterial, zweite Kamera mit Ton, sehr leise Aufnahmen. Akustik-Schwellen wurden auf wenigen Projekten kalibriert.
- Zwei Personen in einem Bild: `reframe.speaker_x` ist nur logisch geprüft, `stacked` ist nicht gebaut.
- Szenen ohne Sprache stehen nur als Overlays oder im Nachlauf (`tail`), ein Item ganz ohne Wörter gibt es nicht.
- Die Ursache von `std::out_of_range: vector` ist offen.
