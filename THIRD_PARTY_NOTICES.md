# Drittanbieter-Hinweise

## FFmpeg (ffmpeg, ffprobe)

Schnippo (MIT) ruft FFmpeg und ffprobe als **eigenständige Programme** auf (Unterprozess, keine Bibliothek wird
gelinkt). Ist auf dem Rechner bereits ein ffmpeg installiert (PATH, Homebrew), wird dieses verwendet. Sonst kommen die
Programme aus dem PyPI-Paket [`portable-ffmpeg-full`](https://pypi.org/project/portable-ffmpeg-full/) (Version 0.5.0),
das uv beim ersten Start der Erweiterung von PyPI installiert. Das `.mcpb`-Paket selbst enthält keine FFmpeg-Binärdatei.

- Wrapper `portable-ffmpeg`: MIT.
- Enthaltene Binärdateien: FFmpeg 9.0.2 (Build von Martin Riedl), lizenziert unter **GPL-3.0-or-later**, mit
  x264/x265 und weiteren Komponenten unter ihren eigenen Lizenzen.
- Quellcode und Lizenztexte der Binärdateien:
  https://github.com/mrkbac/portable-ffmpeg/releases/tag/ffmpeg-9.0.2-1

FFmpeg ist eine Marke von Fabrice Bellard, dem Begründer des FFmpeg-Projekts (https://ffmpeg.org). Schnippo ist
nicht mit FFmpeg verbunden.

Bedeutung für die Weitergabe (keine Rechtsberatung): Weil FFmpeg nur als separates Programm aufgerufen wird, bleibt der
eigene Code MIT (GPL-FAQ „mere aggregation“). Solange das Bundle die Binärdatei nicht selbst enthält, verteilen
PyPI/der Paket-Maintainer die GPL-Binärdatei samt Quellcode. Würde die Binärdatei ins Bundle gelegt, müssten GPL-Text,
FFmpeg-Hinweise und der Quellcode-Link (oder ein schriftliches Angebot) mitgeliefert werden.

## Python-Abhängigkeiten

Installiert aus PyPI, nicht in diesem Repository enthalten.

| Paket | Version | Lizenz | Quelle |
|---|---|---|---|
| mcp | 2.3.0 | MIT | https://github.com/modelcontextprotocol/python-sdk |
| pydantic | 2.14.2 | MIT | https://github.com/pydantic/pydantic |
| httpx | 0.28.1 | BSD-3-Clause | https://github.com/encode/httpx |
| numpy | 2.5.4 | BSD-3-Clause und weitere (0BSD, MIT, Zlib) | https://github.com/numpy/numpy |
| opencv-python-headless | 4.14.0.94 | Apache-2.0 (OpenCV), Bundles mit eigenen Lizenzen | https://github.com/opencv/opencv-python |
| pillow | 13.0.0 | MIT-CMU | https://github.com/python-pillow/Pillow |
| python-docx | 1.2.0 | MIT | https://github.com/python-openxml/python-docx |
| rapidfuzz | 3.14.6 | MIT | https://github.com/rapidfuzz/RapidFuzz |
| portable-ffmpeg-full | 0.5.0 | Wrapper MIT, Binärdateien GPL-3.0-or-later | siehe oben |

Die vollständige Liste mit transitiven Abhängigkeiten steht in `uv.lock`.

## Playwright und Chromium

Bewegte Grafiken rendert Schnippo mit [Playwright](https://github.com/microsoft/playwright-python) 1.64.1 (Apache-2.0) und chromium-headless-shell ([Chromium](https://www.chromium.org), BSD-3-Clause und weitere). Beides ist nicht im Paket enthalten: Das Tool `motion_setup` lädt es beim ersten Gebrauch in den Cache. Der Browser läuft ohne Netzwerkzugriff.

## Schriften

Liegen in `src/schnippo/mg/fonts/`, jeweils mit Lizenztext, alle unter der [SIL Open Font License 1.1](https://openfontlicense.org): DM Sans, Instrument Sans, Inter, Manrope, Space Grotesk. Die Schriften wurden nicht verändert, nur als WOFF2 in einzelnen Schnitten beigelegt.

## Sound-Effekte

Eigene Effekte in `src/schnippo/data/sfx/wav/` sind synthetisch erzeugt und stehen unter MIT. Maus, Tastatur, Uhr, Klingel und Vinyl-Scratch sind Aufnahmen unter CC0 von [Freesound](https://freesound.org). Quelle, Urheber und Bearbeitung je Datei: [LICENSES.md](src/schnippo/data/sfx/LICENSES.md).

| Quelle | Urheber | Lizenz |
|---|---|---|
| [Freesound 192068](https://freesound.org/s/192068/) mouseclicks | Nutzerkonto gelöscht | CC0 |
| [Freesound 866643](https://freesound.org/s/866643/) Keyboard typing | 7empest | CC0 |
| [Freesound 869203](https://freesound.org/s/869203/) Steba oven clock | initbruv | CC0 |
| [Freesound 668909](https://freesound.org/s/668909/) Vinyl Scratch | ChuckChuckGoof | CC0 |

## Marken

DaVinci Resolve ist eine Marke von Blackmagic Design Pty Ltd. Schnippo ist ein unabhängiges Projekt und nicht mit Blackmagic Design verbunden. Claude ist eine Marke von Anthropic.
