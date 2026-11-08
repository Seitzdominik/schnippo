# Übergabe-Prompt für Claude Code auf dem Windows-PC

Falls Schnippo auf Windows nicht läuft: Claude Code auf dem PC starten und alles unterhalb der Linie einfügen.

---

Hilf mir, Schnippo auf diesem Windows-PC zum Laufen zu bringen.

**Projekt.** Schnippo ist ein lokaler Python-MCP-Server, mit dem Claude Video in DaVinci Resolve Studio schneidet. Er liest einen Ordner mit Takes ein, transkribiert mit Gladia und baut nicht-destruktive Timelines aus den Originalclips. Der Server misst, Claude entscheidet redaktionell. Auf dem Mac läuft alles und ist mit Resolve 21.1.2 erprobt. Windows ist neu: Die automatischen Tests laufen in GitHub Actions auf Windows, aber ohne Resolve. Das Repository ist `https://github.com/Seitzdominik/schnippo`, Einstieg in den Code ist `src/schnippo/server.py`. Alles Plattformabhängige steht in `src/schnippo/platforms.py`, die Pfadregeln in `src/schnippo/guard.py`, der Zugriff auf Resolve in `src/schnippo/resolve_bridge.py`. Eine Liste der macOS-Annahmen steht in `docs/ENTWICKLUNG.md`, Abschnitt „Plattformen“. Python 3.14 kommt über uv, ffmpeg über das Paket `portable-ffmpeg-full`, Grafiken rendert Playwright mit Chromium. Keys liegen im Windows-Anmeldeinformationsspeicher über `keyring`, in der Erweiterung oder in `GLADIA_API_KEY`.

**Repository holen und lokal starten.**

```powershell
winget install --id=astral-sh.uv -e
git clone https://github.com/Seitzdominik/schnippo.git
cd schnippo
uv sync --extra motion
git config core.hooksPath .githooks
uv run pytest -q
$env:PYTHONUTF8 = "1"
uv run python tools/mcp_call.py check_setup "{}"
```

Mit `tools/mcp_call.py <tool> '<json>'` rufst du einzelne Tools wie ein MCP-Client auf.

**Reihenfolge der Diagnose.** Gehe sie von oben nach unten durch und höre an der ersten Stelle auf, die nicht geht. Dort suchst du die Ursache, belegst sie und behebst sie erst dann.

1. **Python und fusionscript:** Passt `uv run python -c "import struct,sys; print(sys.version, struct.calcsize('P')*8)"` (64 bit)? Liegt `fusionscript.dll` dort, wo `platforms.resolve_paths()` sucht? Lädt `DaVinciResolveScript`? Die README unter `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\` ist maßgeblich. Sagt ein Fehler, dass die DLL oder eine ihrer Abhängigkeiten fehlt, prüfe `os.add_dll_directory` und ob diese Python-Version zur DLL passt. Probiere dann uv-Pythons mit `uv run --python 3.13`, bevor du am Code änderst.
2. **Verbindung zu Resolve:** Läuft `Resolve.exe`? Steht External scripting auf Local? Ist es die Studio-Version? Antwortet `scriptapp("Resolve")`?
3. **ffmpeg:** `uv run python -c "from schnippo.media import find_tool; print(find_tool('ffmpeg'), find_tool('ffprobe'))"`.
4. **Gladia:** `check_setup` zeigt den Key-Status. Transkribieren kostet Geld: nur einen kurzen Clip und nur, wenn ich zugestimmt habe.
5. **Timeline-Bau:** erst harte Schnitte, ohne Grafiken. Stimmen Pfade, Bin `Schnippo/`, Framerate, Ton?
6. **Grafiken und Chromium:** `motion_setup`, dann eine Grafik. Transparenz prüfen.
7. **Render und Export.**

**Wo die Logs liegen.**

- Server-Log: `%APPDATA%\Claude\logs\mcp-server-Schnippo.log`, allgemein `%APPDATA%\Claude\logs\mcp.log`
- Resolve-Log: `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\logs\`. Prüfe den Ort, falls er in dieser Version abweicht.
- Einstellungen: `%APPDATA%\schnippo`, Cache: `%LOCALAPPDATA%\schnippo\Cache`

**Grundsätze, die immer gelten.**

- Nicht-destruktiv: Originalmedien nie verändern, verschieben oder löschen.
- In Resolve-Projekten von mir nichts löschen. Versuche nur in einem eigenen Testprojekt, das ich dir nenne. Vor jedem Bau prüfen, welches Projekt offen ist.
- Stürzt Resolve ab: Nicht wiederholen. Zuerst das Protokoll lesen und die Ursache belegen, Vermutungen als Vermutung benennen, weitere riskante Versuche mit mir absprechen.
- Keys nie ausgeben, loggen oder committen.
- Keine Testdaten, Screenshots mit Personen, Namen oder Medien committen. Vor jedem Commit läuft `uv run python tools/check_public.py`, der Hook macht das automatisch.
- `uv run pytest -q` muss vor jedem Commit grün sein. Neue Tests nur mit erfundenen Daten.

**Fixes zurück ins Repository.** Lege für jeden Fix einen eigenen Branch an (`windows/<thema>`), einen Commit je Thema, mit einem Test, wenn das ohne Resolve möglich ist. Öffne einen Pull Request gegen `main` und beschreibe darin Ursache, Beleg und Fix. Trage neue Erkenntnisse in `docs/ENTWICKLUNG.md` ein. Tag und Release mache ich selbst.

Fang mit Schritt 1 an und sag mir nach jedem Schritt kurz, was du gefunden hast.
