# Release

SemVer. Beta bis 1.0: `0.x.y`. Releases nicht als „Pre-release“ markieren, sonst findet der Update-Hinweis sie nicht (GitHub `releases/latest`).

1. Version in `pyproject.toml` und `src/schnippo/__init__.py` erhöhen, `uv lock`, `uv run python tools/build_plugin.py`.
2. `CHANGELOG.md` ergänzen. Der Abschnitt der Version wird Release-Text und Update-Hinweis.
3. Commit, dann `git tag v<version>` und `git push origin main v<version>`.

Die Action `release` prüft Tag und Version, startet `tools/check_public.py` als Pflichtschritt, vergleicht `plugin/`, lässt die Tests laufen, baut `.mcpb`, Wheel und sdist, startet das Wheel über `uvx` und hängt alles ans Release.

## Branch `stable`

Das Anthropic-Verzeichnis folgt dem Branch `stable`, nicht `main`. Die Action `release` setzt ihn als letzten Schritt auf den Release-Commit, nachdem das Paket auf PyPI liegt. So zeigt `plugin/.mcp.json` dort immer auf eine Version, die es gibt, und halbfertige Änderungen auf `main` erreichen das Verzeichnis nicht. Den Branch nicht von Hand ändern. Der Schritt schiebt nur vorwärts und schlägt fehl, wenn `stable` nicht im Release-Commit enthalten ist.

## PyPI einrichten (einmalig, nur du)

Der Name `schnippo` war am 7. November 2026 auf PyPI und TestPyPI frei. Die Action nutzt Trusted Publishing und kommt ohne Token aus.

1. Konten auf https://test.pypi.org und https://pypi.org anlegen, 2FA einschalten.
2. Auf beiden unter „Publishing“ → „Add a new pending publisher“ eintragen: Owner `Seitzdominik`, Repository `schnippo`, Workflow `release.yml`, Environment `testpypi` bzw. `pypi`.
3. Im GitHub-Repo unter Settings → Environments die Umgebungen `testpypi` und `pypi` anlegen.
4. Unter Settings → Secrets and variables → Actions → Variables `PYPI_PUBLISH` auf `testpypi` setzen und die Action `release` für den Tag von Hand starten.
5. Prüfen: `uvx --index https://test.pypi.org/simple/ --index-strategy unsafe-best-match schnippo`.
6. `PYPI_PUBLISH` auf `pypi` setzen, Action erneut starten, prüfen: `uvx schnippo`.

Eine Version lässt sich auf PyPI nicht ersetzen. Bei Fehlern kommt die nächste Patch-Version.

## Plattformen

Die `.mcpb` ist plattformübergreifend (Typ `uv`, eine Datei für macOS und Windows, etwa 14 MB). Python und die Abhängigkeiten holt uv beim ersten Start für das jeweilige System, ffmpeg bringt dabei das Wheel mit: etwa 24 MB auf Apple Silicon, 62 MB auf Windows. Die Action `ci` baut und startet alles auf beiden Systemen.

## Signatur der `.mcpb`

`mcpb sign --self-signed` läuft ohne Zertifikat durch, aber `mcpb verify` und `mcpb info` melden die Datei danach weiter als nicht signiert (geprüft mit mcpb 2.1.2). Selbstsignieren bringt also nichts, die Releases bleiben unsigniert. Eine echte Signatur braucht ein Zertifikat einer anerkannten Stelle, das kostet Geld. Ob Claude Desktop bei unsignierten Dateien einen Hinweis zeigt, steht nicht in der Dokumentation, die Installation funktioniert aber.
