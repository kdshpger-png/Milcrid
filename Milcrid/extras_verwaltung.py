# extras_verwaltung.py
# Portal-Bereich "Extras" (Klaus-Wunsch 2026-08-31): alles, was FEST zu
# Milcrid gehoert - Milcrids eigene kleine Anwendungen (Uhr, Rechner,
# Kalender) und kuenftig weitere wie ein Terminplaner oder der IP-Waechter.
#
# Warum ein eigener Bereich: die Milcrid-Anwendungen lagen bisher im
# App-Store bzw. unter "Meine Apps" - dort stehen aber FREMDE Programme, die
# Klaus selbst hinzufuegt. Milcrids eigene Sachen sind kein Zubehoer, sie
# gehoeren zum System ("das macht ansich keinen Sinn" sie in den App-Store
# zu legen, Klaus 2026-08-31).
#
# Jedes Extra hat einen An/Aus-Schalter, und der ist - wie bei den
# Faehigkeiten (siehe faehigkeiten_verwaltung.py) - der WIRKMECHANISMUS,
# keine blosse Anzeige: ist ein Extra aus, wird es im Portal nicht
# angeboten UND die KI kann es nicht oeffnen (siehe open_app in bridge.py,
# das milcridApps gegen diese Liste filtert). Das ist auch die Antwort auf
# die Frage, was mit Extras passiert, die jemand gar nicht brauchen kann -
# etwa ein IP-Waechter auf einem Rechner ohne eigenen Webserver: einfach
# ausgeschaltet lassen, dann ist er nirgends im Weg.

import json
import os

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEN_PFAD = os.path.join(BASIS_ORDNER, "extras.json")

# name -> Beschreibung fuers Portal.
#   art="milcridapp": oeffnet die gleichnamige Anwendung aus apps.json
#                     (Schluessel "milcridApps"), app_id ist deren id.
# Neue Extras hier eintragen - das Portal baut seine Liste daraus auf, es
# muss also nichts im HTML nachgezogen werden.
EXTRAS = {
    "uhr": {
        "titel": "Milcrid Uhr",
        "beschreibung": "Uhrzeit und Wecker",
        "icon": "🕐",
        "art": "milcridapp",
        "app_id": "uhr",
    },
    "rechner": {
        "titel": "Milcrid Rechner",
        "beschreibung": "Taschenrechner",
        "icon": "🧮",
        "art": "milcridapp",
        "app_id": "rechner",
    },
    "terminplaner": {
        "titel": "Milcrid Termine",
        "beschreibung": "Termine mit Erinnerung, Dateien und Notizen",
        "icon": "🗓️",
        "art": "milcridapp",
        "app_id": "terminplaner",
    },
    "notizen": {
        "titel": "Milcrid Notizen",
        "beschreibung": "Notizen – auch zu einem Datum oder Termin",
        "icon": "📝",
        "art": "milcridapp",
        "app_id": "notizen",
    },
    "kalender": {
        "titel": "Milcrid Kalender",
        "beschreibung": "Monatsübersicht über die Termine",
        "icon": "📅",
        "art": "milcridapp",
        "app_id": "kalender",
    },
    # Malprogramm (Klaus, 16.09.2026): Idee aufzeichnen und der lokalen oder
    # der Online-KI geben, siehe skizze_verwaltung.py.
    "skizze": {
        "titel": "Milcrid Skizze",
        "beschreibung": "Zeichnen und der KI zeigen, was daraus werden soll",
        "icon": "🎨",
        "art": "milcridapp",
        "app_id": "skizze",
    },
    # Editor, Bildbetrachter, Video (Klaus, 24.09.2026) - oeffnen auch die
    # Dateien aus dem Datei Manager (Einstellungen > Standardprogramme).
    # Abgeschaltet: dort nicht mehr angeboten, die Dateien gehen an das
    # naechste passende Programm.
    "editor": {
        "titel": "Milcrid Editor",
        "beschreibung": "Schnell etwas schreiben – oder .txt, .py & Co. öffnen",
        "icon": "📝",
        "art": "milcridapp",
        "app_id": "editor",
    },
    "bild": {
        "titel": "Milcrid Bildbetrachter",
        "beschreibung": "Bilder ansehen, blättern, drehen, speichern",
        "icon": "🖼️",
        "art": "milcridapp",
        "app_id": "bild",
    },
    "video": {
        "titel": "Milcrid Video",
        "beschreibung": "Videos und Musik abspielen",
        "icon": "🎬",
        "art": "milcridapp",
        "app_id": "video",
    },
    # Bedienungsanleitung fuer Menschen (Klaus, 24.09.2026): "was es ist, wie
    # es funktioniert, Tastaturbelegung - so was wie Wikipedia".
    "handbuch": {
        "titel": "Milcrid Handbuch",
        "beschreibung": "Was Milcrid ist, wie du es bedienst, alle Tasten",
        "icon": "📖",
        "art": "milcridapp",
        "app_id": "handbuch",
    },
    # Chat mit einer Online-KI ueber den eigenen API-Schluessel (Klaus,
    # 15.09.2026). Der Schalter hier nimmt nur das Fenster heraus - ob etwas
    # nach draussen geht, entscheidet der Schalter "Verbindung" im Fenster
    # (beim Start immer aus), siehe online_ki_verwaltung.py.
    "onlinechat": {
        "titel": "Milcrid Online KI",
        "beschreibung": "Chat mit Gemini, Claude & Co. über deinen API-Schlüssel",
        "icon": "🌐",
        "art": "milcridapp",
        "app_id": "onlinechat",
    },
    # art="portalfenster" (Klaus-Wunsch 2026-09-21): ein Fenster, das schon
    # IM Portal steckt, aber eine eigene Kachel bekommt - "Fenster wie
    # Einstellungen, aber mit Kachel, damit man es wo andocken kann, wenn man
    # es oefter benutzt". Von aussen nicht von einer Milcrid-App zu
    # unterscheiden: Kachel unter "Meine Apps", ziehbar auf einen blauen
    # Seiten-Button oder einen goldenen Punkt, Schalter hier, eigenes
    # Fenster. Der Unterschied ist nur, woher der Inhalt kommt (aus dem
    # Portal statt aus einer App-Datei) - siehe PORTALFENSTER im Portal.
    "papierkorb": {
        "titel": "Milcrid Papierkorb",
        "beschreibung": "Gelöschtes ansehen, zurückholen oder endgültig löschen",
        "icon": "\U0001f5d1\ufe0f",
        "art": "portalfenster",
        "app_id": "papierkorb",
    },
    "direktaufgaben": {
        "titel": "Milcrid Direkt Aufgaben",
        "beschreibung": "Aufträge mit Kürzel – anlegen, ändern, mit einem Klick ausführen",
        "icon": "\u25B6\ufe0f",
        "art": "portalfenster",
        "app_id": "direktaufgaben",
    },
    "dialogregeln": {
        "titel": "Milcrid Dialog-Regeln",
        "beschreibung": "Was Milcrid bei bekannten Fenstern vorschlägt – ansehen und ändern",
        "icon": "\U0001f6a6",
        "art": "portalfenster",
        "app_id": "dialogregeln",
    },
    # art="programm": ein eigenstaendiges Programm mit eigenem Fenster,
    # gestartet wie jede App unter "Meine Apps".
    #
    # Warum hier KEINE Portal-Ansicht (Klaus-Entscheidung 2026-08-31, nach
    # einem ersten Versuch als Portal-Bereich): eine Adressliste ist eine
    # TABELLE mit vielen hundert Zeilen, Sortierung, Mehrfachauswahl und
    # Detailfenster. Als Karten im Portal war das bei mehr als einer
    # Handvoll Eintraege unbrauchbar. Ein eigenes Fenster hat den Platz
    # dafuer - und der Gewinn ist ausserdem, dass es NUR EIN Programm gibt
    # (dasselbe laeuft auf cubi), statt zweier Fassungen, die auseinander
    # driften.
    "ipwaechter": {
        "titel": "IP-Wächter",
        "beschreibung": "Wer besucht deinen eigenen Webserver",
        "icon": "🛰️",
        "art": "programm",
        "exec": "python3 " + os.path.join(BASIS_ORDNER, "ip_waechter.py"),
        "desktop": os.path.expanduser("~/.local/share/applications/milcrid-ip-waechter.desktop"),
        # AUS als Standard: die allermeisten betreiben auf ihrem Rechner
        # keinen eigenen Webserver, dann gaebe es nichts zu sehen. Wer einen
        # hat, schaltet es ein.
        "standard_an": False,
    },
}

# Den IP-Waechter gibt es nur, wo er liegt - im oeffentlichen Paket fehlt er
# (Klaus 26.09.2026, GitHub). Ohne diese Zeilen stuende ein Extra im Portal,
# das beim Anklicken ins Leere startet.
if not os.path.exists(os.path.join(BASIS_ORDNER, "ip_waechter.py")):
    EXTRAS.pop("ipwaechter", None)

# Was fest zu Milcrid gehoert, ist standardmaessig AN - anders als bei den
# Faehigkeiten, wo eine neue Faehigkeit erst freigeschaltet werden muss.
# Begruendung: ein Extra oeffnet nur ein eigenes Fenster, es greift nicht
# nach aussen. Wer es nicht braucht, schaltet es ab.
_STANDARD_AN = True


def _daten_laden():
    try:
        with open(DATEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    return daten if isinstance(daten, dict) else {}


def _standard(name):
    """Voreinstellung je Extra - meist AN, einzelne koennen es ueberschreiben
    (z.B. der IP-Waechter, der ohne eigenen Webserver nichts anzuzeigen
    haette)."""
    return EXTRAS.get(name, {}).get("standard_an", _STANDARD_AN)


def ist_aktiv(name):
    return bool(_daten_laden().get(name, _standard(name)))


def info():
    daten = _daten_laden()
    return {"extras": [
        {"name": n, "titel": e["titel"], "beschreibung": e["beschreibung"],
         "icon": e["icon"], "art": e["art"], "app_id": e.get("app_id", ""),
         "exec": e.get("exec", ""), "desktop": e.get("desktop", ""),
         "an": bool(daten.get(n, _standard(n)))}
        for n, e in EXTRAS.items()
    ]}


def umschalten(name, an):
    if name not in EXTRAS:
        return {"erfolg": False, "fehler": f'Unbekanntes Extra "{name}".'}
    daten = _daten_laden()
    daten[name] = bool(an)
    with open(DATEN_PFAD, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2, sort_keys=True)
    return {"erfolg": True}


def app_id_aktiv(app_id):
    """Gehoert diese milcridApps-id zu einem eingeschalteten Extra? Von
    bridge.open_app benutzt, damit ein abgeschaltetes Extra auch fuer die
    KI wirklich weg ist und nicht nur im Portal versteckt."""
    for name, e in EXTRAS.items():
        if e.get("app_id") == app_id:
            return ist_aktiv(name)
    return True  # keine Zuordnung -> nicht von uns verwaltet, also erlauben
