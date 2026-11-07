# Durchgang 3: B-Roll und Overlays

**Einziger Job:** Bilder ergänzen, wo sie den Inhalt zeigen oder einen Schnitt kaschieren. Schnitt und Timing aus V2 bleiben.

Kennzeichnung: **[E]** belegt · **[P]** Profi-Praxis · **[V]** Anbieter-Meinung · **[S]** Default/Synthese (konfigurierbar).

## Vorgehen
1. `get_frames(stills)` für Standbilder, `get_frames("broll")` für die Szenen der B-Roll-Clips (Frame-IDs `c05:f0123`).
2. Pro Bild/Clip die passende Textstelle suchen (Regeln unten).
3. Overlays in die Cutlist, `validate_cutlist` prüfen.
4. Bauen als `<Name>_V3_BRoll`.

## Video-B-Roll
- Clips ohne Sprache erkennt der Server als B-Roll (Liste in `get_edit_context`). Falsch erkannt? `set_clip_role`.
- Overlay: `{"media": "c05", "from_frame": "c05:f0120", "to_frame": "c05:f0300", "from_word": …, "to_word": …}`. `from_frame` ist der erste gezeigte Frame; `to_frame` begrenzt, wie weit das Material reicht. Die Länge bestimmen die Wörter (und das Einrasten an Schnitten).
- `from_frame` auf einen ruhigen Beginn der Szene legen (kein Schwenk-Ende, keine Unschärfe); nicht über einen Szenenwechsel im Clip hinaus, außer gewollt.
- Ton der B-Roll ist **stumm** [S]. `"audio": "atmo"` legt ihn leise (−20 dB) auf eine eigene Spur, nur wenn die Atmosphäre etwas erzählt.
- Andere Framerate: ganzzahlige Vielfache (50 → 25 fps) sind framegenau. Andere Raten gehen nur für stumme B-Roll, mit Warnung (±1 Frame).
- Zeitlupe: `"slowmo": true` (oder Cutlist-Option `broll_slowmo: "auto"`) zeigt 50-fps-Material in 25 fps mit 50 % Tempo, nur am Timeline-Clip. Dafür braucht es doppelt so viel Material ab `from_frame`.

## Was passt
- **Wörtlich** [V/P]: Die B-Roll zeigt das genannte Nomen, die Zahl, das Produkt, den Ort. Keine generischen Bilder ohne Bezug zum Satz.
- Eine B-Roll darf **keine Reaktion oder kein Ereignis vortäuschen**, das nicht stattfand [P].
- Kein passendes Material? Dann keine B-Roll. Leere Stellen sind besser als beliebige.

## Wo nicht
- Nicht über den Hook (Reel: erste 2–3 s), nicht über die Kernthese, nicht über emotionale/persönliche Momente, nicht über den CTA [V/E: Gesicht wirkt].

## Timing
- Einsatz auf oder kurz nach dem Schlüsselwort; Rückkehr zum Gesicht an einer Satzgrenze [S].
- Dauer pro Einblendung: Reel 1,5–3 s; YouTube 3–8 s; Kurs 3–8 s; Werbespot 1–3 s [V/S]. Detaillierte Bilder/Grafiken mindestens 3 s [V].
- Häufigkeit Reel: etwa alle 8–15 s eine Einblendung [S]. YouTube-Abdeckung 30–50 % [V, schwach belegt]. Kurs 10–30 %. Werbespot 40–70 %, alle 3–6 s ein neues Bild.
- Interview: B-Roll bevorzugt über Fragen-Schnitte und über längere Antworten, nie über die emotionale Pointe.
- B-Roll bevorzugt dort, wo sie einen Jump-Cut oder Bildfehler kaschiert [P].

## Gestaltung
- Höchstens 1–2 Grafikelemente gleichzeitig neben dem Gesicht [S].
- Höchstens 2–3 Übergangsarten pro Video; Überblendungen nur mit Bedeutung [V/P].
- Standbilder: formatfüllend, langsame Bewegung (Zoom/Schwenk); Richtung an Bildinhalt anpassen (z. B. Straße → hineinzoomen).
