# Technik: Tools und Cutlist pro Durchgang

**Aufnahmetipp (für den Nutzer):** 1 Sekunde ruhig in die Kamera schauen, bevor du sprichst – dann gibt es einen ruhigen
ersten Frame für den Hook.

Ergänzt die vier Leitfäden um die Bedienung des Servers. `get_edit_context(pass=…)` hängt den Abschnitt „Alle Durchgänge“
und den Abschnitt des aktuellen Durchgangs an.

## Alle Durchgänge
- Material nur über IDs referenzieren: Wörter `c01:w0120`, Segmente `c01:s012`, Gruppen `c01:G03`, Frames `c01:f0114`,
  Standbilder `i03`. Nie Timecodes ausrechnen.
- Flags (Füllwort, Pause, Wiederholung, Neuanfang) und Retake-Gruppen sind Hinweise des Servers, keine Entscheidungen.
- Jede Cutlist hat `name` (Projektname, z. B. `"Schlaf_Reel"`). Die Timeline heißt `<name>_Schnippo`. Baut Schnippo sie erneut, liegt der alte Stand als Sicherung in `Schnippo/Versionen` und die Handänderungen werden wieder eingesetzt. Eine zusätzliche Timeline nur mit `"new_timeline": true`, wenn der Nutzer das ausdrücklich verlangt.
- Timelines, die Schnippo nicht gebaut hat, werden nie ersetzt.
- `pass` nur im Durchgangs-Modus (Rückfragen „nach jedem Schritt“).
- Ab dem Fine Cut `"base_cutlist": "<name>_Schnippo"` angeben. Der Server übernimmt alles daraus und
  wendet nur die Felder an, die der aktuelle Durchgang ändern darf; andere Felder werden mit Warnung ignoriert.
- Immer erst `validate_cutlist`, dann `build_timeline`.
- Bilder (Kontaktabzüge, ≈ 500–1 200 Token) nur bei Bedarf anfordern, nicht zur Kontrolle jedes Segments.
- Erkennungsfehler im Text mit `set_word_text` (dauerhaft) oder `corrections` in der Cutlist korrigieren, nicht umformulieren.

## rough
- Items: ganze Sätze von erstem bis letztem Wort (`clip`, `from_word`, `to_word`, `note` mit Begründung).
  Ein Satz über zwei Segmente ist **ein** Item. Verworfene Segmente in `rejected` mit Grund (füllt `_Alternativen`).
- Hook: im ersten Item `start_frame` setzen (`get_frames("c01:s001", "interval", interval_s=0.1, pad_s=1.0)` zeigt die
  Frames vor dem ersten Wort). Der Server lehnt Frames ab, die das erste Wort anschneiden.
- Knappe Take-Wahl: `get_take_frames("c01:G03")`.
- Der Server schneidet im Rough Cut nur an den Item-Grenzen; Pausen und Füller innerhalb der Items bleiben (nur Löcher
  über `rough_max_gap_ms` werden gekürzt). `validate_cutlist` zeigt zusätzlich die Laufzeit-Schätzung nach dem Fine Cut.
- Erlaubt: `items`, `rejected`, `corrections`, `markers`, `alternates`. Ignoriert: Zoom, `punch_in`, `overlays`, `audio`.
```json
{"name": "Schlaf_Reel", "pass": "rough", "alternates": true,
 "items": [{"clip": "c01", "from_word": "w0001", "to_word": "w0008", "start_frame": "c01:f0114", "note": "Hook"}],
 "rejected": [{"segment": "c01:s002", "reason": "erster Versuch, ersetzt durch s003"}]}
```

## fine
- Pausen und Füller schneidet der Server nach dem Profil (Restpause, Lückengrenze, Füller raus); überschreibbar in `options`
  (`keep_pause_ms`, `tighten_gaps_over_ms`, `cut_fillers`).
- Bewusste Pause nach einer Kernaussage/vor einer Pointe: am Item `"pause_after_ms": 500` (Reel 400–600, YouTube 500–1000).
- `validate_cutlist` markiert unruhige Schnitte (⚠) → `preview_cuts(cutlist)` ansehen → Grenzen per `start_frame`/`end_frame`
  oder anderem Start-/Endwort korrigieren. Die Bewegungsregel verschiebt Schnitte selbst höchstens 200 ms.
- Punch-ins: `"punch_in": {"mode": "alternate"}` (Skala aus dem Profil, 112–120 %); Akzent pro Item `"zoom": 1.3`.
  Wann gewechselt wird, hängt vom Stil ab (`ruhig`: nur an Satzanfängen; `dicht`: an jedem Jump-Cut).
- Änderungen an `items` sind erlaubt, werden aber als Take-/Inhaltsänderung gegenüber dem Rough Cut gemeldet.
```json
{"name": "Schlaf_Reel", "pass": "fine", "base_cutlist": "Schlaf_Reel_Schnippo",
 "punch_in": {"mode": "alternate"}, "item_changes": [{"index": 12, "zoom": 1.3, "pause_after_ms": 500}]}
```
`item_changes` ändert einzelne Items der Basis (1-basiert) ohne die ganze Liste zu wiederholen
(`start_frame`, `end_frame`, `zoom`, `pause_after_ms`, `note`).

## broll
- `get_frames("stills")` zeigt alle Standbilder. Overlay über einen Wortbereich, den man ohne Gesicht versteht:
  `{"media": "i03", "from_word": "c01:w0250", "to_word": "c01:w0255", "focus": "center", "motion": "slow_zoom_in"}`.
- `motion`: `none` | `slow_zoom_in` | `slow_zoom_out` | `pan_left` | `pan_right`; `focus`: wichtiger Bildteil.
- `validate_cutlist` warnt bei Overlays über dem Hook (erste Sekunden), unter der Mindestdauer oder über dem letzten Satz.
- Erlaubt: `overlays`, `corrections`. Schnitt, Zoom und Optionen kommen unverändert aus der Basis.

**Sound-Effekte:** `list_sfx` zeigt die Bibliothek. `"sfx": [{"category": "swish", "at": "O1", "note": "…"}, {"category": "tick", "at": "G2", "event": "end"}, {"category": "impact_soft", "at": "c01:w0123"}]`. `at` ist eine Grafik (`G1`), ein Overlay (`O1`) oder ein Wort. Der Server richtet den Transient aus: Grafik auf die Box, `event: "end"` auf den Endwert des Zählers, Overlay auf den Bildwechsel. Riser enden auf dem Ereignis, Atmo, Ticken und Tippen beginnen darauf und laufen so lange wie das Element oder `duration_ms`. Intensität und Pegel leitet er aus Modus und Designsprache ab; `gain_db` nur setzen, wenn es begründet ist. `deliberate: true` erlaubt Hook-Satz und CTA. Ein `sfx` im Motion-Durchgang ersetzt die Liste aus dem B-Roll-Durchgang. Nachträglich: `revise` mit `add_sfx` und `remove_sfx`. Ob ein Moment ernst oder emotional ist, prüft kein Automat: das entscheidest du beim Setzen.

## polish
- Zuerst `analyze_audio`, dann `"audio": {"target_lufs": -14}`. EQ/De-Esser nur, wenn die Messung es begründet
  (`"deesser": "auto"`). Der Server legt ein Export-Preset mit Lautheits-Normalisierung an (True Peak ≤ −1 dBTP).
- Nach `build_timeline`: `run_qc(timeline)` und `export_transcript(timeline=…)` (SRT, TXT, bei YouTube Kapitel).
- Schnittänderungen nur, wenn die QC einen Fehler findet (`item_changes` mit `note: "QC: …"`).
```json
{"name": "Schlaf_Reel", "pass": "polish", "base_cutlist": "Schlaf_Reel_Schnippo", "audio": {"target_lufs": -14}}
```

## motion
- Optionaler Durchgang 5, Basis: die Polish-Timeline. Schnitt, B-Roll und Ton bleiben; nur `graphics` (und `brand`).
- Stellen auswählen (Zahl, Liste, Schlüsselbegriff, Hook-Text) und dem Nutzer kurz vorschlagen; Reel 1–3 Grafiken.
- Templates: `hook_text {text}` · `callout {text, label?, underline?}` · `counter {from, to, suffix, label?}` ·
  `list_steps {title?, items[2–4]}` · `lower_third {name, role}` (16:9) · `underline_arrow {from, to, kind}`.
  Position, Größe, Farben, Schrift und Bewegung kommen aus den Tokens/der Marke – nicht selbst festlegen.
- Zeitraum über Wörter (`from_word`/`to_word`) oder `duration_ms`; zu kurze Bereiche verlängert der Server auf
  Eingang + Haltezeit (≥ 1,5 s, Listen ≥ 3 s) + Ausgang. `expressive: true` höchstens für 1–2 Schlüsselmomente.
- **Erst `preview_graphic(cutlist)` ansehen** (6 Standbilder über dem echten Frame + Prüfungen), dann `build_timeline`.
- Marke: `"brand": "<Profil>"`; ohne Angabe das aktive Profil (Design einrichten: `setup_design`).
```json
{"name": "Schlaf_Reel", "pass": "motion", "base_cutlist": "Schlaf_Reel_Schnippo",
 "graphics": [{"template": "counter", "params": {"from": 0, "to": 90, "suffix": "Tage"}, "from_word": "c01:w0078",
               "to_word": "c01:w0083", "note": "Kernzahl"}]}
```

**Sound-Effekte:** `list_sfx` zeigt die Bibliothek. `"sfx": [{"category": "swish", "at": "O1", "note": "…"}, {"category": "tick", "at": "G2", "event": "end"}, {"category": "impact_soft", "at": "c01:w0123"}]`. `at` ist eine Grafik (`G1`), ein Overlay (`O1`) oder ein Wort. Der Server richtet den Transient aus: Grafik auf die Box, `event: "end"` auf den Endwert des Zählers, Overlay auf den Bildwechsel. Riser enden auf dem Ereignis, Atmo, Ticken und Tippen beginnen darauf und laufen so lange wie das Element oder `duration_ms`. Intensität und Pegel leitet er aus Modus und Designsprache ab; `gain_db` nur setzen, wenn es begründet ist. `deliberate: true` erlaubt Hook-Satz und CTA. Ein `sfx` im Motion-Durchgang ersetzt die Liste aus dem B-Roll-Durchgang. Nachträglich: `revise` mit `add_sfx` und `remove_sfx`. Ob ein Moment ernst oder emotional ist, prüft kein Automat: das entscheidest du beim Setzen.
