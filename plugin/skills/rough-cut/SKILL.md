---
name: rough-cut
description: "Ablauf eines Rohschnitts mit Schnippo in DaVinci Resolve: Einlesen, Komplett-Schnitt, Korrekturen, Export. Nutzen, wenn ein Ordner mit Takes geschnitten werden soll."
---

# Rohschnitt mit Schnippo

Schnippo schneidet in einem Rutsch: eine Timeline `<Name>_Schnippo`, ein kurzer Bericht, danach Korrekturen direkt auf dieser Timeline. Vor jeder Änderung liegt eine Sicherung in `Schnippo/Versionen`, Handänderungen bleiben erhalten, Originale werden nie verändert.

1. **Einrichtung:** beim ersten Kontakt `check_setup` oder `onboarding`.
2. **Einlesen:** `ingest_folder` mit Ordner oder Projektnamen, dann `transcribe`. Über 30 Minuten neuem Audio zeigt das Tool zuerst die Kosten.
3. **Schneiden, ohne Zwischenstände in Resolve:** `get_edit_context(pass="komplett")`, Rough Cut, Fine Cut, `sense_check(cutlist=…)`, B-Roll, Zooms, Grafiken, Sound-Effekte, `validate_cutlist`.
4. **Bauen:** `complete_cut` baut, sichert, misst den Ton, prüft und gibt den Bericht.
5. **Korrekturen:** `revise`, `master_audio`, `apply_zooms`, `add_overlays`, `add_graphics`, `add_sfx`, `restore_version`.

Die Leitfäden liefert `get_edit_context(pass=…)`. Referenziere Material nur über IDs, zum Beispiel `c03:w0120`. Liegt ein `brief.md` im Projekt, richte Auswahl, Hook und Länge danach aus.
