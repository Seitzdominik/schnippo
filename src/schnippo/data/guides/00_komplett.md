# Komplett-Schnitt: alles in einem Rutsch

Der Nutzer möchte nicht vier Durchgänge abwarten. Du triffst die Entscheidungen, die sonst über mehrere Runden liefen, in einem Zug und legst am Ende genau eine Timeline und einen kurzen Bericht vor.

## 1. Vorab, einmal und kurz
- Material einlesen (`ingest_folder`, `import_to_resolve=true`), transkribieren (`transcribe`, Kosten nennen; ab 30 min neuem Audio erst nach OK).
- Format und Inhaltstyp stehen im Brief oder in der Erkennung (`get_edit_context` nennt beides). Vorrang: Chat > `brief.md` > Vorliebe > Erkennung.
- Eigennamen: nur bei echten unsicheren Namen fragen, dann `set_glossary`.
- Werbespot oder Szenen ohne Skript: Reihenfolge bestätigen lassen (`show_review`), das ist die einzige inhaltliche Pflichtfrage.
- Kostenschätzung nennen. Mehr fragst du nicht.

## 2. Dann ohne Unterbrechung, intern
Arbeite die Leitfäden der Reihe nach ab, aber baue keine Zwischenstände in Resolve. Du prüfst mit `validate_cutlist` und Kontaktabzügen (`preview_cuts`, `get_frames`). Nach jedem Block ein Satz im Chat, damit der Nutzer sieht, dass es läuft („Rough Cut fertig, Gegenhören läuft …“), bei längeren Stücken mit grober Restzeit.

1. **Rough Cut:** Inhalt, Reihenfolge, Take-Wahl, Laufzeit (Leitfaden 01).
2. **Fine Cut:** Pausen, Wortenden, Kernaussagen als `beats`, `punch_in` (Leitfaden 02).
3. **Gegenhören:** `sense_check(cutlist=…)` hört die geplante Fassung ab, ohne dass etwas in Resolve liegt. Nähte und Sinnfehler direkt in der Cutlist beheben, dann erneut (nur Geändertes kostet).
4. Vor dem Ton einmal `analyze_audio`. **B-Roll und Overlays** (Leitfaden 03), **Zooms**, **Grafiken** (Leitfaden 05), **Sound-Effekte** (Leitfaden 06).
5. **Eine** Cutlist mit allem: `items`, `rejected`, `beats`, `punch_in`, `overlays`, `graphics`, `sfx`, `audio`. Ohne `pass`. `validate_cutlist` muss GÜLTIG sagen.
6. `complete_cut(cutlist, borderline=[…], open_questions=[…])` baut die Timeline, sichert sie, misst den Ton, prüft und gibt den Bericht.

Wünsche pro Auftrag kommen als Satz: „ohne Grafiken“ → `skip=["graphics"]`, „ohne Sound-Effekte“ → `skip=["sfx"]`, „ohne B-Roll“ → `skip=["overlays"]`, „ohne Zooms“ → `skip=["zooms"]`, „ohne Ton-Mastering“ → `skip=["audio"]`, „nur Rohschnitt“ → `skip=["rough"]`.

Kapitel gehören nicht in die Cutlist: Beim Export `export_transcript(timeline=…, chapters=[…])`. Die Abschnitte „Technik“ weiter unten beschreiben auch den Durchgangs-Modus; `build_timeline` und `base_cutlist` brauchst du im Komplett-Schnitt nicht.

Cold Open: Der Satz wandert nach vorn und steht an seiner alten Stelle nicht noch einmal; dort bleibt höchstens ein kurzer Rückbezug.

`ingest_folder` kündigt eine Bestätigung von A- und B-Roll an, wenn der Ordner unsortiert ist. Bei „nur wenn nötig“ und „keine“ entscheidest du selbst und nennst die Einordnung im Bericht.

## Rückfragen
Die Einstellung steht in der ersten Zeile von `get_edit_context`.
- **nur wenn nötig** (Standard): Du fragst nur bei echten Widersprüchen im Material oder fehlender Szenenreihenfolge. Grenzfälle entscheidest du nach Leitfaden und trägst sie in `borderline` ein, mit Zeitstempel im fertigen Schnitt: `{"at": "1:12", "what": "Zweiter Versuch des Satzes zur Dosierung genommen, der erste stockt"}`.
- **keine:** Du fragst gar nicht; was unklar bleibt, steht in `open_questions`.
- **nach jedem Schritt:** Durchgänge wie in den Leitfäden 01 bis 04 mit `pass` und `show_review`. Alle arbeiten auf `<Name>_Schnippo`.

## 3. Danach
Den Bericht aus `complete_cut` weitergeben. Korrekturen laufen direkt auf dieser Timeline, Handänderungen des Nutzers bleiben erhalten:
- Inhalt: `revise` (Stücke raus, rein, kürzer; bei geänderter Reihenfolge baut Schnippo neu und setzt die Handänderungen wieder ein).
- Nur Ton: `master_audio`. Zooms: `apply_zooms`. Nachträglich B-Roll, Grafiken, Effekte: `add_overlays`, `add_graphics`, `add_sfx`.
- Vor jeder Änderung liegt eine Sicherung in `Schnippo/Versionen`. `list_versions` zeigt sie, `restore_version` holt eine zurück.
- Eine zusätzliche Timeline nur, wenn der Nutzer das ausdrücklich will: `new_timeline=true`.
