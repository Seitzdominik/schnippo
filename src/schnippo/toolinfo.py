"""Title and permission hints of every tool, as the Claude directory asks for them. r: only reads. w: adds to our own state or to something new, overwrites nothing of the user's. d: changes the Resolve
project or the user's files, or deletes; hosts ask before each call. n in the kind: reaches an outside service."""

TOOLS = {
    "complete_cut": ("Komplett-Schnitt", "d"), "master_audio": ("Ton mastern", "d"), "apply_zooms": ("Zooms setzen", "d"), "add_overlays": ("B-Roll einfügen", "d"), "add_graphics": ("Grafiken einfügen", "d"), "add_sfx": ("Sound-Effekte einfügen", "d"),
    "list_versions": ("Sicherungen auflisten", "r"), "restore_version": ("Sicherung wiederherstellen", "d"), "set_checkpoints": ("Rückfragen einstellen", "w"),
    "analyze_audio": ("Ton analysieren", "r"), "build_timeline": ("Timeline bauen", "d"), "check_setup": ("Einrichtung prüfen", "rn"), "clear_cache": ("Cache aufräumen", "d"),
    "create_project": ("Projekt anlegen", "d"), "design_preview": ("Design-Vorschau", "r"), "detect_format": ("Format erkennen", "r"), "export_final": ("Video exportieren", "d"),
    "export_reels": ("Reels exportieren", "d"), "export_transcript": ("Untertitel exportieren", "d"), "fetch_sfx": ("Sound von Freesound laden", "dn"),
    "find_reel_candidates": ("Reel-Stellen finden", "r"), "find_sfx": ("Sounds auf Freesound suchen", "rn"), "generate_sfx": ("Sound mit ElevenLabs erzeugen", "dn"),
    "get_edit_context": ("Schnitt-Kontext lesen", "r"), "get_frames": ("Kontaktabzug ansehen", "r"), "get_take_frames": ("Takes vergleichen", "r"), "get_transcript": ("Transkript lesen", "r"),
    "ingest_folder": ("Ordner einlesen", "w"), "list_clips": ("Clips auflisten", "r"), "list_sfx": ("Sound-Effekte auflisten", "r"), "load_script": ("Skript laden", "w"), "locate": ("Stelle finden", "r"),
    "merge_cutlists": ("Cutlists zusammenführen", "r"), "motion_setup": ("Grafik-Renderer installieren", "wn"), "onboarding": ("Onboarding", "w"), "prepare_recordings": ("Aufnahmen aufbereiten", "d"),
    "preview_cuts": ("Schnitte ansehen", "r"), "preview_graphic": ("Grafik-Vorschau", "r"), "read_timeline_changes": ("Änderungen in Resolve lesen", "w"), "reel_cutlist": ("Reel-Cutlist erstellen", "r"),
    "reel_sheet": ("Reel-Kontaktblatt", "w"), "resolve_status": ("Resolve-Status", "r"), "resume_job": ("Abgebrochenen Job fortsetzen", "d"), "revise": ("Änderungswünsche umsetzen", "d"),
    "run_qc": ("Qualität prüfen", "w"), "save_brand": ("Design-Profil speichern", "d"), "sense_check": ("Fertigen Schnitt gegenhören", "wn"), "set_clip_role": ("Clip einordnen", "w"),
    "set_format": ("Format festlegen", "w"), "set_glossary": ("Glossar ergänzen", "d"), "set_word_text": ("Wort korrigieren", "w"), "setup_design": ("Design einrichten", "r"),
    "show_reel_candidates": ("Reel-Vorschläge zeigen", "w"), "show_review": ("Entscheidungen vorlegen", "w"), "store_api_key": ("API-Key sicher speichern", "d"),
    "submit_review": ("Entscheidungen übernehmen", "w"), "suggest_corrections": ("Korrekturen vorschlagen", "r"), "transcribe": ("Transkribieren", "wn"), "validate_cutlist": ("Cutlist prüfen", "r"),
}
