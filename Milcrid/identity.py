# identity.py
# Identitaetskern des Ich-Agenten Milcrid.
# Verwaltet die Datei self/identity.json. Sie ist zweigeteilt:
#   - fundament : NUR Klaus aenderbar. Wird hier NIE geschrieben (schreibgeschuetzt).
#   - selbst    : Der Agent schreibt sich hier fort, ausschliesslich ueber
#                 update_identity(). Deep-Merge, NIE Komplett-Ueberschreiben.
#
# Der Merge-Mechanismus ist bewusst NICHT neu gebaut, sondern derselbe wie
# bei den Profilen (profiles._tief_mergen / profiles._daten_lesen). So gibt es
# EINE Quelle fuer die Merge-Logik, und beide Wege koennen nie auseinanderlaufen.

import os
import json
from datetime import date

import profiles  # gemeinsame Merge- und Parse-Logik wiederverwenden

BASE_DIR = os.path.realpath(os.path.expanduser("~/Milcrid"))
IDENTITY_PFAD = os.path.join(BASE_DIR, "self", "identity.json")

# Nur diese Felder darf der Agent im selbst-Teil beschreiben. Alles andere
# wird abgelehnt. Das haelt den selbst-Teil sauber und verhindert, dass sich
# das Modell eigene Felder erfindet (Sicherung 3: kein Drift).
ERLAUBTE_SELBST_FELDER = ("positionen", "offene_fragen", "widersprueche_zu_klaus")


def identity_laden():
    """Laedt self/identity.json. Gibt das dict zurueck, oder None wenn die
    Datei fehlt oder unlesbar ist. Legt NICHTS an - das fundament muss von
    Klaus kommen, niemals vom Code."""
    if not os.path.exists(IDENTITY_PFAD):
        return None
    try:
        with open(IDENTITY_PFAD, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _datum_setzen(werte):
    """Setzt bei jedem Listen-Eintrag, der ein dict ist, datum = heute.
    WICHTIG: Das Datum vergibt der CODE, nie das Modell. Damit kann ein
    Eintrag nicht mit falschem oder erfundenem Datum in die Historie -
    er ist immer auf den Tag des tatsaechlichen Schreibens datiert und
    damit jederzeit pruefbar. Ein vom Modell mitgeschicktes datum wird
    bewusst ueberschrieben."""
    heute = date.today().isoformat()
    for feld, inhalt in werte.items():
        if isinstance(inhalt, list):
            for eintrag in inhalt:
                if isinstance(eintrag, dict):
                    eintrag["datum"] = heute
    return werte


def update_identity(data=""):
    """Werkzeug fuer den Agenten: schreibt AUSSCHLIESSLICH in den selbst-Teil
    von self/identity.json.

    Erwartet 'data' als dict (oder JSON-Text). Beispiel:
      {"widersprueche_zu_klaus": [
         {"thema": "...", "position": "...", "begruendung": "..."}]}
    Das datum-Feld muss NICHT mitgeschickt werden - der Code setzt es selbst.

    Garantien:
      - fundament wird NIE angefasst (schreibgeschuetzt).
      - Nur Felder aus ERLAUBTE_SELBST_FELDER werden uebernommen.
      - datum jedes neuen Eintrags wird vom Code gesetzt, nicht vom Modell.
      - Deep-Merge ueber profiles._tief_mergen: Listen wachsen an,
        nichts wird komplett ueberschrieben.
    """
    # KI Profil > Selbst > An/Aus (25.09.2026). Lazy-Import: memory.py kennt
    # identity.py nicht, ein Zirkel ist so ausgeschlossen.
    import memory
    if not memory.einstellungen_lesen().get("selbst_aufzeichnen", True):
        return ("[Abgelehnt] Klaus hat das Fortschreiben des Selbstbilds ausgeschaltet "
                "(KI Profil > Selbst). Es wurde nichts eingetragen - sag ihm das.")
    identity = identity_laden()
    if identity is None:
        return ("[Identitaet] self/identity.json fehlt oder ist unlesbar - "
                "es wird nichts geschrieben. Die Datei muss zuerst angelegt werden.")

    neu = profiles._daten_lesen(data)
    if not neu:
        return "[Identitaet] Keine verwertbaren Daten uebergeben - nichts geaendert."

    # Nur erlaubte selbst-Felder durchlassen; fundament und unbekannte Felder raus.
    gefiltert = {k: v for k, v in neu.items() if k in ERLAUBTE_SELBST_FELDER}
    abgelehnt = [k for k in neu.keys() if k not in ERLAUBTE_SELBST_FELDER]

    if not gefiltert:
        erlaubt = ", ".join(ERLAUBTE_SELBST_FELDER)
        return (f"[Identitaet] Kein beschreibbares Feld dabei. Erlaubt sind nur: "
                f"{erlaubt}. Abgelehnt: {', '.join(abgelehnt) or '-'}")

    # Datum code-seitig setzen, BEVOR gemerged wird.
    _datum_setzen(gefiltert)

    # selbst-Teil sicherstellen, OHNE das fundament zu beruehren.
    selbst = identity.get("selbst")
    if not isinstance(selbst, dict):
        selbst = {}
        identity["selbst"] = selbst

    profiles._tief_mergen(selbst, gefiltert)
    selbst["_aktualisiert_am"] = date.today().isoformat()

    # Ganze Datei zurueckschreiben (fundament unveraendert + neuer selbst-Teil).
    try:
        with open(IDENTITY_PFAD, "w", encoding="utf-8") as f:
            json.dump(identity, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"[Identitaet] Fehler beim Speichern: {e}"

    uebernommen = ", ".join(gefiltert.keys())
    meldung = f"[Identitaet] selbst-Teil aktualisiert. Felder: {uebernommen}."
    if abgelehnt:
        meldung += f" Ignoriert (nicht beschreibbar): {', '.join(abgelehnt)}."
    return meldung


if __name__ == "__main__":
    print("Identitaets-Datei:", IDENTITY_PFAD)
    ident = identity_laden()
    if ident is None:
        print("Noch keine identity.json vorhanden.")
    else:
        print("Fundament vorhanden:", "fundament" in ident)
        print("Selbst-Felder:", list((ident.get("selbst") or {}).keys()))
