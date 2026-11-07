# Durchgang 4: Polish

**Einziger Job:** Ton fertig machen, technische Qualitätskontrolle, Transkript exportieren. Keine Schnittänderungen mehr, außer die QC findet einen Fehler.

Kennzeichnung: **[E]** belegt · **[P]** Profi-Praxis · **[S]** Default/Synthese (konfigurierbar).

## Ton
- `analyze_audio` zuerst; **jede EQ-Maßnahme braucht eine Begründung aus der Messung** [S].
- Lautheit **−14 LUFS integriert** (Toleranz −13 bis −16), **True Peak ≤ −1 dBTP** [P, keine offizielle Plattformvorgabe].
- Doppelte Mono-Spuren erkennen und die Kopie stummschalten.
- EQ-Richtwerte, nur bei Bedarf [P]: Hochpass ab 80 Hz (60–100 Hz), dumpfer Klang 200–500 Hz kleiner schmaler Cut, Präsenz 2–5 kHz +1–3 dB breit, Zischlaute 5–8 kHz per De-Esser.
- Kompression nach EQ, ~3:1, 2–6 dB Gain Reduction [P/S] (sofern per API möglich).
- Musik (später): 15–25 dB unter Sprache mit Ducking; erst anlegen, wenn der Schnitt ohne Musik funktioniert [S/P]. Bei geplantem Trending-Audio in der App: Export ohne Musik.

## Qualitätskontrolle (automatisiert, im Bericht auflisten)
- Keine Flash-Frames (Teilstücke < 3 Frames), keine Lücken ohne Ton, keine angeschnittenen Wörter.
- Nicht auf jedem Schnitt ein Zoom.
- Framerate, Dauer und A/V-Sync verifiziert.
- Keine Wasserzeichen anderer Apps im Material [E: wird von Plattformen abgewertet].

## Sinnprüfung vor dem Export (`sense_check`)
Der fertige Schnitt wird noch einmal **gehört**: Der Ton geht an Gladia (etwa 0,10 USD je 10 min, Quittung im Ergebnis).
1. **Nähte (automatisch):** Gehörtes gegen erwarteten Text, ±2 Wörter um jeden Schnitt. Verschluckt, verdoppelt, verstümmelt = „unsaubere Naht“ mit Zeitstempel. Abweichungen abseits der Nähte sind Erkennungsrauschen.
2. **Sinn (Claude):** Den gehörten Text abschnittsweise lesen wie ein Zuschauer: Satzbrüche, Bezüge ohne Bezugswort („das“, „er“ ohne vorherige Nennung), unvollendete Gedanken, abrupte Themensprünge, Widersprüche. Je Fund Zeitstempel und Vorschlag: Satz zurückholen, anderen Take nehmen, Satz entfernen.
3. **Beheben:** per `revise`, neu bauen, `sense_check` auf der neuen Version: nur geänderte Stücke werden erneut transkribiert. Unklare Fälle als Frage an den Nutzer.
`export_transcript` nutzt danach die gehörten Wortzeiten (genauer im fertigen Schnitt), Korrekturen gelten weiter.

## Video-Export
- Nach bestandener QC: `export_final(timeline)` – Reel 1080×1920 (Hochformat) oder YouTube 1080p (Querformat);
  `youtube_4k` nur aus 4K-Timelines. Kein zusätzliches Normalisieren: die Lautheit steckt schon in der Timeline.
- Kein Reframing: aus einer Querformat-Timeline wird kein Reel.

## Transkript-Export (statt Untertitel in Resolve)
- `export_transcript` aus den Wort-Timestamps des **fertigen Schnitts**, mit allen Korrekturen: `.srt` (für Instagram/Edits/YouTube-Upload), `.txt` (Fließtext, z. B. für Beschreibung/Blog).
- YouTube-Profil: zusätzlich Kapitelvorschläge (erstes bei 0:00, ≥ 3 Kapitel, je ≥ 10 s) [S].
- Untertitel-Blöcke: max. 3–5 Wörter, Bruch an Satzzeichen/Pausen [V].

## Abschluss
- Dem Nutzer melden: Laufzeit, Lautheit/True Peak, Anzahl Schnitte/Punch-ins/Overlays, offene Grenzfälle und inhaltliche Fragen.
- Hinweis an den Nutzer: einmal bei 1× komplett ansehen, einmal bei 1,25× auf Längen [V].
