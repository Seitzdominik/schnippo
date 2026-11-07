"""An invented take for tests: 36 sentences about baking bread, spoken at a steady pace, with retakes in sentences
21, 22, 26 and 28. No real recording behind it."""
from schnippo.models import AnalyzedTranscript, Clip
from schnippo.segments import segment

RETAKE = "Der Teig ruht danach zwölf Stunden im Kühlschrank und wird dadurch viel aromatischer."
SENTENCES = [
    "Heute backen wir gemeinsam ein einfaches Bauernbrot.",
    "Du brauchst dafür nur vier Zutaten aus dem Vorratsschrank.",
    "Mehl kaufe ich am liebsten direkt in der kleinen Mühle.",
    "Das Wasser sollte lauwarm sein und nicht zu heiß.",
    "Salz kommt erst nach zwanzig Minuten in die Schüssel.",
    "Die Hefe löst sich schneller auf, wenn du rührst.",
    "Eine große Holzschüssel hält die Wärme besonders gut.",
    "Knete alles zehn Minuten kräftig mit beiden Händen.",
    "Mit einer Küchenmaschine geht das natürlich etwas bequemer.",
    "Der Klebertest zeigt dir, wann die Masse fertig ist.",
    "Zieh ein Stück dünn auseinander und halte es ans Licht.",
    "Reißt es sofort, dann knetest du noch etwas weiter.",
    "Ein feuchtes Tuch schützt die Oberfläche vor dem Austrocknen.",
    "Im Winter stelle ich alles neben die Heizung.",
    "Nach einer Stunde hat sich das Volumen fast verdoppelt.",
    "Jetzt falten wir die Ränder vorsichtig zur Mitte.",
    "Dieser Schritt bringt Spannung in den runden Laib.",
    "Bemehle dein Gärkörbchen großzügig mit Roggenmehl.",
    "Lege den Laib mit dem Schluss nach oben hinein.",
    "Anfänger nehmen einfach eine Schüssel mit einem Geschirrtuch.",
    RETAKE,
    "Der Teig ruht danach zwölf Stunden im Kühlschrank und wird dadurch sehr aromatisch.",
    "Am nächsten Morgen heizt du den Ofen richtig vor.",
    "Ein gusseiserner Topf speichert die Hitze am besten.",
    "Stelle ihn gleich leer auf das unterste Gitter.",
    "Der Teig ruht dann zwölf Stunden im Kühlschrank und wird so viel aromatischer.",
    "Schneide die Oberseite mit einer scharfen Klinge ein.",
    "Der Teig ruht danach zwölf Stunden im Kühlschrank und wird dabei viel aromatischer.",
    "Dampf sorgt am Anfang für eine glänzende Kruste.",
    "Nach dreißig Minuten nimmst du den Deckel herunter.",
    "Jetzt bekommt das Brot seine dunkle Farbe.",
    "Klopfe auf den Boden, es muss hohl klingen.",
    "Lass es unbedingt eine Stunde auf dem Gitter auskühlen.",
    "Frisch angeschnitten wird die Krume sonst schnell klebrig.",
    "Butter und etwas grobes Meersalz genügen völlig.",
    "Schreib mir gern, wie dein erstes Brot geworden ist.",
]
RETAKES = (21, 22, 26, 28)


def words(pace: float = 0.32, gap: float = 1.1) -> list[dict]:
    """One entry per word, a pause between sentences."""
    out, t = [], 0.5
    for sentence in SENTENCES:
        for w in sentence.split():
            out.append({"id": f"w{len(out) + 1:04d}", "text": w, "start_s": round(t, 3), "end_s": round(t + pace - 0.04, 3)})
            t += pace
        t += gap
    return out


def analyzed() -> tuple[AnalyzedTranscript, float]:
    ws = words()
    duration = ws[-1]["end_s"] + 1.0
    entries = [{**w, "kind": "word", "confidence": 0.9, "flags": []} for w in ws]
    return AnalyzedTranscript(clip_id="c01", provider="fake", language="de", entries=entries), duration


def clip(duration: float) -> Clip:
    return Clip(id="c01", path="/x/take.mov", fingerprint="f", duration_s=duration, fps_num=30, fps_den=1,
                width=1920, height=1080, rotation=90)


def segments(cfg):
    at, duration = analyzed()
    return segment(at, cfg, duration), duration
