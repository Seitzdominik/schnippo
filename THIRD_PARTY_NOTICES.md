# Drittanbieter-Hinweise

## FFmpeg (ffmpeg, ffprobe)

Dieses Projekt (MIT) ruft FFmpeg und ffprobe als **eigenständige Programme** auf (Unterprozess, keine Bibliothek wird
gelinkt). Ist auf dem Rechner bereits ein ffmpeg installiert (PATH, Homebrew), wird dieses verwendet. Sonst kommen die
Programme aus dem PyPI-Paket [`portable-ffmpeg-full`](https://pypi.org/project/portable-ffmpeg-full/) (Version 0.5.0),
das uv beim ersten Start der Erweiterung von PyPI installiert. Das `.mcpb`-Paket selbst enthält keine FFmpeg-Binärdatei.

- Wrapper `portable-ffmpeg`: MIT.
- Enthaltene Binärdateien: FFmpeg 9.0.2 (Build von Martin Riedl), lizenziert unter **GPL-3.0-or-later**, mit
  x264/x265 und weiteren Komponenten unter ihren eigenen Lizenzen.
- Quellcode und Lizenztexte der Binärdateien:
  https://github.com/mrkbac/portable-ffmpeg/releases/tag/ffmpeg-9.0.2-1

FFmpeg ist eine Marke von Fabrice Bellard, dem Begründer des FFmpeg-Projekts (https://ffmpeg.org). Dieses Projekt ist
nicht mit FFmpeg verbunden.

Bedeutung für die Weitergabe (keine Rechtsberatung): Weil FFmpeg nur als separates Programm aufgerufen wird, bleibt der
eigene Code MIT (GPL-FAQ „mere aggregation“). Solange das Bundle die Binärdatei nicht selbst enthält, verteilen
PyPI/der Paket-Maintainer die GPL-Binärdatei samt Quellcode. Würde die Binärdatei ins Bundle gelegt, müssten GPL-Text,
FFmpeg-Hinweise und der Quellcode-Link (oder ein schriftliches Angebot) mitgeliefert werden.

## Python-Abhängigkeiten

Alle weiteren Abhängigkeiten (mcp, pydantic, httpx, numpy, opencv-python-headless, pillow, python-docx, rapidfuzz)
stehen unter permissiven Lizenzen (MIT, BSD, Apache-2.0, HPND).
