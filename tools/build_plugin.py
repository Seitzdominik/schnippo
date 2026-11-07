"""Writes the plugin variant for the Claude directory into plugin/: manifest, MCP entry, README, LICENSE and skills from the guides. Run after a version change.

    uv run python tools/build_plugin.py"""
import json
import re
import shutil
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from schnippo import branding as b  # noqa: E402

OUT = REPO / "plugin"
GUIDES = REPO / "src" / "schnippo" / "data" / "guides"
SKILLS = {
    "reels": ("07_reels.md", "Reels aus einem fertigen langen Video finden, bauen und exportieren. Nutzen bei Wünschen wie „Mach aus dem Video 3 Reels“ oder Hochformat aus 16:9."),
    "sound-design": ("06_sound_design.md", "Regeln für Sound-Effekte im Videoschnitt: wann, wie viel, wie laut. Nutzen, bevor im B-Roll- oder Motion-Durchgang Effekte gesetzt werden."),
    "motion-graphics": ("05_motion_graphics.md", "Regeln für Grafiken im Schnitt: Callouts, Zähler, Hook-Texte, sichere Zonen. Nutzen, bevor im Motion-Durchgang Grafiken gesetzt werden."),
}
FLOW = """# Rohschnitt mit Schnippo

Schnippo arbeitet in Durchgängen, jeder mit einer eigenen Timeline. Nichts wird überschrieben, Originale bleiben unverändert.

1. **Einrichtung:** beim ersten Kontakt `check_setup` oder `onboarding`.
2. **Einlesen:** `ingest_folder` mit Ordner oder Projektnamen, dann `transcribe`. Über 30 Minuten neuem Audio zeigt das Tool zuerst die Kosten.
3. **Rough Cut:** `get_edit_context(pass="rough")`, Cutlist schreiben, `validate_cutlist`, `build_timeline`, dann `show_review`.
4. **Fine Cut:** Rhythmus, Punch-ins, Atempausen.
5. **B-Roll:** nur Bilder ergänzen, der Schnitt bleibt.
6. **Polish:** `analyze_audio`, Lautheit, `run_qc(audio=true)`, `sense_check`, Export.
7. **Motion:** Grafiken auf Wunsch.

Die Leitfäden je Durchgang liefert `get_edit_context(pass=…)`. Referenziere Material nur über IDs, zum Beispiel `c03:w0120`. Liegt ein `brief.md` im Projekt, richte Auswahl, Hook und Länge danach aus.
"""
README = """# Schnippo

{tagline}. Schnippo baut aus deinen Takes per Chat einen Rohschnitt in DaVinci Resolve Studio, mit Ton, Zooms, B-Roll, Grafiken und Reels. Deine Originaldateien bleiben unverändert. DaVinci Resolve ist eine Marke von Blackmagic Design, Schnippo ist ein unabhängiges Projekt.

## Einrichtung

Du brauchst einen Mac, DaVinci Resolve Studio 21.1 oder neuer mit „External scripting using = Local“, [uv](https://docs.astral.sh/uv/) und einen eigenen [Gladia-Key](https://app.gladia.io). Nach der Installation fragt das Plugin nach dem Key. Gibt es keine Abfrage, sag im Chat „Richte mich ein“: Das Tool `store_api_key` öffnet ein Systemfenster und legt den Key im Schlüsselbund ab. Der Key läuft nie durch den Chat.

## Installation

`/plugin install schnippo --marketplace Seitzdominik/schnippo`

## Nutzung

Sag zum Beispiel „Schneide den Ordner … als Reel“ oder „Mach aus dem Video 3 Reels“. Beim ersten Start führt ein kurzes Onboarding durch alles.

## Was das Plugin startet und wohin es Daten schickt

Das Plugin startet den lokalen MCP-Server mit `uvx schnippo@{version}` von PyPI. Quellcode: {repo}

| Ziel | Wann | Was |
|---|---|---|
| Gladia (api.gladia.io) | beim Transkribieren | Tonspur der Clips |
| GitHub (api.github.com) | höchstens einmal täglich, abschaltbar | Abfrage der neuesten Version, keine Daten |
| Freesound, ElevenLabs | nur mit eigenem Key und auf Wunsch | Suchbegriff oder Beschreibung |
| PyPI, GitHub (Playwright, ffmpeg) | bei Installation und beim ersten Grafik-Render | Download von Abhängigkeiten |

Transkripte und Kontaktabzüge sieht das KI-Modell deines Claude-Kontos. Es gibt keine Telemetrie.

## Privacy Policy

Vollständig unter {privacy}.

- **Datenerhebung:** Schnippo selbst erhebt keine Daten und betreibt keinen Server.
- **Nutzung und Speicherung:** Transkripte, Analysen und Einstellungen bleiben lokal in `~/Library/Caches/schnippo` und `~/.config/schnippo`.
- **Weitergabe an Dritte:** nur an die Dienste aus der Tabelle oben, mit deinem eigenen Konto.
- **Aufbewahrung:** Du löschst lokale Daten jederzeit mit `clear_cache` oder im Finder. Für Gladia gelten deren Bedingungen.
- **Kontakt:** {author}, {author_url}

## Lizenz

MIT. Hinweise zu Dritten: {repo}/blob/main/THIRD_PARTY_NOTICES.md
"""


def main():
    version = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / ".claude-plugin").mkdir(parents=True)
    plugin = {"name": b.SLUG, "displayName": b.DISPLAY_NAME, "version": version, "description": f"{b.TAGLINE}: Rohschnitt per Chat, mit Ton, Zooms, B-Roll, Grafiken und Reels.",
              "author": {"name": b.AUTHOR, "url": b.AUTHOR_URL}, "homepage": b.HOMEPAGE, "repository": b.REPOSITORY, "license": "MIT", "keywords": ["video", "schnitt", "davinci-resolve", "transkript", "reels"],
              "documentationUrl": b.DOCS_URL, "supportUrl": b.SUPPORT_URL, "privacyPolicyUrl": b.PRIVACY_URL,
              "userConfig": {
                  "gladia_api_key": {"type": "string", "title": "Gladia-API-Key", "description": "Für die Transkription, von app.gladia.io.", "sensitive": True, "required": False},
                  "projects_folder": {"type": "directory", "title": "Standardordner für Projekte", "description": "Dann reicht im Chat der Projektname.", "required": False},
                  "format": {"type": "string", "title": "Format", "description": "auto, reel, youtube, course oder commercial.", "default": "auto", "required": False},
                  "sfx": {"type": "string", "title": "Sound-Effekte", "description": "off, subtil oder normal.", "default": "subtil", "required": False}}}
    (OUT / ".claude-plugin" / "plugin.json").write_text(json.dumps(plugin, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mcp = {"mcpServers": {b.SLUG: {"command": "uvx", "args": [f"schnippo@{version}"],
                                   "env": {"GLADIA_API_KEY": "${user_config.gladia_api_key}", "SCHNIPPO_PROJECTS_FOLDER": "${user_config.projects_folder}", "SCHNIPPO_FORMAT": "${user_config.format}",
                                           "SCHNIPPO_SFX_MODE": "${user_config.sfx}"}}}}
    (OUT / ".mcp.json").write_text(json.dumps(mcp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(README.format(tagline=b.TAGLINE, version=version, repo=b.REPOSITORY, privacy=b.PRIVACY_URL, author=b.AUTHOR, author_url=b.AUTHOR_URL), encoding="utf-8")
    shutil.copy2(REPO / "LICENSE", OUT / "LICENSE")
    shutil.copy2(b.brand_file("icon.png", REPO / "packaging" / "icon.png"), OUT / ".claude-plugin" / "icon.png")

    def skill(name, description, body):
        d = OUT / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n{body.strip()}\n", encoding="utf-8")

    skill("rohschnitt", "Ablauf eines Rohschnitts mit Schnippo in DaVinci Resolve: Einlesen, Durchgänge, Prüfung, Export. Nutzen, wenn ein Ordner mit Takes geschnitten werden soll.", FLOW)
    for name, (file, description) in SKILLS.items():
        skill(name, description, (GUIDES / file).read_text(encoding="utf-8"))
    print("plugin/ geschrieben", version)


if __name__ == "__main__":
    main()
