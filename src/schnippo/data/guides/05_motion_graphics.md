# Durchgang 5 (optional): Motion Graphics

**Einziger Job:** Wenige, hochwertige Grafiken, die eine Aussage verstärken. Schnitt, B-Roll und Ton bleiben unverändert.

**Grundhaltung:** Nicht animieren, weil man kann, sondern nur, wenn es der Aussage hilft [P]. **Billig wirkt nicht das Einfache, sondern das Unsystematische** [P]: wechselnde Dauern, Standard-Kurven, mehrere Schriften, Effekte ohne Funktion.

Kennzeichnung: **[E]** belegt · **[P]** Profi-Praxis · **[V]** Anbieter-Meinung · **[S]** Default/Synthese (konfigurierbar). Alle Werte stehen als Tokens in `design_tokens.json`; Grafiken dürfen **nur** diese Tokens verwenden.

## Wann eine Grafik
- Zahl, Liste, Struktur oder Schlüsselbegriff, der beim Zuhören untergeht (z. B. „90 Tage · 2 Phasen").
- Hook-Text: eine Zeile, ≤ 6–8 Wörter, ab Frame 1, weil viele ohne Ton schauen [E: Mosseri, Text im Bild].
- Name/Rolle als Bauchbinde (YouTube).
- **Nicht:** laufende Untertitel (macht die Plattform-App), Deko ohne Inhalt, Emojis.
- Menge: Reel 1–3 Grafiken, YouTube etwa eine pro Abschnitt. Max. 1–2 Grafikelemente gleichzeitig [S].

## Bewegung
- **Eingang bremst ab, Ausgang beschleunigt und ist kürzer** (≈ 60–70 % der Eingangsdauer) [E: IBM Carbon, Material 3]. Niemals lineare Bewegung auf Position oder Skalierung, niemals nur ein Fade ohne Positions- oder Maskenänderung [S].
- Kurven: Eingang `cubic-bezier(0.05, 0.7, 0.1, 1)`, Ausgang `cubic-bezier(0.3, 0, 0.8, 0.15)`, Positionswechsel `cubic-bezier(0.2, 0, 0, 1)` [E].
- Dauern: klein 150–250 ms, groß 400–700 ms; Dauer wächst mit Weg und Größe [E].
- **Expressive Kurven/Längen nur für 1–2 Schlüsselmomente pro Video** [E: Carbon].
- **Masken-Reveal statt Hineinfliegen:** Text gleitet hinter einer unsichtbaren Kante hoch; die Box öffnet sich zuerst, der Text folgt 3–5 Frames später [P: Vox-Analyse].
- Gestaffelt: Wörter 50 ms, Zeilen 100 ms Versatz [S].
- Overshoot nur klein (≤ 5–10 %) und abklingend, nach ≤ 2 Schwingungen in Ruhe, alle Eigenschaften synchron [P]. Kein Bounce-Preset.
- Unterstreichungen und Pfeile werden **zuletzt** gezeichnet [P/V].
- Haltezeit: lang genug zum zweimaligen Lesen, mindestens ~1,5 s für kurze Texte; komplexe Grafiken ≥ 3 s [V/S].

## Typografie und Farbe
- **Eine** Schriftfamilie (fette/halbfette Grotesk der Inter/SF-Klasse), max. 2 Schnitte [V/P/S].
- Eine Akzentfarbe plus Neutraltöne; ein Eckenradius; ein Box-Stil [S].
- Kontrast über Box/Scrim (40–60 % Schwarz) oder Kontur sichern, nicht auf helles Footage hoffen; Ziel ≥ 4,5:1 [P/S].
- **Verboten:** Bevel/WordArt, schwere Schlagschatten, Glows, gemischte Icon-Stile, Pastell-Text, dekorative Schriften, Emojis, Sound-Effekte auf jedem Element [V/S].

## Platzierung (9:16, 1080×1920)
- Sichere Zone: oben ≥ 290 px, unten ≥ 670 px, links ≥ 108 px, rechts ≥ 180 px (Instagram-Buttons) → sichere Box x 108–900, y 290–1340 [E abgeleitet/S].
- **Nie über Mund oder Augen** (Gesichtsposition vom Server). Callouts neben dem Kopf (y ≈ 300–700), Hook-Text oberhalb des Kopfes [S].
- 16:9: seitlich ≥ 96 px, oben/unten ≥ 54 px; Bauchbinde auf der Seite gegenüber der Blickrichtung [S].

## Abstand zum Kopf und sichere Zone (Server prüft) [S]
- **Kopf statt Gesicht:** Die Gesichtserkennung liefert nur das Gesicht; die Kopfbox ist nach oben um 0,6 × Gesichtshöhe
  (Stirn/Haare) und seitlich um je 0,25 × Gesichtsbreite erweitert.
- **Mindestabstand** zwischen den sichtbaren Grafik-Pixeln (inkl. Unterstreichung) und der Kopfbox: **≥ 48 px** bei 1080 px
  Breite (`layout.head_clearance_px`). Nie Berührung oder Überdeckung.
- **Über die ganze Dauer:** Kopfposition alle 3 Frames im Grafik-Zeitraum, nach Punch-in-Zoom und -Pan; die Grafik muss
  für die ungünstigste Position passen. Gesten (Bewegung im Grafikbereich) sind eine weiche Warnung.
- **Sichere Zone** (Reel 1080 × 1920: x 108–900, y 290–1340): sichtbare Pixel vollständig innerhalb. Harte Regel.
- **Ausweich-Reihenfolge:** (1) über dem Kopf, notfalls kleiner bis zur Mindestgröße (Versalhöhe ≥ 48 px), (2) neben dem
  Kopf, wenn ≥ 300 px frei sind, (3) unter dem Kinn im Brustbereich, (4) **nicht setzen** und melden („kein sauberer
  Platz“) – dann andere Stelle, kürzerer Text (z. B. ohne Zusatzzeile) oder ohne Grafik.
- **Kanten an Schnitten:** Grafiken dürfen mitten in einem Clip ein-/ausblenden, aber nicht 1–10 Frames neben einem
  Schnitt (dann rastet die Kante auf den Schnitt ein); Standbilder rasten bis 0,6 s auf Schnitte ein.

## Vorgehen
1. Stellen auswählen (siehe „Wann") und dem Nutzer kurz vorschlagen.
2. Template wählen und Parameter setzen; freie Gestaltung nur im Sandbox-Modus.
3. **Kontaktblatt prüfen** (5–6 Standbilder je Grafik, über dem echten Frame, Hilfslinien Kopfbox/Abstand/sichere Zone):
   sichere Zone, Lesbarkeit, Abstand zum Kopf, wirkt es hochwertig?
4. Erst dann rendern. Im Komplett-Schnitt gehören die Grafiken in die eine Cutlist, auf einer fertigen Timeline nimmst du `add_graphics`.

## Innenabstand (alle Boxen, Tokens unter `spacing`)
- Seitlich ≥ 0,9–1,2 × Versalhöhe, oben/unten ≥ 0,5–0,7 × Versalhöhe; Abstand Name ↔ Rolle 0,25–0,35 × Namensgröße; Akzentlinie mit eigenem Abstand zum Text. Alles relativ zur Schrift, skaliert also mit 1080p/4K.
- Boxbreite folgt dem Text plus Innenabstand; kurze Namen bekommen eine Mindestbreite.
- Der Server misst im gerenderten Frame Text gegen Box. Unterschreitet eine Grafik das Minimum, wird sie nicht gesetzt. `preview_graphic` zeichnet die Hilfslinien (Text grün, Minimum weiß), `run_qc` führt die Werte auf.
- Bauchbinde: Title-Safe-Abstand, Seite gegenüber dem Kopf. Bewegung unter der Grafik (Hände) wird als weiche Warnung gemeldet; ein ruhendes Mikrofon erkennt der Server nicht, das im Bild prüfen.
