# memory_search.py
# Suchwerkzeug fuer Milcrids Gedaechtnis.
#
# WICHTIG: Diese Datei aendert NICHTS. Sie liest nur. memory.py und bridge.py
# bleiben unberuehrt. Loeschen = alles ist wie vorher.
#
# Der Grundgedanke:
#   Milcrid soll NIE eine ganze Archiv-Datei lesen muessen. Python durchsucht
#   die Dateien und gibt Milcrid nur die TREFFER zurueck. Python kann 10.000
#   Bloecke in Millisekunden durchgehen, ohne ein einziges Token zu verbrauchen.
#
# Zwei Werkzeuge:
#   search_memory(begriff, monate)  -> Bloecke aus dem Gedaechtnis
#                                      (Zusammenfassungen: was besprochen wurde)
#   search_chats(begriff, monate)   -> Fundstellen in den Transkripten
#                                      (Wortlaut: wie es gesagt wurde)
#
# Gesucht wird IM INHALT, nicht im Dateinamen. Das Datum ist ein zweiter
# Filter, kein Suchweg.
#
# Alleine testen (ohne Milcrid):
#   python3 memory_search.py kompression
#   python3 memory_search.py kompression 6
#   python3 memory_search.py --info

import os
import re
import json
from datetime import date

import memory   # nur fuer die Pfade -> eine einzige Quelle
import config   # Kontextfenster -> eine einzige Quelle (num_ctx im Modelfile)


# --- Die EINZIGE Zahl, die du drehen musst -------------------------------

# Dein Kontextfenster. Kommt aus config (Quelle: num_ctx im Modelfile).
# Beim Modellwechsel NICHT hier aendern, sondern num_ctx im Modelfile -
# diese Zahl folgt dann automatisch. Alles andere rechnet sich daraus.

# Wie viel Prozent des Fensters darf eine Antwort dieses Werkzeugs belegen?
# 15 % ist die Regel, die wir auch fuers Kurzzeitgedaechtnis benutzen.
ANTEIL = 0.15

# Deutscher Text mit Umlauten: rund 3,4 Zeichen pro Token. Gemessen an
# deiner echten short-term.json, nicht geschaetzt.
ZEICHEN_PRO_TOKEN = 3.4


def _budget():
    """Zeichen-Budget fuer eine Antwort. Bei 16384 -> 8356 Zeichen (~2450
    Token), bei 32768 -> 16713 Zeichen.

    Wird bei JEDER Suche frisch gerechnet statt einmal beim Import: vorher
    stand hier "BUDGET = int(FENSTER * ...)" mit FENSTER als Import-Kopie von
    config.KONTEXT_FENSTER. Wechselte man das Modell im Portal (anderes
    num_ctx), rechnete die Suche weiter mit dem alten Fenster - bei einem
    kleineren Modell also zu grosszuegig, was genau den Kontext-Ueberlauf
    ausloest, den dieses Budget verhindern soll."""
    return int((config.KONTEXT_FENSTER or config.STANDARD_FENSTER)
               * ANTEIL * ZEICHEN_PRO_TOKEN)

# Wie viele Zeichen links und rechts um eine Fundstelle im Transkript.
KONTEXT_ZEICHEN = 300

# Harte Obergrenze fuer die Anzahl Treffer, falls die Bloecke mal winzig sind.
TREFFER_DECKEL = 20


# --- Wo liegen die Bloecke? ------------------------------------------------
# Alle vier Quellen haben dasselbe Block-Format:
#   {"datum", "stichwort", "zusammenfassung", "voll_transkript"}

def _block_dateien():
    """Alle JSON-Dateien, in denen Gedaechtnis-Bloecke liegen koennen."""
    dateien = []

    # 1) Das aktive Kurzzeitgedaechtnis
    dateien.append(memory.KURZZEIT_DATEI)

    # 2) Alles im Langzeit-Ordner, was nach Bloecken aussieht:
    #    archiv.json (alt), long-term.json (von Hand gepflegt),
    #    archiv_2026-07-13.json (neu, rotiert)
    if os.path.isdir(memory.LANGZEIT_ORDNER):
        for wurzel, ordner, files in os.walk(memory.LANGZEIT_ORDNER):
            for f in files:
                if f.lower().endswith(".json"):
                    dateien.append(os.path.join(wurzel, f))

    return dateien


def _bloecke_sammeln():
    """Liest alle Bloecke aus allen Quellen. Doppelte werden entfernt."""
    bloecke = []
    gesehen = set()

    for pfad in _block_dateien():
        if not os.path.exists(pfad):
            continue
        try:
            with open(pfad, "r", encoding="utf-8") as f:
                daten = json.load(f)
        except Exception:
            continue   # kaputte oder fremde JSON einfach ueberspringen

        if not isinstance(daten, list):
            continue

        for b in daten:
            if not isinstance(b, dict):
                continue
            if "zusammenfassung" not in b:
                continue   # kein Gedaechtnis-Block

            # Doppelte erkennen. Der Text selbst ist der Schluessel.
            # Datum + Stichwort reicht NICHT: Du kannst am selben Tag zweimal
            # zum selben Thema gespeichert haben - zwei echte Chats, gleiches
            # Stichwort, aber VERSCHIEDENE Zusammenfassungen. Die duerfen nicht
            # verschwinden. Nur wenn der Text Zeichen fuer Zeichen gleich ist,
            # hast du ihn wirklich doppelt (z.B. per Hand rueberkopiert).
            schluessel = (b.get("datum", ""),
                          b.get("stichwort", ""),
                          (b.get("zusammenfassung", "") or "").strip())
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)

            b = dict(b)
            b["_quelle"] = os.path.basename(pfad)
            bloecke.append(b)

    # Neuester zuerst
    bloecke.sort(key=lambda b: b.get("datum", ""), reverse=True)
    return bloecke


# --- Zeitfilter ------------------------------------------------------------

def _grenzdatum(monate):
    """Gibt das Datum vor X Monaten zurueck. Ohne Zusatzmodul."""
    heute = date.today()
    jahr = heute.year
    monat = heute.month - int(monate)
    while monat <= 0:
        monat += 12
        jahr -= 1
    tag = min(heute.day, 28)   # sicher gegen kurze Monate
    return date(jahr, monat, tag).isoformat()


def _monate_lesen(monate):
    """Milcrid schickt Zahlen als Text ('6'). Sauber umwandeln."""
    if monate is None or monate == "":
        return None
    try:
        m = int(str(monate).strip())
        return m if m > 0 else None
    except (ValueError, TypeError):
        return None


# --- Suchlogik -------------------------------------------------------------

def _woerter(begriff):
    """Zerlegt 'kompression python' in ['kompression', 'python'].
    Ein Block muss ALLE Woerter enthalten, um als Treffer zu zaehlen."""
    return [w for w in re.split(r"\s+", (begriff or "").strip().lower()) if w]


def _passt(text, woerter):
    text = text.lower()
    return all(w in text for w in woerter)


def _block_text(i, b):
    """Ein Treffer als Text. Genau so sieht Milcrid ihn."""
    return (f"[{i}] {b.get('datum','?')} | {b.get('stichwort','?')}\n"
            f"    Volltext: {b.get('voll_transkript','-')}\n"
            f"    {(b.get('zusammenfassung','') or '').strip()}\n")


# --- WERKZEUG 1: Bloecke suchen (das Gedaechtnis) --------------------------

def search_memory(begriff, monate=None):
    """Sucht in allen Gedaechtnis-Zusammenfassungen nach einem Begriff.

    begriff  = ein oder mehrere Woerter. Alle muessen vorkommen.
    monate   = optional. Nur Eintraege aus den letzten X Monaten.

    Gibt NUR die Treffer-Bloecke zurueck, nie eine ganze Datei.
    """
    woerter = _woerter(begriff)
    if not woerter:
        return "Kein Suchbegriff angegeben."

    m = _monate_lesen(monate)
    grenze = _grenzdatum(m) if m else None

    bloecke = _bloecke_sammeln()
    treffer = []

    for b in bloecke:
        if grenze and b.get("datum", "") < grenze:
            continue
        durchsuchbar = f"{b.get('stichwort','')} {b.get('zusammenfassung','')}"
        if _passt(durchsuchbar, woerter):
            treffer.append(b)

    if not treffer:
        zeitraum = f" in den letzten {m} Monaten" if m else ""
        return (f"Keine Treffer fuer '{begriff}'{zeitraum}. "
                f"({len(bloecke)} Bloecke durchsucht.)")

    gesamt = len(treffer)

    # Budget fuellen: So viele Bloecke wie reinpassen, aber NIE mitten in
    # einem Block abschneiden. Danach wird ehrlich gezaehlt.
    gezeigt = []
    verbraucht = 0
    budget = _budget()
    for b in treffer[:TREFFER_DECKEL]:
        text = _block_text(len(gezeigt) + 1, b)
        if gezeigt and verbraucht + len(text) > budget:
            break
        gezeigt.append(text)
        verbraucht += len(text)

    zeitraum = f", letzte {m} Monate" if m else ""
    if len(gezeigt) < gesamt:
        kopf = (f"{gesamt} Treffer fuer '{begriff}'{zeitraum}. "
                f"Hier die {len(gezeigt)} neuesten - mehr passt nicht ins "
                f"Kontextfenster. Fuer den Rest: genauerer Begriff oder "
                f"kleinerer Zeitraum.")
    else:
        kopf = f"{gesamt} Treffer fuer '{begriff}'{zeitraum}:"

    teile = [kopf, ""] + gezeigt
    teile.append("Brauchst du den vollen Wortlaut, lies die genannte "
                 "Volltext-Datei mit read_file.")
    return "\n".join(teile)


# --- WERKZEUG 2: Transkripte durchsuchen (der Wortlaut) --------------------

def _txt_dateien():
    """Alle Chat-Transkripte im Langzeit-Ordner (auch in Unterordnern)."""
    pfade = []
    if not os.path.isdir(memory.LANGZEIT_ORDNER):
        return pfade
    for wurzel, ordner, files in os.walk(memory.LANGZEIT_ORDNER):
        for f in files:
            if f.lower().endswith(".txt"):
                pfade.append(os.path.join(wurzel, f))
    return sorted(pfade, reverse=True)   # neueste zuerst (Dateiname beginnt mit Datum)


def _datum_aus_name(dateiname):
    """Holt 2026-07-13 aus '2026-07-13_thema.txt'. Sonst None."""
    t = re.match(r"(\d{4}-\d{2}-\d{2})", os.path.basename(dateiname))
    return t.group(1) if t else None


def search_chats(begriff, monate=None):
    """Sucht in den vollen Chat-Transkripten (.txt) nach einem Begriff.

    Gibt NICHT den Chat zurueck, sondern nur die FUNDSTELLE:
    ein Ausschnitt von je 300 Zeichen links und rechts.
    """
    woerter = _woerter(begriff)
    if not woerter:
        return "Kein Suchbegriff angegeben."

    m = _monate_lesen(monate)
    grenze = _grenzdatum(m) if m else None

    haupt = woerter[0]           # danach wird die Stelle gesucht
    treffer = []
    durchsucht = 0

    for pfad in _txt_dateien():
        datum = _datum_aus_name(pfad)
        if grenze and datum and datum < grenze:
            continue

        try:
            with open(pfad, "r", encoding="utf-8", errors="replace") as f:
                inhalt = f.read()
        except Exception:
            continue

        durchsucht += 1
        if not _passt(inhalt, woerter):
            continue

        # Erste Fundstelle des Hauptworts, mit Umgebung
        stelle = inhalt.lower().find(haupt)
        if stelle < 0:
            continue

        von = max(0, stelle - KONTEXT_ZEICHEN)
        bis = min(len(inhalt), stelle + len(haupt) + KONTEXT_ZEICHEN)
        ausschnitt = inhalt[von:bis].strip()
        ausschnitt = re.sub(r"\s+", " ", ausschnitt)

        treffer.append({
            "datei": os.path.basename(pfad),
            "datum": datum or "?",
            "ausschnitt": ausschnitt,
        })

        if len(treffer) >= 5:
            break

    if not treffer:
        zeitraum = f" in den letzten {m} Monaten" if m else ""
        return (f"Keine Fundstelle fuer '{begriff}'{zeitraum}. "
                f"({durchsucht} Transkripte durchsucht.)")

    zeitraum = f", letzte {m} Monate" if m else ""
    teile = [f"{len(treffer)} Fundstelle(n) fuer '{begriff}'{zeitraum}:", ""]
    for i, t in enumerate(treffer, 1):
        teile.append(f"[{i}] {t['datei']}")
        teile.append(f"    ...{t['ausschnitt']}...")
        teile.append("")

    teile.append("Das sind nur Ausschnitte. Den ganzen Chat liest du mit "
                 "read_file und dem genannten Dateinamen.")

    return "\n".join(teile)


# --- Selbsttest: laeuft ohne Milcrid, ohne Ollama, ohne bridge ---------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--info":
        bloecke = _bloecke_sammeln()
        txt = _txt_dateien()
        print()
        print(f"  Gedaechtnis-Bloecke gefunden: {len(bloecke)}")
        print(f"  Transkripte (.txt) gefunden:  {len(txt)}")
        print()
        quellen = {}
        for b in bloecke:
            quellen[b["_quelle"]] = quellen.get(b["_quelle"], 0) + 1
        print("  Verteilt auf:")
        for q, n in sorted(quellen.items(), key=lambda x: -x[1]):
            print(f"    {n:>4} Bloecke   {q}")
        print()
        if bloecke:
            print(f"  Aeltester Block: {bloecke[-1].get('datum')}")
            print(f"  Neuester Block:  {bloecke[0].get('datum')}")
        print()
        sys.exit(0)

    if len(sys.argv) < 2:
        print()
        print("  So testest du:")
        print("    python3 memory_search.py --info")
        print("    python3 memory_search.py bewusstsein")
        print("    python3 memory_search.py bewusstsein 3      (nur letzte 3 Monate)")
        print()
        sys.exit(0)

    begriff = sys.argv[1]
    monate = sys.argv[2] if len(sys.argv) > 2 else None

    print()
    print("=" * 70)
    print("  search_memory  --  Bloecke aus dem Gedaechtnis")
    print("=" * 70)
    print(search_memory(begriff, monate))
    print()
    print("=" * 70)
    print("  search_chats  --  Fundstellen im Wortlaut")
    print("=" * 70)
    print(search_chats(begriff, monate))
    print()
