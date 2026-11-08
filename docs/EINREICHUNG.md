# Einreichung im Anthropic-Verzeichnis

Abgleich des Stands 0.13.0 mit der Doku vom 8. November 2026: [Submit a plugin](https://claude.com/docs/plugins/submit), [Plugin pre-submission checklist](https://claude.com/docs/plugins/pre-submission-checklist), [Connector submission](https://claude.com/docs/connectors/building/submission), [Plugin support by app](https://claude.com/docs/plugins/platform-support), [Software Directory Policy](https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy).

Status: ✅ erfüllt, ⚠️ offen, 👤 muss der Nutzer tun.

| Punkt | Status | Beleg |
|---|---|---|
| `plugin/.claude-plugin/plugin.json` vorhanden | ✅ | `plugin/` |
| Nur das Manifest in `.claude-plugin/` | ⚠️ | `icon.png` liegt dort |
| Keine Symlinks, LFS, `.DS_Store`, `.gitattributes` | ✅ | `git ls-files` |
| Größe: unter 50 MiB als Archiv, unter 10.000 Dateien | ✅ | 16,6 MB, 258 Dateien |
| Name, Anzeigename, Autor | ✅ | `plugin.json` |
| Beschreibung und Keywords englisch | ⚠️ | deutsch |
| README mit mindestens 40 Wörtern, Lizenz | ✅ | `plugin/README.md`, `plugin/LICENSE` |
| README ist der Eintrag im Verzeichnis: englisch | ⚠️ | deutsch |
| README nennt alles, was läuft, gesendet oder geladen wird | ⚠️ | fehlen: KI-Anbieter, Gegenhören, erstes Einlesen |
| Mindestens drei Beispiel-Prompts, Fehlerbehebung (Policy 3.C, 3.E) | ⚠️ | fehlen in `plugin/README.md` |
| Paket exakt angeheftet, Doku nennt `uvx <package>==1.2.3` | ⚠️ | `schnippo@0.13.0` |
| Kein `uv.toml` oder andere Paketquelle im Plugin | ✅ | `plugin/` |
| Keys über `userConfig` mit `sensitive` | ✅ | `plugin.json` |
| Cowork lädt den Server nur, wenn alle `user_config`-Felder einen Standardwert haben | ⚠️ | Key und Projektordner ohne Standard |
| Tool-Titel und Hinweise, Namen bis 64 Zeichen | ✅ | `src/schnippo/toolinfo.py`, `tests/test_release.py` |
| Einstufung jedes Tools geprüft | ⚠️ | `export_transcript` überschreibt frühere Exporte |
| Privacy Policy in README, `privacyPolicyUrl`, `privacy_policies` | ✅ | README, `plugin.json`, Manifest |
| Skill-Name englisch | ⚠️ | `rohschnitt` |
| Eigener verfolgter Branch `stable` | ⚠️ | fehlt |
| KI-erzeugtes Audio ist ausgeschlossen (Policy 4.B) | ⚠️ | optionale Funktion `generate_sfx` mit ElevenLabs |
| Eigene oder freigegebene Endpunkte (Policy 3.F) | 👤 | Gladia, Freesound sind Drittanbieter |
