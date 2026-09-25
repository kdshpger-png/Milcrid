# theme_verwaltung.py
# Einstellungen > Farbauswahl Portal: speichert das gewaehlte Portal-Thema
# (Regler-Farbton oder Grau/Schwarz) serverseitig, damit es einen Neustart
# uebersteht - vorher stand die Auswahl nur im DOM/CSS des Portal-Fensters
# und war nach jedem Neuladen wieder auf Blau zurueckgesetzt (Klaus-Bug
# 2026-08-25).
#
# "hue" deckt sowohl den Regler als auch den Blau-Punkt ab (Blau ist einfach
# hue=208, siehe BLAU_HUE in milcrid_portal.html), Grau/Schwarz sind eigene
# feste Modi ohne Farbton.
#
# Seit 2026-09-05 zwei weitere, UNABHAENGIGE Einstellungen dazu (Klaus-
# Wunsch: Seiten-Buttons in einer eigenen Farbe, Milcrid-Bild als
# Hintergrund) - alle drei liegen in derselben Datei, aber
# speichern()/button_speichern()/hintergrund_speichern() lesen den
# jeweils aktuellen Stand ERST und schreiben ihn dann mit der eigenen
# Aenderung zurueck, statt die Datei jedes Mal komplett neu aufzubauen -
# sonst wuerde z.B. das Setzen der Button-Farbe die Hintergrund-Wahl
# ueberschreiben.

import json
import os

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEN_PFAD = os.path.join(BASIS_ORDNER, "theme.json")

_STANDARD = {
    "modus": "hue", "hue": 208,
    "button_modus": "hue", "button_hue": 208,
    "hintergrund": "standard",
    "schrift_modus": "hue", "schrift_hue": 42,
    "schriftart": "",
    "gold_modus": "hue", "gold_hue": 42,
}


def _daten_laden():
    try:
        with open(DATEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    if not isinstance(daten, dict):
        daten = {}
    modus = daten.get("modus")
    if modus not in ("hue", "grau", "schwarz"):
        modus = _STANDARD["modus"]
    hue = daten.get("hue")
    if not isinstance(hue, (int, float)):
        hue = _STANDARD["hue"]
    button_modus = daten.get("button_modus")
    if button_modus not in ("hue", "grau", "schwarz"):
        button_modus = _STANDARD["button_modus"]
    button_hue = daten.get("button_hue")
    if not isinstance(button_hue, (int, float)):
        button_hue = _STANDARD["button_hue"]
    hintergrund = daten.get("hintergrund")
    if hintergrund not in ("standard", "milcrid"):
        hintergrund = _STANDARD["hintergrund"]
    schrift_modus = daten.get("schrift_modus")
    if schrift_modus not in ("hue", "schwarz", "weiss"):
        schrift_modus = _STANDARD["schrift_modus"]
    schrift_hue = daten.get("schrift_hue")
    if not isinstance(schrift_hue, (int, float)):
        schrift_hue = _STANDARD["schrift_hue"]
    schriftart = daten.get("schriftart")
    if not _schriftart_gueltig(schriftart):
        schriftart = _STANDARD["schriftart"]
    gold_modus = daten.get("gold_modus")
    if gold_modus not in ("hue", "grau", "schwarz"):
        gold_modus = _STANDARD["gold_modus"]
    gold_hue = daten.get("gold_hue")
    if not isinstance(gold_hue, (int, float)):
        gold_hue = _STANDARD["gold_hue"]
    return {
        "modus": modus, "hue": hue,
        "button_modus": button_modus, "button_hue": button_hue,
        "hintergrund": hintergrund,
        "schrift_modus": schrift_modus, "schrift_hue": schrift_hue,
        "schriftart": schriftart,
        "gold_modus": gold_modus, "gold_hue": gold_hue,
    }


def _schriftart_gueltig(name):
    """Leer = Standard. Sonst ein Name aus fc-list - er landet im Portal in
    einer CSS-Variable ("Name", var(--sans)), darum keine Zeichen, die dort
    aus den Anfuehrungszeichen ausbrechen koennten."""
    return (isinstance(name, str) and len(name) <= 100
            and not any(z in name for z in '"\\;{}<>\n\r'))


def _schreiben(daten):
    with open(DATEN_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)


def info():
    return {"erfolg": True, **_daten_laden()}


def speichern(modus, hue=None):
    if modus not in ("hue", "grau", "schwarz"):
        return {"erfolg": False, "fehler": f'Unbekannter Theme-Modus "{modus}".'}
    daten = _daten_laden()
    daten["modus"] = modus
    daten["hue"] = hue if isinstance(hue, (int, float)) else daten["hue"]
    _schreiben(daten)
    return {"erfolg": True}


def button_speichern(modus, hue=None):
    """Einstellungen > Farben > Button-Farbe (Klaus-Wunsch 2026-09-05):
    eigener Modus/Farbton NUR fuer die Seiten-Buttons (--sb-btn* im
    Portal-Skript), unabhaengig vom grossen Portal-Thema oben. Gleiches
    Prinzip wie speichern() oben, inklusive Blau/Grau/Schwarz-Punkten -
    Klaus-Wunsch 2026-09-05: "wie Farbe Portal die 2 anderen Farben"."""
    if modus not in ("hue", "grau", "schwarz"):
        return {"erfolg": False, "fehler": f'Unbekannter Button-Modus "{modus}".'}
    daten = _daten_laden()
    daten["button_modus"] = modus
    daten["button_hue"] = hue if isinstance(hue, (int, float)) else daten["button_hue"]
    _schreiben(daten)
    return {"erfolg": True}


def hintergrund_speichern(wert):
    """Einstellungen > Hintergrund (Klaus-Wunsch 2026-09-05): "standard"
    (der bisherige Farbverlauf) oder "milcrid" (das vorhandene Start-Logo-
    Bild als Hintergrund, siehe milcrid-splash.jpg). Bewusst NUR diese
    zwei Werte - ein eigenes Bild hochladen ist fuer spaeter vorgemerkt."""
    if wert not in ("standard", "milcrid"):
        return {"erfolg": False, "fehler": f'Unbekannter Hintergrund "{wert}".'}
    daten = _daten_laden()
    daten["hintergrund"] = wert
    _schreiben(daten)
    return {"erfolg": True}


def schrift_speichern(modus, hue=None):
    """Einstellungen > Farben > Schriftfarbe (Knopf-Beschriftung, --btn-text):
    stand bis 21.09.2026 nur im DOM und fiel bei jedem Neuladen auf Gold
    zurueck (Klaus' Zwickmuehle: Farbe aendern nimmt das Start-Logo,
    Neuladen nimmt die Farbe). "hue" = Regler bzw. Gold (42), dazu die zwei
    festen Punkte Schwarz/Weiss."""
    if modus not in ("hue", "schwarz", "weiss"):
        return {"erfolg": False, "fehler": f'Unbekannte Schriftfarbe "{modus}".'}
    daten = _daten_laden()
    daten["schrift_modus"] = modus
    daten["schrift_hue"] = hue if isinstance(hue, (int, float)) else daten["schrift_hue"]
    _schreiben(daten)
    return {"erfolg": True}


def schriftart_speichern(name):
    """Einstellungen > Schrift > Schriftart (--btn-font), leer = Standard.
    Gleiche Luecke wie bei der Schriftfarbe, am selben Tag geschlossen."""
    if not _schriftart_gueltig(name):
        return {"erfolg": False, "fehler": "Diesen Schriftnamen kann ich nicht speichern."}
    daten = _daten_laden()
    daten["schriftart"] = name
    _schreiben(daten)
    return {"erfolg": True}


def gold_speichern(modus, hue=None):
    """Einstellungen > Farben > Goldene Button-Farbe (Klaus-Wunsch
    2026-09-21): die goldenen Punkte an der Eingabeleiste, unabhaengig von
    Portal- und blauer Button-Farbe. "hue" = Regler bzw. Gold (42)."""
    if modus not in ("hue", "grau", "schwarz"):
        return {"erfolg": False, "fehler": f'Unbekannte Farbe für die goldenen Knöpfe "{modus}".'}
    daten = _daten_laden()
    daten["gold_modus"] = modus
    daten["gold_hue"] = hue if isinstance(hue, (int, float)) else daten["gold_hue"]
    _schreiben(daten)
    return {"erfolg": True}
