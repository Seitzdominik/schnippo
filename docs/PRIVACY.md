# Datenschutzerklärung / Privacy Policy

Stand: 7. November 2026. Gilt für Schnippo ab Version 0.11.0.

Schnippo ist eine lokale Software. Herausgeber ist Seitz Dominik Visuals, https://sdv.design. Der Herausgeber betreibt keinen Server für Schnippo und erhält keine Daten von dir.

## Welche Daten verarbeitet werden

Schnippo verarbeitet auf deinem Rechner: Videos, Audio und Bilder aus den Ordnern, die du angibst, daraus abgeleitete Tonspuren, Einzelbilder, Transkripte und Analysen, deine Einstellungen und API-Keys. Es gibt keine Telemetrie, keine Nutzungsstatistik und keine Absturzberichte.

## Nutzung und Speicherung

Alles bleibt lokal, außer es steht im nächsten Abschnitt.

- Cache: `~/Library/Caches/schnippo`
- Einstellungen, Glossare, Marken-Angaben: `~/.config/schnippo`
- Exporte: Ordner `schnippo-export/` neben deinem Material
- Keys: Einstellungen der Erweiterung in Claude Desktop, macOS-Schlüsselbund, Umgebungsvariable oder deine `config.toml`. Keys werden nie protokolliert.

## Weitergabe an Dritte

| Empfänger | Daten | Wann | Grund |
|---|---|---|---|
| Gladia (`api.gladia.io`) | Tonspur, 16 kHz mono, ohne Metadaten, und deine Glossar-Begriffe | beim Transkribieren, mit deinem Key | dein Auftrag, dein Gladia-Konto |
| Dein KI-Anbieter, zum Beispiel Anthropic (Claude) | Transkripte, Schnittkontext, Dateinamen, Einzelbilder und Kontaktabzüge | während des Schnitts im Chat | dein Konto beim Anbieter |
| Freesound (`freesound.org`) | Suchbegriffe | nur auf Wunsch, mit deinem Key | dein Auftrag |
| ElevenLabs (`api.elevenlabs.io`) | Beschreibung eines Effekts | nur auf Wunsch, mit deinem Key | dein Auftrag |
| GitHub (`api.github.com`) | keine Inhalte, nur die Abfrage der neuesten Version; GitHub sieht dabei deine IP-Adresse | höchstens einmal am Tag, abschaltbar | Update-Hinweis |
| PyPI, GitHub, Playwright-CDN | keine Inhalte, nur Downloads von Abhängigkeiten | bei Installation und beim ersten Grafik-Render | Installation |

Für diese Dienste gelten deren eigene Datenschutzbestimmungen: [Gladia](https://www.gladia.io/privacy-policy), [Anthropic](https://www.anthropic.com/legal/privacy), [Freesound](https://freesound.org/help/privacy/), [ElevenLabs](https://elevenlabs.io/privacy-policy), [GitHub](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement).

Nutze Schnippo nur mit Material, das du diesen Diensten geben darfst. Das gilt besonders für Aufnahmen anderer Personen.

## Aufbewahrung

Lokale Daten bleiben, bis du sie löschst: mit dem Tool `clear_cache`, im Finder oder durch Deinstallieren der Erweiterung. Wie lange Gladia und dein KI-Anbieter Daten aufbewahren, bestimmen deren Bedingungen und dein Konto.

## Kontakt

Seitz Dominik Visuals, https://sdv.design. Fragen auch unter https://github.com/Seitzdominik/schnippo/issues.

---

## English summary

Schnippo is local software from Seitz Dominik Visuals, who run no server for it and receive no data. There is no telemetry.

- **Collection:** Schnippo processes your media, transcripts, settings and keys on your computer.
- **Use and storage:** everything stays in `~/Library/Caches/schnippo` and `~/.config/schnippo`, unless listed below.
- **Third parties:** audio goes to Gladia; transcripts, file names and frames go to your AI provider; search terms go to Freesound or ElevenLabs only on request and with your key; the update check calls GitHub at most daily and can be switched off.
- **Retention:** local data stays until you delete it with `clear_cache` or in the Finder. Third-party retention follows their terms.
- **Contact:** Seitz Dominik Visuals, https://sdv.design
