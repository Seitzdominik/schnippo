# Schnippo

AI rough cuts for DaVinci Resolve: tell Claude which folder to cut and get a non-destructive timeline in DaVinci Resolve Studio. Your original files are never changed.
Start with the [English summary](#english-summary), die deutsche Anleitung steht [weiter unten](#deutsch).

## English summary

Schnippo reads a folder of takes, transcribes it with Gladia using your own key, lets Claude choose takes and cuts, and builds a timeline in DaVinci Resolve Studio from your original clips, with audio mastering, zooms, B-roll, graphics, sound effects and reels. Before every change it saves a backup timeline, and manual edits you make in Resolve are kept. Schnippo's messages and editing guides are in German; English footage works too.

### Where it runs

Claude Code (terminal, IDE extensions and the Code tab of the Claude desktop app) and Cowork sessions on your own computer. Regular chat does not start local servers; for chat in Claude Desktop use the `.mcpb` from [Releases](https://github.com/Seitzdominik/schnippo/releases).

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
- **Anything else:** [open an issue](https://github.com/Seitzdominik/schnippo/issues).

## What the plugin runs, sends and fetches

The plugin starts the local MCP server with `uvx schnippo==0.13.0` from PyPI. Source code: https://github.com/Seitzdominik/schnippo. On your computer it talks to DaVinci Resolve through its scripting interface and runs `ffmpeg` and `ffprobe`. The key window uses `osascript` on macOS and `powershell` on Windows. Helpers are installed once with `uv pip install`. Graphics render in a headless Chromium with all network requests blocked.

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

Full policy: [English](https://schnippo.com/en/privacy/), [Deutsch](https://schnippo.com/datenschutz/).

- **Data collection:** Schnippo processes your media, transcripts, settings and keys on your computer. The publisher receives none of it.
- **Use and storage:** transcripts, analyses and settings stay local: on macOS in `~/Library/Caches/schnippo` and `~/.config/schnippo`, on Windows in `%LOCALAPPDATA%\schnippo\Cache` and `%APPDATA%\schnippo`.
- **Third-party sharing:** only the services in the table above, with your own accounts.
- **Retention:** local data stays until you delete it with `clear_cache`, in the Finder or Explorer. Gladia and your AI provider keep data according to their own terms.
- **Contact:** Seitz Dominik Visuals, dominik@sdv.design, [GitHub issues](https://github.com/Seitzdominik/schnippo/issues).

Schnippo is not intended for people under 18. Only use it with material you are allowed to share with these services.

## Licence and trademark

MIT, © Seitz Dominik Visuals. Third-party notices: https://github.com/Seitzdominik/schnippo/blob/main/THIRD_PARTY_NOTICES.md. DaVinci Resolve is a trademark of Blackmagic Design. Schnippo is an independent project and is not affiliated with Blackmagic Design.

## Deutsch

KI-Rohschnitt für DaVinci Resolve. Schnippo baut aus deinen Takes per Chat einen Rohschnitt in DaVinci Resolve Studio, mit Ton, Zooms, B-Roll, Grafiken und Reels. Deine Originaldateien bleiben unverändert.

**Du brauchst** einen Mac oder Windows 10/11 (64 bit, Beta), DaVinci Resolve Studio 21.1 oder neuer mit „External scripting using = Local“, [uv](https://docs.astral.sh/uv/) und einen eigenen [Gladia-Key](https://app.gladia.io).

**Installation:** wie oben. Nach der Installation fragt Claude Code nach dem Key. Gibt es keine Abfrage, sag „Richte mich ein“: `store_api_key` öffnet ein Systemfenster, der Key läuft nie durch den Chat.

**Nutzung:** Sag zum Beispiel „Schneide den Ordner … als Reel“ oder „Mach aus dem Video 3 Reels“. Beim ersten Start führt ein kurzes Onboarding durch alles.

Datenschutz: https://schnippo.com/datenschutz/
