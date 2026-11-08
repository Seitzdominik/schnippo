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
TAGLINE_EN = "AI rough cuts for DaVinci Resolve"
CONTACT = "dominik@sdv.design"  # the address of the published privacy policy
SKILLS = {
    "reels": ("07_reels.md", "Reels aus einem fertigen langen Video finden, bauen und exportieren. Nutzen bei Wünschen wie „Mach aus dem Video 3 Reels“ oder Hochformat aus 16:9."),
    "sound-design": ("06_sound_design.md", "Regeln für Sound-Effekte im Videoschnitt: wann, wie viel, wie laut. Nutzen, bevor im B-Roll- oder Motion-Durchgang Effekte gesetzt werden."),
    "motion-graphics": ("05_motion_graphics.md", "Regeln für Grafiken im Schnitt: Callouts, Zähler, Hook-Texte, sichere Zonen. Nutzen, bevor im Motion-Durchgang Grafiken gesetzt werden."),
}
FLOW = """# Rohschnitt mit Schnippo

Schnippo schneidet in einem Rutsch: eine Timeline `<Name>_Schnippo`, ein kurzer Bericht, danach Korrekturen direkt auf dieser Timeline. Vor jeder Änderung liegt eine Sicherung in `Schnippo/Versionen`, Handänderungen bleiben erhalten, Originale werden nie verändert.

1. **Einrichtung:** beim ersten Kontakt `check_setup` oder `onboarding`.
2. **Einlesen:** `ingest_folder` mit Ordner oder Projektnamen, dann `transcribe`. Über 30 Minuten neuem Audio zeigt das Tool zuerst die Kosten.
3. **Schneiden, ohne Zwischenstände in Resolve:** `get_edit_context(pass="komplett")`, Rough Cut, Fine Cut, `sense_check(cutlist=…)`, B-Roll, Zooms, Grafiken, Sound-Effekte, `validate_cutlist`.
4. **Bauen:** `complete_cut` baut, sichert, misst den Ton, prüft und gibt den Bericht.
5. **Korrekturen:** `revise`, `master_audio`, `apply_zooms`, `add_overlays`, `add_graphics`, `add_sfx`, `restore_version`.

Die Leitfäden liefert `get_edit_context(pass=…)`. Referenziere Material nur über IDs, zum Beispiel `c03:w0120`. Liegt ein `brief.md` im Projekt, richte Auswahl, Hook und Länge danach aus.
"""
README = """# Schnippo

{tagline_en}: tell Claude which folder to cut and get a non-destructive timeline in DaVinci Resolve Studio. Your original files are never changed.
Start with the [English summary](#english-summary), die deutsche Anleitung steht [weiter unten](#deutsch).

## English summary

Schnippo reads a folder of takes, transcribes it with Gladia using your own key, lets Claude choose takes and cuts, and builds a timeline in DaVinci Resolve Studio from your original clips, with audio mastering, zooms, B-roll, graphics, sound effects and reels. Before every change it saves a backup timeline, and manual edits you make in Resolve are kept. Schnippo's messages and editing guides are in German; English footage works too.

### Where it runs

Claude Code (terminal, IDE extensions and the Code tab of the Claude desktop app) and Cowork sessions on your own computer. Regular chat does not start local servers; for chat in Claude Desktop use the `.mcpb` from [Releases]({repo}/releases).

### Requirements

- Apple Silicon Mac, or 64-bit Windows 10/11 (beta)
- DaVinci Resolve Studio 21.1 or later, with Preferences → System → General → External scripting using = Local
- [uv](https://docs.astral.sh/uv/) on your PATH
- Your own [Gladia key](https://app.gladia.io), roughly USD 0.61 per hour of audio

### Install

Add Schnippo from the plugin directory, or in Claude Code:

```
/plugin marketplace add Seitzdominik/schnippo
/plugin install schnippo@schnippo
```

Claude Code asks for your Gladia key when you enable the plugin. If you skip it, say "Set me up": the `store_api_key` tool opens a system window and saves the key in the macOS Keychain or the Windows Credential Manager, so it never passes through the chat. The first start downloads about 44 MB and can take a few minutes on Windows.

### First cut

Try these prompts:

1. "Set me up."
2. "Cut the folder /path/to/takes as a YouTube video."
3. "Remove #05 from the timeline and master the audio again."
4. "Make 3 reels from the finished video."

### Troubleshooting

- **The server does not start:** check that `uv --version` works, then look at `/mcp`.
- **Resolve is not reachable:** start DaVinci Resolve Studio, open a project and set External scripting to Local. The free version has no scripting.
- **A cut went wrong:** say "Restore the previous version". Backups are in the bin `Schnippo/Versionen`.
- **Anything else:** [open an issue]({repo}/issues).

## What the plugin runs, sends and fetches

The plugin starts the local MCP server with `uvx schnippo=={version}` from PyPI. Source code: {repo}. On your computer it talks to DaVinci Resolve through its scripting interface and runs `ffmpeg` and `ffprobe`. The key window uses `osascript` on macOS and `powershell` on Windows. Helpers are installed once with `uv pip install`. Graphics render in a headless Chromium with all network requests blocked.

| Destination | When | What |
|---|---|---|
| Gladia (`api.gladia.io`) | transcribing, checking the finished cut (`sense_check`), checking your key; with your key | audio track (16 kHz mono, no metadata), glossary terms |
| Your AI provider, for example Anthropic (Claude) | during the cut, through your own account | transcripts, editing context, file names, frames and contact sheets |
| GitHub (`api.github.com`) | at most once a day, can be switched off | only a query for the latest version |
| Freesound (`freesound.org`) | only on request, with your key | search terms |
| ElevenLabs (`api.elevenlabs.io`) | only on request, with your key | description of a sound effect |
| PyPI (`pypi.org`, `files.pythonhosted.org`) | at installation, at the first ingest (ffmpeg, OpenCV), at `motion_setup` | downloads only |
| GitHub (`github.com`) | at installation, when uv needs a Python runtime | downloads only |
| Playwright CDN (`cdn.playwright.dev`) | at `motion_setup` | downloads Chromium for graphics |

There is no telemetry and no Schnippo server.

## Privacy Policy

Full policy: [English]({privacy}), [Deutsch]({privacy_de}).

- **Data collection:** Schnippo processes your media, transcripts, settings and keys on your computer. The publisher receives none of it.
- **Use and storage:** transcripts, analyses and settings stay local: on macOS in `~/Library/Caches/schnippo` and `~/.config/schnippo`, on Windows in `%LOCALAPPDATA%\\schnippo\\Cache` and `%APPDATA%\\schnippo`.
- **Third-party sharing:** only the services in the table above, with your own accounts.
- **Retention:** local data stays until you delete it with `clear_cache`, in the Finder or Explorer. Gladia and your AI provider keep data according to their own terms.
- **Contact:** {author}, {contact}, [GitHub issues]({repo}/issues).

Schnippo is not intended for people under 18. Only use it with material you are allowed to share with these services.

## Licence and trademark

MIT, © {author}. Third-party notices: {repo}/blob/main/THIRD_PARTY_NOTICES.md. DaVinci Resolve is a trademark of Blackmagic Design. Schnippo is an independent project and is not affiliated with Blackmagic Design.

## Deutsch

{tagline}. Schnippo baut aus deinen Takes per Chat einen Rohschnitt in DaVinci Resolve Studio, mit Ton, Zooms, B-Roll, Grafiken und Reels. Deine Originaldateien bleiben unverändert.

**Du brauchst** einen Mac oder Windows 10/11 (64 bit, Beta), DaVinci Resolve Studio 21.1 oder neuer mit „External scripting using = Local“, [uv](https://docs.astral.sh/uv/) und einen eigenen [Gladia-Key](https://app.gladia.io).

**Installation:** wie oben. Nach der Installation fragt Claude Code nach dem Key. Gibt es keine Abfrage, sag „Richte mich ein“: `store_api_key` öffnet ein Systemfenster, der Key läuft nie durch den Chat.

**Nutzung:** Sag zum Beispiel „Schneide den Ordner … als Reel“ oder „Mach aus dem Video 3 Reels“. Beim ersten Start führt ein kurzes Onboarding durch alles.

Datenschutz: {privacy_de}
"""


def main():
    version = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / ".claude-plugin").mkdir(parents=True)
    plugin = {"name": b.SLUG, "displayName": b.DISPLAY_NAME, "version": version, "description": f"{TAGLINE_EN}: cut by chat, with audio, zooms, B-roll, graphics and reels.",
              "author": {"name": b.AUTHOR, "url": b.AUTHOR_URL}, "homepage": b.HOMEPAGE, "repository": b.REPOSITORY, "license": "MIT", "icon": "icon.png", "keywords": ["video-editing", "davinci-resolve", "rough-cut", "transcript", "reels", "mcp"],
              "documentationUrl": b.DOCS_URL, "supportUrl": b.SUPPORT_URL, "privacyPolicyUrl": b.PRIVACY_URL,
              "userConfig": {
                  "gladia_api_key": {"type": "string", "title": "Gladia API key", "description": "Used for transcription. Get one at app.gladia.io.", "sensitive": True, "required": False},
                  "projects_folder": {"type": "directory", "title": "Default projects folder", "description": "Lets you use just the project name in chat.", "required": False},
                  "format": {"type": "string", "title": "Format", "description": "auto, reel, youtube, course or commercial.", "default": "auto", "required": False},
                  "sfx": {"type": "string", "title": "Sound effects", "description": "off, subtil or normal.", "default": "subtil", "required": False}}}
    (OUT / ".claude-plugin" / "plugin.json").write_text(json.dumps(plugin, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mcp = {"mcpServers": {b.SLUG: {"command": "uvx", "args": [f"schnippo=={version}"],
                                   "env": {"PYTHONUTF8": "1", "GLADIA_API_KEY": "${user_config.gladia_api_key}", "SCHNIPPO_PROJECTS_FOLDER": "${user_config.projects_folder}", "SCHNIPPO_FORMAT": "${user_config.format}",
                                           "SCHNIPPO_SFX_MODE": "${user_config.sfx}"}}}}
    (OUT / ".mcp.json").write_text(json.dumps(mcp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(README.format(tagline=b.TAGLINE, tagline_en=TAGLINE_EN, version=version, repo=b.REPOSITORY, privacy=b.PRIVACY_URL, privacy_de=b.PRIVACY_URL_DE, author=b.AUTHOR, contact=CONTACT), encoding="utf-8")
    shutil.copy2(REPO / "LICENSE", OUT / "LICENSE")
    shutil.copy2(b.brand_file("icon.png", REPO / "packaging" / "icon.png"), OUT / "icon.png")

    def skill(name, description, body):
        d = OUT / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n{body.strip()}\n", encoding="utf-8")

    skill("rough-cut", "Ablauf eines Rohschnitts mit Schnippo in DaVinci Resolve: Einlesen, Komplett-Schnitt, Korrekturen, Export. Nutzen, wenn ein Ordner mit Takes geschnitten werden soll.", FLOW)
    for name, (file, description) in SKILLS.items():
        skill(name, description, (GUIDES / file).read_text(encoding="utf-8"))
    print("plugin/ geschrieben", version)


if __name__ == "__main__":
    main()
