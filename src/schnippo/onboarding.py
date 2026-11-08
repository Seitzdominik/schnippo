"""First start: short texts, Claude leads, the server keeps the state. In chat text, because cards of local extensions do not show in Claude Desktop."""

from __future__ import annotations

from . import prefs
from .branding import DISPLAY_NAME

HOW_PATH = "Pfad kopieren am Mac: Rechtsklick auf den Ordner, Wahltaste (⌥) halten, „… als Pfadname kopieren“ (oder ⌥⌘C im Finder)."


def instruction(state: dict) -> str:
    """Addition to the server instructions."""
    if state["onboarding"]["done"] or state["onboarding"]["later"]:
        return ""
    return "\n\nErster Start: biete kurz das Onboarding an (überspringbar), onboarding(step=\"willkommen\")."


def hint(state: dict, tool: str, first_call: bool) -> tuple[str | None, bool]:
    """Line for Claude in a tool result, and whether the state changed. First call of a session while nothing is decided; after „Später“ once at the next job; new things after an update."""
    ob = state["onboarding"]
    if tool == "onboarding":
        return None, False
    if ob["done"]:
        if first_call and ob.get("version", 0) < prefs.VERSION:
            news = [prefs.NEWS[v] for v in sorted(prefs.NEWS) if v > ob.get("version", 0)]
            ob["version"] = prefs.VERSION
            return ("Neu seit dem letzten Besuch, sag es dem Nutzer kurz: " + " ".join(news)) if news else None, True
        return None, False
    if ob["later"] == 0 and first_call:
        return "Erster Start: biete kurz das Onboarding an (überspringbar), onboarding(step=\"willkommen\").", False
    if ob["later"] == 1 and tool == "ingest_folder":
        ob["later"] = 2
        return "Der Nutzer hat das Onboarding verschoben: erinnere einmal kurz daran, danach nicht mehr.", True
    return None, False


def welcome() -> str:
    return (f"Hallo! {DISPLAY_NAME} schneidet aus deinen Takes einen Rohschnitt in DaVinci Resolve, mit Ton, Zooms, B-Roll, Grafiken und auf Wunsch Reels.\n"
            "Dafür brauchst du Resolve Studio und einen Gladia-Key für die Transkription. An deinen Originaldateien ändert sich nichts.\n"
            "Das Einrichten dauert 2–3 Minuten. Los, „Ich kenne mich aus“ oder „Später“?\n\n"
            "[Für Claude: Text fast wörtlich zeigen. Los → step=\"einrichtung\", „Ich kenne mich aus“ → step=\"kenne_mich_aus\", „Später“ → step=\"spaeter\".]")


def setup(open_points: list[str]) -> str:
    if not open_points:
        return "Einrichtung: alles bereit ✅\n\n[Für Claude: kurz sagen und gleich weiter mit step=\"vorlieben\".]"
    return ("Das fehlt noch:\n" + "\n".join(open_points) + "\n\n[Für Claude: Punkt für Punkt in Alltagssprache durchgehen, ein Punkt je Nachricht. Nach jeder Lösung step=\"einrichtung\" erneut aufrufen, "
            "dann weiter mit step=\"vorlieben\". Der Nutzer darf auch weitergehen und später zurückkommen.]")


def questions(saved: dict) -> str:
    return ("Ein paar kurze Fragen, die Empfehlung steht in Klammern. „Passt“ nimmt alle Empfehlungen.\n"
            "1. Was schneidest du meistens? Reels, YouTube, Kurse, Interviews, Werbung (automatisch erkennen)\n"
            "2. Tempo: ruhig, dicht (ausgewogen)\n"
            "3. Sprache der Aufnahmen (Deutsch)\n"
            "4. Grafiken an oder aus (an) · 5. Sound-Effekte: aus, normal (subtil)\n"
            "6. Optional: Ordner für deine Projekte, einfach den Pfad einfügen\n\n"
            "[Für Claude: Fragen gesammelt stellen. Antworten: step=\"vorlieben\", answers={\"format\", \"style\", \"language\", \"graphics\", \"sfx\", \"projects_folder\"}; "
            "„Passt“ = answers={}. Alles später im Chat änderbar." + (f" Schon gespeichert: {saved}." if saved else "") + "]")


LABEL = {"format": {"auto": "automatisch erkennen", "reel": "Reels", "youtube": "YouTube und Interviews", "course": "Kurse", "commercial": "Werbung"},
         "style": {"ruhig": "ruhig", "ruhig-dicht": "ausgewogen", "dicht": "dicht"}, "sfx": {"off": "aus", "subtil": "subtil", "normal": "normal"}}


def saved_text(p: dict, bad: list[str]) -> str:
    lines = [f"Gespeichert: {LABEL['format'].get(p['format'], p['format'])}, Tempo {LABEL['style'].get(p['style'], p['style'])}, Sprache {p['language']}, Grafiken {'an' if p['graphics'] else 'aus'}, "
             f"Sound-Effekte {LABEL['sfx'].get(p['sfx'], p['sfx'])}" + (f", Projekte in {p['projects_folder']}" if p.get("projects_folder") else ", kein Standardordner") + "."]
    lines.append("Das gilt für alle Jobs, du kannst es pro Job anders sagen.")
    if bad:
        lines.append("Nicht verstanden, bitte noch einmal: " + "; ".join(bad))
    nxt = "Bei Grafiken an fragen: „Design jetzt einrichten oder später?“ (jetzt → setup_design). " if p["graphics"] else ""
    return "\n".join(lines) + f"\n\n[Für Claude: {nxt}Dann fragen, ob der Nutzer die Aufnahme-Tipps sehen möchte (step=\"tipps\") oder direkt testen (step=\"test\").]"


def tips() -> str:
    return ("So wird dein Material gut schneidbar:\n"
            "1. Vor und nach jedem Take 1 Sekunde ruhig in die Kamera schauen\n"
            "2. Bei einem Versprecher den ganzen Satz neu sprechen\n"
            "3. Das Wort „nochmal“ sagen, dann findet das Tool den Neuanfang\n"
            "4. Ansteckmikro nutzen · 5. Ruhiger Raum, Fenster zu\n"
            "6. Für Reels in 4K filmen: Dann bleibt beim Zuschnitt auf Hochformat genug Schärfe\n\n"
            "[Für Claude: weiter mit step=\"test\".]")


def test_question() -> str:
    return ("Hast du einen kurzen Clip (1–3 Minuten) zum Ausprobieren? Nenne den Ordner, dann sage ich dir vorher, was es kostet.\n" + HOW_PATH + "\n\n"
            "[Für Claude: Antwort → step=\"test\", answers={\"folder\": …}. Kein Clip → step=\"abschluss\". Es gibt kein Demo-Material.]")


def test_estimate(line: str, clips: int) -> str:
    return (f"{clips} Clip(s) gefunden. {line}\nSoll ich loslegen?\n\n"
            "[Für Claude: Erst nach dem OK des Nutzers transcribe aufrufen, dann der normale Ablauf im erkannten Format bis zum Export. Danach step=\"abschluss\".]")


def cheat_sheet(projects_folder=None) -> str:
    start = "„Schneide das Projekt … als Reel / YouTube-Video“ (der Name reicht)" if projects_folder else "„Schneide den Ordner … als Reel / YouTube-Video“"
    return ("So sprichst du mit mir:\n"
            f"• {start}\n"
            "• „Mach aus dem Video 3 Reels“\n"
            "• „Schnitt 5 ist zu früh“ · „Bei 0:23 den anderen Take“ · „Grafik bei 1:10 raus“\n"
            "• „Design ändern“ · „Richte mich ein“ · „Onboarding wiederholen“\n"
            "Neues Projekt: „Leg ein Projekt Kunde Thema an“ erzeugt die Ordner A-Roll, B-Roll, Bilder und Skript plus glossar.txt und brief.md.\n"
            + HOW_PATH)


def finish(state: dict, projects_folder=None) -> str:
    state["onboarding"].update({"done": True, "version": prefs.VERSION})
    return "Fertig eingerichtet! Dein Spickzettel:\n" + cheat_sheet(projects_folder)


def later(state: dict) -> str:
    state["onboarding"]["later"] = 1
    return "Alles klar, dann später. Ich erinnere dich höchstens noch einmal beim nächsten Job. „Onboarding wiederholen“ geht jederzeit."


def repeat(state: dict) -> str:
    """Stays done: breaking off a repeat must not bring back the first-start note."""
    if not state["onboarding"]["done"]:
        state["onboarding"]["later"] = 0
    return welcome()
