# Durchgang 2: Fine Cut

**Einziger Job:** Rhythmus und unsichtbare Schnittpunkte. Inhalt und Take-Wahl aus dem Rough Cut bleiben, außer ein Schnitt funktioniert nachweislich nicht.

Kennzeichnung: **[E]** belegt · **[P]** Profi-Praxis · **[S]** Default/Synthese (konfigurierbar).

## Vorgehen
1. Cutlist aus V1 übernehmen.
2. Pausen, Füller und Atmer nach den Regeln unten.
3. `validate_cutlist` → auffällige Schnitte (Bewegungswert) → `preview_cuts` ansehen.
4. Problematische Schnitte per `start_frame`/`end_frame` oder Take-Wechsel korrigieren.
5. Punch-ins setzen.
6. Im Komplett-Schnitt weiter, nichts bauen. Im Durchgangs-Modus: `build_timeline` auf `<Name>_Schnippo`.

## Schnittpunkte
- **Nie in einem Wort schneiden** [P]. Vorlauf vor dem Wort 2–4 Frames, Nachlauf 3–6 Frames [S] (Server-Default: 80/120 ms).
- **Wortenden kommen aus dem Signal, nicht aus Gladia** (dessen Grenzen liegen auf dem stimmhaften Teil). Der Server folgt dem Ausklang bis Rauschboden + 6 dB (max. 350 ms lang, 200 ms Reel), sucht den Konsonanten-Einsatz bis 120 ms vor dem Wort und hält die letzten/ersten 10 ms jedes Stücks nahe am Rauschboden. Ein `{?}` ohne Lücke am Wort (bis 0,28 s) ist ein gedehntes Wort und bleibt. Ein stimmhafter Laut direkt nach dem Satzende (`hm`, Seufzen, Lachen) gehört zur Aussage. Was nicht geht, meldet `validate_cutlist`/`run_qc` als „harte Kante“: dann per `start_frame`/`end_frame` oder anderem Take nachbessern.
- Prüfreihenfolge je Schnitt [P]: **Bedeutung → Bild** (Haltung, Hände, Blick, Lider) **→ Ton** (Knacken, Raumton-Sprung).
- Nicht auf halb geschlossenen Lidern, nicht mitten in einer Geste; Ruhe oder Bewegungsbeginn bevorzugen [S]. Der Server sucht das automatisch (max. 200 ms Verschiebung); Claude prüft das Ergebnis in `preview_cuts`.
- Zielkonflikte nach Murchs Rule of Six [P]: **Emotion > Story > Rhythmus** > Blickführung > Bildebene > Raum. Ein Schnitt mit richtiger Emotion und leichtem Bildsprung schlägt einen sauberen, aber leblosen Schnitt.

## Pausen, Füller, Atmer
- Restpause zwischen Sätzen (auch an Item-Grenzen): Reel 100–250 ms, YouTube/Kurs/Interview 250–450 ms; im Satz etwas weniger [S]. War die Originalpause kürzer, bleibt sie.
- **FC3 – Atempausen nach wichtigen Aussagen (Pflicht in langen Formaten):** Kernaussagen, Pointen und Abschnittsenden kennzeichnen, damit Zuschauer die Information verarbeiten können [S/P]. Am Item `"beat": "key" | "section"` (gilt für sein letztes Wort) oder für Stellen im Item `"beats": [{"after": "c01:w0330", "beat": "key"}]`.
  - Richtwert lange Formate: etwa eine Kernaussage je 30–60 s bzw. nach jedem inhaltlichen Punkt. Reel: höchstens 1–2.
  - Der Server lässt dahinter die **natürliche** Pause stehen: `key` Reel 300–500 ms, lang 600–1000 ms; `section` lang 800–1200 ms. Nie künstliche Stille; war das Original kürzer, bleibt das Original. Der Raumton der Pause bleibt.
  - `validate_cutlist` zeigt je Beat die tatsächliche Pause. Liegt ein Beat auf einer Stelle ohne Originalpause, lieber den nächsten Satzschluss nehmen.
- Füller (`{?}`), Fehlstarts und Wiederholungen raus; Qualifizierungen, Lacher und echte Reaktionen bleiben [P].
- Hörbare Einatmer zwischen Sätzen raus. Stil `ruhig`: natürliche Atmer an Absatzgrenzen behalten, sonst klingt es roboterhaft [P/S].

## Punch-ins (Jump-Cuts kaschieren)
- Bei Jump-Cuts in derselben Einstellung abwechseln: **100 % ↔ 120 %** [S]. Der Server streut jede dritte Stufe als Abwechslung ein (112 %, dann 125 %); jede zweite Stufe ist 100 %, zwei gleiche Stufen folgen nie direkt aufeinander.
- Obergrenze nach Quellauflösung (Lieferung 1080p): **1080p-Quelle max. ~125 %**, darüber wird es weich (Warnung in `validate_cutlist`); **4K-Quelle bis ~200 %** ohne Verlust. Beim 4K-Export sind gezoomte Stellen hochskaliert.
- Nie zwei aufeinanderfolgende Schnitte mit gleicher Skala auf demselben Take ohne Abdeckung [S].
- Punch-ins nur an Satzanfängen; eine Rahmung mindestens einen Satz halten, nicht bei jedem Schnitt wechseln [S].
- **Akzent-Punch** (130–135 %, per `zoom` am Item) nur für Pointen, max. einen Satz halten, sparsam [S]. Bei 1080p-Quelle liegt er über der Grenze: nur bewusst einsetzen.
- Ausrichtung: Gesicht bleibt an Position; Augen etwa im oberen Drittel [P/S].

## Tempo
- Dicht im Hook (erste 10 s) und an Übergängen, lockerer bei komplexen Erklärungen [S].
- Visueller Wechsel (Schnitt, Punch-in, B-Roll, Grafik) im Mittel: Reel alle 2–4 s, kein unveränderter Frame > 5 s; YouTube alle 3–7 s [V/S]. Das ist ein Richtwert, kein Zwang: lieber ein ruhiger guter Satz als ein Zoom ohne Grund.
- Stil-Parameter: `dicht` (sehr schnell, z. B. Fitness/Finanzen/Entertainment) · `ruhig` (B2B, Beratung, Premium). Default `ruhig-dicht` [V].

## Split-Edits (nur YouTube, nach dem harten Schnitt)
- Dialog-Überlappung ~0,5 s; J-Cut an Abschnittsübergängen bis 2 s [P]. Für Reels in der Regel nicht nötig.
