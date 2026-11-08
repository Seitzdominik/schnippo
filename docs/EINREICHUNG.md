# Einreichung im Anthropic-Verzeichnis

Stand 0.13.1, abgeglichen am 8. November 2026 mit [Submit a plugin](https://claude.com/docs/plugins/submit), [Plugin pre-submission checklist](https://claude.com/docs/plugins/pre-submission-checklist), [Connector submission](https://claude.com/docs/connectors/building/submission), [Plugin support by app](https://claude.com/docs/plugins/platform-support), [Manifest reference](https://code.claude.com/docs/en/plugins-reference) und [Software Directory Policy](https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy). Die Regeln ändern sich, vor der Einreichung kurz gegenlesen.

Status: ✅ erfüllt, ⚠️ offen, 👤 muss der Nutzer tun. Die Tests stehen in `tests/test_plugin_listing.py`.

## 1. Status-Checkliste

### Ordner und Repository

| Punkt | Status | Beleg |
|---|---|---|
| `plugin/.claude-plugin/plugin.json`, nur das Manifest in diesem Ordner | ✅ | Test `test_only_the_manifest_lives_in_claude_plugin` |
| Keine Symlinks, LFS, `.gitattributes`, Systemdateien | ✅ | Test `test_directory_file_rules`, `git ls-files` |
| Repository unter 50 MiB als Archiv, unter 10.000 Dateien | ✅ | 16,6 MB, 274 Dateien |
| Dateien im Plugin unter 256 KiB, nur Text und Bilder | ✅ | Test, Ordner 128 KB |
| Repository öffentlich | ✅ | https://github.com/Seitzdominik/schnippo |
| Verfolgter Branch `stable` | ✅ | `.github/workflows/release.yml`, `docs/RELEASE.md` |

### Manifest und Eintrag

| Punkt | Status | Beleg |
|---|---|---|
| Name, Anzeigename, Autor, Version, Beschreibung, Icon | ✅ | `plugin/.claude-plugin/plugin.json` |
| Beschreibung, Keywords, Einstellungen englisch | ✅ | Test `test_listing_texts_are_english`, `packaging/manifest.template.json` |
| README mit mindestens 40 Wörtern, Eintrag englisch, deutsche Fassung am Ende | ✅ | `plugin/README.md` |
| Lizenz | ✅ | `plugin/LICENSE`, `license` im Manifest |
| Mindestens drei Beispiel-Prompts, Fehlerbehebung (Policy 3.C, 3.E) | ✅ | `plugin/README.md`, Test |
| Skills englisch benannt | ✅ | `plugin/skills/rough-cut/` |
| `claude plugin validate ./plugin --strict` | ✅ | ✔ Validation passed, Claude Code 2.1.317 |

### Start und Sicherheit

| Punkt | Status | Beleg |
|---|---|---|
| Paket exakt angeheftet | ✅ | `uvx schnippo==0.13.1`, Test `test_package_is_pinned_to_this_release` |
| Keine eigene Paketquelle im Plugin | ✅ | Test |
| Keys nur über `userConfig` mit `sensitive` | ✅ | Test `test_keys_are_asked_for_and_marked_sensitive` |
| Alle Netzwerkziele im README | ✅ | Test `test_readme_names_every_network_destination` |
| Grafiken ohne Netzwerk | ✅ | `src/schnippo/mg/render.py:103`, live: `fetch` auf http und https blockiert |
| Keine Secrets, auch nicht in der Historie | ✅ | `tools/check_public.py --history` |
| Nachgeladener Code nur aus dokumentierten Paketen | ✅ | `src/schnippo/deps.py` (Version aus dem Release, Hash geprüft), `motion_setup` |
| Tool-Titel und Hinweise, Einstufung geprüft | ✅ | `src/schnippo/toolinfo.py`, vier Tests |
| Cache löschen nur mit Bestätigung | ✅ | `clear_cache(confirm=false)`, Test |
| Abhängigkeiten aktuell (Policy 5.G) | ✅ | `uv tree --outdated`: OpenCV 4.14 statt 5.0 bewusst, sonst aktuell bis auf ein Patch-Release von pydantic |
| Installation aus dem GitHub-Repo in frischer Umgebung | ✅ | Abschnitt „Installationstest“ |
| Start aus PyPI mit genau dieser Version | ⚠️ | erst nach dem Tag möglich, siehe Abschnitt 2 |

### Datenschutz

| Punkt | Status | Beleg |
|---|---|---|
| Abschnitt „Privacy Policy“ mit beiden URLs | ✅ | `README.md`, `plugin/README.md`, Test |
| `privacyPolicyUrl`, `privacy_policies` | ✅ | `plugin.json`, `packaging/manifest.template.json` |
| Erhebung, Nutzung, Dritte, Aufbewahrung, Kontakt | ✅ | `plugin/README.md`, `docs/PRIVACY.md` |
| Website stimmt mit dem Verhalten überein | ⚠️ | Abweichungen unten, Website-Chat |

### Entscheidungen und Punkte für das Review

| Punkt | Status | Beleg |
|---|---|---|
| KI-erzeugtes Audio ist nicht erlaubt (Policy 4.B) | ⚠️ 👤 | `generate_sfx` nutzt ElevenLabs. Empfehlung: im Plugin abschalten |
| Eigene oder freigegebene Endpunkte (Policy 3.F) | ⚠️ | Gladia und Freesound sind Drittdienste, mit eigenem Key des Nutzers. Das kann im Review eine Frage auslösen |
| Paket aus einer Registry | Erwartet | Meldung „Runs a pinned npx or uvx package“ führt immer zum Review durch einen Menschen, sie ist keine Ablehnung |
| Testkonto mit Beispieldaten (Policy 3.D) | 👤 | Das Plugin-Formular fragt laut Doku nicht danach. Falls doch: Resolve Studio und eigenes Material sind nötig, `check_setup` läuft auch ohne |

### Wo das Plugin läuft

| Oberfläche | Verhalten |
|---|---|
| Claude Code, auch der Code-Tab in Claude Desktop | lädt und fragt nach den Einstellungen |
| Cowork auf dem eigenen Rechner | lädt laut Doku, fragt nichts ab. Darum haben alle Felder Standardwerte. Nicht getestet |
| Chat auf claude.ai und in Claude Desktop | ignoriert lokale Server. Dafür bleibt die `.mcpb` aus den Releases |

### Installationstest

Getestet am 8. November 2026 auf macOS mit eigenem `HOME`, eigener Claude-Konfiguration und leerem uv-Cache. Weil 0.13.1 erst mit dem Tag auf PyPI liegt, kam nur das Paket Schnippo aus einem lokalen Wheel (`UV_FIND_LINKS`), alle Abhängigkeiten aus PyPI.

- `claude plugin marketplace add Seitzdominik/schnippo` und `claude plugin install schnippo@schnippo`: ok, vier Skills und ein Server.
- Kaltstart bis zur ersten Antwort: 32,6 s. Claude Code bricht bei 30 s ab und zeigt „Failed to connect“. Beim zweiten Versuch verbindet es, danach 0,4 s. Ein Limit lässt sich im Plugin nicht setzen, nur mit `MCP_TIMEOUT`. Das README beschreibt „Reconnect“.
- `check_setup`: läuft, 59 Tools, nennt den fehlenden Key und `store_api_key`.
- Einstellungen: leere Felder kommen leer an, `format` und `projects_folder` kommen im Server an.

### Key im Plugin

1. Claude Code fragt beim Aktivieren nach dem Key oder mit `/plugin configure schnippo@<marketplace>`. Der Wert liegt im sicheren Speicher des Systems und kommt als `GLADIA_API_KEY` beim Server an.
2. Ohne Eintrag: „Richte mich ein“. `store_api_key` öffnet ein Systemfenster und speichert in Schlüsselbund oder Anmeldeinformationsverwaltung. Der Key läuft nie durch den Chat.
3. Der Code-Tab in Claude Desktop verhält sich wie Claude Code. Der Chat startet das Plugin nicht.

Nicht getestet: ein echter sensibler Wert, weil Claude Code ihn in den echten Schlüsselbund schreibt, und das echte Eingabefenster von `store_api_key`. Die Speicherlogik ist mit Unit-Tests abgedeckt. 👤 Einmal prüfen: Plugin installieren, Key eintragen, `check_setup` meldet ihn als gültig.

### Abweichungen auf der Website (nicht geändert)

1. Downloads von PyPI passieren auch beim ersten Einlesen, die Seiten nennen nur Installation und ersten Grafik-Render.
2. Gladia bekommt auch beim Gegenhören des fertigen Schnitts Ton, die Seiten nennen nur das Transkribieren.
3. Als Speicherort der Keys fehlen die Plugin-Einstellungen in Claude Code. „Deinstallieren der Erweiterung“ gilt auch für das Plugin.
4. Der Abschnitt „Kontaktaufnahme“ fehlt in der englischen Fassung.
5. Es fehlt der Satz, dass Schnippo nicht für Personen unter 18 gedacht ist. Das Formular fragt danach.

## 2. Was du noch tun musst, in dieser Reihenfolge

1. ✅ Repository öffentlich schalten: erledigt.
2. 👤 Entscheiden, was mit `generate_sfx` im Plugin passiert (Policy 4.B).
3. 👤 OK für den Tag `v0.13.1`. Die Action veröffentlicht auf PyPI und setzt `stable`. Bis dahin steht `stable` auf 0.11.0, also erst danach einreichen.
4. 👤 Key im Plugin einmal prüfen, siehe oben.
5. 👤 Auf claude.ai GitHub verbinden, in derselben Organisation, mit Schreibrechten auf das Repository.
6. 👤 Portal https://claude.ai/directory/manage → Submit new → **Plugin bundle**: Repository `Seitzdominik/schnippo`, Plugin path `plugin`, Branch or tag `stable`. Dann Validate.
7. 👤 Listing details prüfen, Data handling und Compliance mit den Antworten aus Abschnitt 3, unter „How new versions reach the directory“ den GitHub push webhook lassen, Submit for review.

## 3. Antworten zum Kopieren

**Data handling: personal data**

> Yes. Schnippo processes the user's own video, audio and images on the user's computer, and stores transcripts, analyses, settings and API keys locally. Recordings can contain the voices and faces of people.

**Data handling: other services**

> Yes, with the user's own accounts and keys: Gladia (audio track and glossary terms, for transcription), the user's AI provider such as Anthropic (transcripts, editing context, file names, frames and contact sheets), and on request only Freesound (search terms) and ElevenLabs (description of a sound effect). GitHub receives a version query at most once a day, which can be switched off. PyPI, GitHub and the Playwright CDN are used for downloads only. The publisher runs no server and receives no data. There is no telemetry.

**Data handling: retention**

> Local data stays on the user's computer until the user deletes it with the clear_cache tool, in the Finder or Explorer. Gladia and the user's AI provider keep data according to their own terms and the user's account.

**Data handling: intended for people under 18**

> No.

**Compliance:** Kontakt-E-Mail `dominik@sdv.design`, dann alle vier Bestätigungen selbst lesen und setzen.

Datenschutz: https://schnippo.com/en/privacy/ · Doku: https://github.com/Seitzdominik/schnippo#readme · Support: https://github.com/Seitzdominik/schnippo/issues

## 4. Updates nach der Veröffentlichung

1. Version in `pyproject.toml` und `src/schnippo/__init__.py` erhöhen, `uv lock`, `uv run python tools/build_plugin.py`, `CHANGELOG.md` ergänzen.
2. Commit, Tag `v<version>`, Push. Die Action baut, veröffentlicht auf PyPI und setzt `stable` nach, siehe `docs/RELEASE.md`.
3. Das Verzeichnis merkt den neuen Commit über den Webhook oder den Zeitplan, prüft ihn und veröffentlicht ihn nach der gewählten Einstellung. Standard: Du wählst „Publish“, ein Reviewer veröffentlicht. Bis dahin bleibt die alte Version live.
4. Ändern sich Funktionen, Tool-Beschreibungen, Datenwege oder Ziele wesentlich, Anthropic informieren (Policy 3.H).

## Key beim Update der `.mcpb`

Claude Desktop legt Key und Einstellungen unter der Kennung der Erweiterung ab: `Claude Extensions Settings/local.mcpb.<autor>.<name>.json`. Autor und Name bleiben ab 0.11.0 gleich, deshalb sollte alles erhalten bleiben. Das ist beobachtet, nicht mit zwei Versionen getestet.
