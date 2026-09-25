# profiles.py
# Personen- und Institutionen-Gedaechtnis fuer Milcrid.
# Legt Profile als einzelne .json-Dateien im Ordner "profiles/" an,
# liest sie, erweitert sie und durchsucht sie.
#
# Aufteilung der Aufgaben:
#   - Anlegen / Erweitern   -> Modell ruft create_or_update_profile() als Werkzeug
#   - Suchen (Institution)  -> Modell ruft search_profile() als Werkzeug
#   - Laden im Chat          -> Code ruft kontext_fuer_eingabe() bei JEDER Eingabe

import os
import re
import json
from datetime import date

# Wurzel wie in bridge.py (~/Milcrid), darunter der eigene Profil-Ordner.
BASE_DIR = os.path.realpath(os.path.expanduser("~/Milcrid"))
PROFIL_ORDNER = os.path.join(BASE_DIR, "profiles")


def _ordner_sicherstellen():
    os.makedirs(PROFIL_ORDNER, exist_ok=True)


def _dateiname(name):
    # Aus "Herr Mueller" wird "herr_mueller.json". Umlaute bleiben erhalten.
    klein = (name or "").strip().lower()
    sauber = re.sub(r"[^\w]+", "_", klein, flags=re.UNICODE).strip("_")
    return (sauber or "unbenannt") + ".json"


def _profil_pfad(name):
    return os.path.join(PROFIL_ORDNER, _dateiname(name))


def profil_existiert(name):
    return os.path.exists(_profil_pfad(name))


def profil_laden(name):
    pfad = _profil_pfad(name)
    if not os.path.exists(pfad):
        return None
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _daten_lesen(data):
    # Macht aus dem 'data'-Argument des Modells ein dict.
    # Schlaegt JSON fehl, landet der Text als Notiz - nichts geht verloren.
    if isinstance(data, dict):
        return data
    text = (data or "").strip()
    if not text:
        return {}

    # Falls das Modell ```json ... ``` drumherum schreibt
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    # 1. Versuch: sauberes JSON
    try:
        geladen = json.loads(text)
        if isinstance(geladen, dict):
            return geladen
    except Exception:
        pass

    # 2. Versuch: typische Modell-Fehler glaetten
    repariert = text.replace("'", '"')
    repariert = re.sub(r",\s*([}\]])", r"\1", repariert)  # Komma vor } oder ]
    try:
        geladen = json.loads(repariert)
        if isinstance(geladen, dict):
            return geladen
    except Exception:
        pass

    # 3. Fallback: als Notiz behalten
    return {"notizen": text}


def _tief_mergen(alt, neu):
    # Fuegt 'neu' in 'alt' ein. Wenn-Dann:
    #   dict + dict        -> rekursiv
    #   Liste beteiligt    -> zusammenfuehren, Duplikate raus (so wachsen z.B.
    #                         Ansprechpartner, statt sich zu ueberschreiben)
    #   sonst (Skalar)     -> neuer Wert ueberschreibt
    for schluessel, wert in neu.items():
        if schluessel not in alt:
            alt[schluessel] = wert
            continue
        vorhanden = alt[schluessel]
        if isinstance(vorhanden, dict) and isinstance(wert, dict):
            _tief_mergen(vorhanden, wert)
        elif isinstance(vorhanden, list) or isinstance(wert, list):
            liste = list(vorhanden) if isinstance(vorhanden, list) else [vorhanden]
            zusatz = wert if isinstance(wert, list) else [wert]
            for element in zusatz:
                if element not in liste:
                    liste.append(element)
            alt[schluessel] = liste
        else:
            alt[schluessel] = wert
    return alt


# --- Werkzeuge fuer das Modell ---

def create_or_update_profile(name="", data=""):
    # Legt ein Profil an oder erweitert ein bestehendes.
    name = (name or "").strip()
    if not name:
        return "[Profil] Kein Name angegeben - nichts gespeichert."

    _ordner_sicherstellen()
    neu = _daten_lesen(data)

    pfad = _profil_pfad(name)
    existierte = os.path.exists(pfad)
    profil = profil_laden(name) or {}

    profil.setdefault("name", name)
    _tief_mergen(profil, neu)

    heute = date.today().isoformat()
    profil.setdefault("erstellt_am", heute)
    profil["aktualisiert_am"] = heute

    try:
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(profil, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"[Profil] Fehler beim Speichern von '{name}': {e}"

    aktion = "erweitert" if existierte else "neu angelegt"
    felder = ", ".join(k for k in profil.keys())
    return f"[Profil] '{name}' {aktion}. Felder: {felder}"


def search_profile(keyword=""):
    # Durchsucht Dateinamen UND Inhalt aller Profile nach einem Begriff.
    keyword = (keyword or "").strip().lower()
    if not keyword:
        return "[Profil-Suche] Kein Suchbegriff angegeben."
    if not os.path.isdir(PROFIL_ORDNER):
        return "[Profil-Suche] Noch keine Profile vorhanden."

    treffer = []
    for datei in sorted(os.listdir(PROFIL_ORDNER)):
        if not datei.endswith(".json"):
            continue
        pfad = os.path.join(PROFIL_ORDNER, datei)
        try:
            with open(pfad, "r", encoding="utf-8") as f:
                roh = f.read()
        except Exception:
            continue
        if keyword in datei.lower() or keyword in roh.lower():
            treffer.append(f"--- {datei} ---\n{roh}")

    if not treffer:
        return f"[Profil-Suche] Kein Profil zu '{keyword}' gefunden."
    return "[Profil-Suche] Gefunden:\n" + "\n\n".join(treffer)


# --- Vom Code aufgerufen: Profil-Erkennung bei JEDER Eingabe ---

def _name_kommt_vor(text, name, klar):
    """Wortweiser Test, ob ein Profilname in der Eingabe steckt.
    WICHTIG: kein einfaches 'in', sonst wuerde Profil 'rose' auch in
    'prose' oder 'rosen' feuern. \\b prueft echte Wortgrenzen.
    Da jetzt JEDE Eingabe geprueft wird, ist das noetig, damit nicht
    dauernd ein falsches Profil geladen wird."""
    for variante in (name, klar):
        if not variante:
            continue
        if re.search(r"\b" + re.escape(variante) + r"\b", text, re.UNICODE):
            return True
    return False


def kontext_fuer_eingabe(eingabe, schon_geladen=None):
    """Prueft die Eingabe gegen bestehende Profilnamen und gibt den
    Kontext-Text fuer die NEU erkannten Profile zurueck.

    Rueckgabe: (kontext_text, neue_namen)
      - kontext_text: String zum Voranstellen, oder None wenn nichts Neues.
      - neue_namen:   Liste der Namen, die diesmal geladen wurden.

    schon_geladen: Menge bereits eingehaengter Namen. Diese werden
    uebersprungen, damit derselbe Name im Chat nicht mehrfach den vollen
    Profiltext einhaengt und den Kontext aufblaeht. Laedt NUR Vorhandenes,
    raet nie etwas."""
    schon_geladen = schon_geladen or set()

    if not os.path.isdir(PROFIL_ORDNER):
        return None, []

    text = (eingabe or "").lower()
    geladen = []
    for datei in sorted(os.listdir(PROFIL_ORDNER)):
        if not datei.endswith(".json"):
            continue
        name = datei[:-5]                 # ".json" abschneiden
        if name in schon_geladen:
            continue                       # in dieser Sitzung schon eingehaengt
        klar = name.replace("_", " ")     # "herr_mueller" -> "herr mueller"
        if _name_kommt_vor(text, name, klar):
            profil = profil_laden(name)
            if profil:
                geladen.append((name, profil))

    if not geladen:
        return None, []

    teile = ["[Bekanntes aus dem Gedaechtnis - nutze es, wenn es passt:]"]
    namen = []
    for name, profil in geladen:
        teile.append(f"\nProfil '{name}':\n" + json.dumps(profil, ensure_ascii=False, indent=2))
        namen.append(name)
    return "\n".join(teile), namen


if __name__ == "__main__":
    print("Profil-Ordner:", PROFIL_ORDNER)
    _ordner_sicherstellen()
    vorhandene = [d for d in os.listdir(PROFIL_ORDNER) if d.endswith(".json")]
    print("Vorhandene Profile:", vorhandene or "keine")
