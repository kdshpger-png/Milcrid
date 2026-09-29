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
    if not _hintergrund_gueltig(hintergrund):
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
        "abdunkeln": _abdunkeln_gueltig(daten.get("abdunkeln")),
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
    return {"erfolg": True, **_daten_laden(), "hintergrund_bilder": hintergrund_bilder()}


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
    (der bisherige Farbverlauf), "milcrid" (das vorhandene Start-Logo-Bild,
    siehe milcrid-splash.jpg) oder seit 29.09.2026 "bild:<Dateiname>" - ein
    eigenes Bild aus der Sammlung HINTERGRUND_ORDNER."""
    if not _hintergrund_gueltig(wert):
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


# ---- Eigene Hintergrundbilder (Klaus-Wunsch 29.09.2026) ----
# "Bilder sehen, kleine Ansicht wie jetzt Milcrid" und ein Bild vom PC als
# Hintergrund nehmen - "wenn man ein Bild im Internet hat, geht man auf
# speichern und fuegt es dann dem Hintergrund zu". Gewaehlte Bilder werden in
# eine eigene Sammlung KOPIERT: loescht Klaus das Original spaeter, bleibt der
# Hintergrund trotzdem. Entfernen legt sie in den Milcrid-Papierkorb.
HINTERGRUND_ORDNER = os.path.join(BASIS_ORDNER, "hintergruende")
BILD_ENDUNGEN = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif")
_HEIM = os.path.realpath(os.path.expanduser("~"))
# Wo Bilder "auf dem PC" ueblicherweise liegen - englische und deutsche Namen.
_SUCH_ORDNER = ("Pictures", "Bilder", "Downloads", "Desktop", "Schreibtisch", "Documents", "Dokumente")
_SUCH_TIEFE = 3          # Unterordner-Ebenen je Suchordner
_SUCH_HOECHSTENS = 300   # neueste zuerst; mehr braucht die Auswahl nicht
_MAX_GROESSE = 50 * 1024 * 1024


def _hintergrund_gueltig(wert):
    if wert in ("standard", "milcrid"):
        return True
    if isinstance(wert, str) and wert.startswith("bild:"):
        name = wert[5:]
        return (name == os.path.basename(name) and not name.startswith(".")
                and os.path.isfile(os.path.join(HINTERGRUND_ORDNER, name)))
    return False


def hintergrund_bilder():
    """Die eigene Sammlung, zuletzt hinzugefuegte zuerst: [{name, pfad}]."""
    try:
        namen = [n for n in os.listdir(HINTERGRUND_ORDNER)
                 if n.lower().endswith(BILD_ENDUNGEN) and not n.startswith(".")]
    except FileNotFoundError:
        return []
    pfade = [os.path.join(HINTERGRUND_ORDNER, n) for n in namen]
    pfade.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return [{"name": os.path.basename(p), "pfad": p} for p in pfade]


def bilder_auf_dem_pc():
    """Bilder in den ueblichen Ordnern, neueste zuerst: [{name, pfad, ordner}].
    Versteckte Ordner und die eigene Sammlung bleiben aussen vor."""
    funde = []
    for basis in _SUCH_ORDNER:
        wurzel = os.path.join(_HEIM, basis)
        if not os.path.isdir(wurzel) or os.path.islink(wurzel):
            continue
        for ordner, unter, dateien in os.walk(wurzel):
            tiefe = ordner[len(wurzel):].count(os.sep)
            unter[:] = [u for u in unter if not u.startswith(".")] if tiefe < _SUCH_TIEFE else []
            for d in dateien:
                if d.startswith(".") or not d.lower().endswith(BILD_ENDUNGEN):
                    continue
                pfad = os.path.join(ordner, d)
                try:
                    st = os.stat(pfad)
                except OSError:
                    continue
                if 0 < st.st_size <= _MAX_GROESSE:
                    funde.append((st.st_mtime, pfad))
    funde.sort(reverse=True)
    return [{"name": os.path.basename(p), "pfad": p,
             "ordner": os.path.relpath(os.path.dirname(p), _HEIM)}
            for _t, p in funde[:_SUCH_HOECHSTENS]]


def hintergrund_hinzufuegen(pfad):
    """Kopiert ein Bild vom PC in die Sammlung und macht es gleich zum Hintergrund."""
    import shutil
    echt = os.path.realpath(str(pfad or ""))
    if not echt.startswith(_HEIM + os.sep) or not os.path.isfile(echt):
        return {"erfolg": False, "fehler": "Das Bild gibt es nicht (mehr)."}
    if not echt.lower().endswith(BILD_ENDUNGEN):
        return {"erfolg": False, "fehler": "Das ist kein Bild, das Milcrid als Hintergrund kennt."}
    if os.path.getsize(echt) > _MAX_GROESSE:
        return {"erfolg": False, "fehler": "Das Bild ist größer als 50 MB."}
    os.makedirs(HINTERGRUND_ORDNER, exist_ok=True)
    stamm, endung = os.path.splitext(os.path.basename(echt))
    name, n = stamm + endung, 2
    while os.path.exists(os.path.join(HINTERGRUND_ORDNER, name)):
        name, n = f"{stamm} ({n}){endung}", n + 1
    ziel = os.path.join(HINTERGRUND_ORDNER, name)
    shutil.copyfile(echt, ziel)
    os.utime(ziel)            # "zuletzt hinzugefuegt" = vorne in der Reihe
    hintergrund_speichern("bild:" + name)
    return {"erfolg": True, "wert": "bild:" + name, "hintergrund_bilder": hintergrund_bilder()}


def hintergrund_entfernen(name):
    """Bild aus der Sammlung in den Milcrid-Papierkorb. War es der Hintergrund,
    gilt danach wieder der Farbverlauf."""
    import papierkorb_verwaltung
    name = str(name or "")
    pfad = os.path.join(HINTERGRUND_ORDNER, name)
    if name != os.path.basename(name) or not os.path.isfile(pfad):
        return {"erfolg": False, "fehler": "Das Bild ist nicht (mehr) in der Sammlung."}
    ergebnis = papierkorb_verwaltung.wegwerfen(pfad)
    if not ergebnis.get("erfolg"):
        return ergebnis
    if not _hintergrund_gueltig(_roh_hintergrund()):
        hintergrund_speichern("standard")
    return {"erfolg": True, **_daten_laden(), "hintergrund_bilder": hintergrund_bilder()}


# ---- Abdunkeln je Bild (Klaus 29.09.2026: "die Bilder sind als Hintergrund viel
# blasser") - bisher lag fest 60 % Dunkelblau ueber jedem Bild. Jetzt eine Stufe je
# Hintergrund, 0 bis 0.7; Milcrid-Bild behaelt seine gewohnten 60 %, eigene Bilder
# fangen bei 15 % an. ----
ABDUNKELN_MILCRID = 0.6
ABDUNKELN_EIGENES = 0.15
ABDUNKELN_MAX = 0.7


def _abdunkeln_gueltig(roh):
    if not isinstance(roh, dict):
        return {}
    return {k: round(min(max(float(v), 0.0), ABDUNKELN_MAX), 2) for k, v in roh.items()
            if isinstance(k, str) and isinstance(v, (int, float))}


def abdunkeln_speichern(wert, stufe):
    """Stufe (0 bis 0.7) fuer einen Hintergrund ("milcrid" oder "bild:<Datei>")."""
    if wert == "standard" or not _hintergrund_gueltig(wert):
        return {"erfolg": False, "fehler": "Für diesen Hintergrund gibt es kein Abdunkeln."}
    if not isinstance(stufe, (int, float)):
        return {"erfolg": False, "fehler": "Ungültige Stufe."}
    daten = _daten_laden()
    daten["abdunkeln"][wert] = round(min(max(float(stufe), 0.0), ABDUNKELN_MAX), 2)
    _schreiben(daten)
    return {"erfolg": True, "abdunkeln": daten["abdunkeln"]}


def hintergrund_umbenennen(alt, neu):
    """Eigenes Bild umbenennen (Klaus 29.09.2026: Google nennt Dateien "a713ba24-...",
    und per Sprache soll "Hintergrundbild Sonne" gehen). neu = Name OHNE Endung."""
    alt = str(alt or "")
    pfad = os.path.join(HINTERGRUND_ORDNER, alt)
    if alt != os.path.basename(alt) or not os.path.isfile(pfad):
        return {"erfolg": False, "fehler": "Das Bild ist nicht (mehr) in der Sammlung."}
    stamm = " ".join(str(neu or "").replace("/", " ").replace("\\", " ").split()).strip(". ")
    if not stamm:
        return {"erfolg": False, "fehler": "Der Name darf nicht leer sein."}
    if len(stamm) > 60:
        return {"erfolg": False, "fehler": "Der Name ist zu lang (höchstens 60 Zeichen)."}
    name = stamm + os.path.splitext(alt)[1].lower()
    if name == alt:
        return {"erfolg": True, **_daten_laden(), "hintergrund_bilder": hintergrund_bilder()}
    if any(os.path.splitext(n)[0].lower() == stamm.lower() for n in os.listdir(HINTERGRUND_ORDNER) if n != alt):
        return {"erfolg": False, "fehler": f"Es gibt schon ein Bild „{stamm}“."}
    zeit = os.path.getmtime(pfad)
    os.rename(pfad, os.path.join(HINTERGRUND_ORDNER, name))
    os.utime(os.path.join(HINTERGRUND_ORDNER, name), (zeit, zeit))   # Platz in der Reihe bleibt
    daten = _daten_laden_roh()
    if daten.get("hintergrund") == "bild:" + alt:
        daten["hintergrund"] = "bild:" + name
    ab = daten.get("abdunkeln")
    if isinstance(ab, dict) and ("bild:" + alt) in ab:
        ab["bild:" + name] = ab.pop("bild:" + alt)
    _schreiben({**_daten_laden(), **{k: daten[k] for k in ("hintergrund", "abdunkeln") if k in daten}})
    return {"erfolg": True, **_daten_laden(), "hintergrund_bilder": hintergrund_bilder()}


def _daten_laden_roh():
    try:
        with open(DATEN_PFAD, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def hintergrund_nach_name(name):
    """Hintergrund-Wert zu einem gesprochenen Namen ("Sonne", "Milcrid", "Standard"),
    sonst None. Vergleich ohne Gross/klein, Leerzeichen, Bindestriche, Umlaute."""
    def eng(t):
        t = str(t or "").lower()
        for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
            t = t.replace(a, b)
        return "".join(z for z in t if z.isalnum())
    g = eng(name)
    if not g:
        return None
    if g in ("standard", "farbverlauf", "normal"):
        return "standard"
    if g == "milcrid":
        return "milcrid"
    treffer = [b["name"] for b in hintergrund_bilder() if eng(os.path.splitext(b["name"])[0]) == g]
    if len(treffer) == 1:
        return "bild:" + treffer[0]
    # Verhoerer (Klaus 29.09.2026: "Bild Milcrid" -> Whisper "BuildMilkWrit"): aehnlichster
    # Name, aber nur eindeutig und ab 5 Buchstaben - sonst lieber nichts als das Falsche.
    import difflib
    kandidaten = [("milcrid", "milcrid"), ("standard", "standard")] + [
        (eng(os.path.splitext(b["name"])[0]), "bild:" + b["name"]) for b in hintergrund_bilder()]
    nah = [(difflib.SequenceMatcher(None, g, k).ratio(), w) for k, w in kandidaten if len(k) >= 5 and len(g) >= 5]
    nah = sorted([n for n in nah if n[0] >= 0.65], reverse=True)
    if nah and (len(nah) == 1 or nah[0][0] - nah[1][0] >= 0.1):
        return nah[0][1]
    return None


def _roh_hintergrund():
    try:
        with open(DATEN_PFAD, "r", encoding="utf-8") as f:
            return json.load(f).get("hintergrund")
    except Exception:
        return None
