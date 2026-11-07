---
name: rohschnitt
description: "Ablauf eines Rohschnitts mit Schnippo in DaVinci Resolve: Einlesen, Durchgänge, Prüfung, Export. Nutzen, wenn ein Ordner mit Takes geschnitten werden soll."
---

# Rohschnitt mit Schnippo

Schnippo arbeitet in Durchgängen, jeder mit einer eigenen Timeline. Nichts wird überschrieben, Originale bleiben unverändert.

1. **Einrichtung:** beim ersten Kontakt `check_setup` oder `onboarding`.
2. **Einlesen:** `ingest_folder` mit Ordner oder Projektnamen, dann `transcribe`. Über 30 Minuten neuem Audio zeigt das Tool zuerst die Kosten.
3. **Rough Cut:** `get_edit_context(pass="rough")`, Cutlist schreiben, `validate_cutlist`, `build_timeline`, dann `show_review`.
4. **Fine Cut:** Rhythmus, Punch-ins, Atempausen.
5. **B-Roll:** nur Bilder ergänzen, der Schnitt bleibt.
6. **Polish:** `analyze_audio`, Lautheit, `run_qc(audio=true)`, `sense_check`, Export.
7. **Motion:** Grafiken auf Wunsch.

Die Leitfäden je Durchgang liefert `get_edit_context(pass=…)`. Referenziere Material nur über IDs, zum Beispiel `c03:w0120`. Liegt ein `brief.md` im Projekt, richte Auswahl, Hook und Länge danach aus.
