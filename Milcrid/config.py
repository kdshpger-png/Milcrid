# config.py
# EINE zentrale Stelle fuer die Kontextfenster-Groesse UND das aktive Modell.
#
# Die WAHRE Quelle fuers Kontextfenster ist der Modelfile-Parameter `num_ctx` -
# die Zahl, die das laufende Modell wirklich benutzt. config.py liest sie dort
# aus, damit sie nur an EINER Stelle steht.
#
# Findet config.py den Modelfile nicht oder keine num_ctx-Zeile, greift der
# Sicherheits-Standard STANDARD_FENSTER. Dann laeuft alles weiter, nur mit der
# hinterlegten Zahl statt der echten. Kein Absturz.

import json
import os
import re

# Sicherheits-Standard, falls der Modelfile nicht lesbar ist.
# Sollte mit num_ctx im Modelfile uebereinstimmen.
STANDARD_FENSTER = 16384

# Neuere Modelle (qwen3.5, gemma4) "denken" vor jeder Antwort - sie schreiben
# erst einen Gedankengang und dann die Antwort. Fuer Milcrid ist das fast immer
# verschenkte Zeit: gemessen am 2026-09-10 mit qwen3.5:9b und dem Satz "oeffne
# die Uhr" - mit Denken 14,7 Sekunden, ohne Denken 2,7. Bei einem Befehl gibt
# es nichts zu ueberlegen, das Werkzeug steht fest.
# Schlimmer noch: passt der Gedankengang nicht ins Kontextfenster, bleibt fuer
# die eigentliche Antwort NICHTS uebrig - Milcrid antwortete dann mit einem
# leeren Text. Genau so sah Klaus' "Haenger" aus.
# Auf True stellen, wenn ein Modell wirklich nachdenken soll (lange Texte,
# Recherche). Aeltere Modelle ignorieren die Einstellung einfach.
DENKEN_ERLAUBT = False

MODELFILE_PFAD = os.path.realpath(os.path.expanduser("~/Milcrid/Modelfile"))

# Eigene Modelfile-Varianten (siehe modelfile_verwaltung.py, Portal-Einstellungen
# > Modelfile) und die gerade gewaehlte aktive Modell-Wahl liegen als kleine
# JSON-Dateien direkt daneben in ~/Milcrid.
_MILCRID_DIR = os.path.dirname(MODELFILE_PFAD)
AKTIVES_MODELL_PFAD = os.path.join(_MILCRID_DIR, "aktives_modell.json")
ENTWUERFE_PFAD = os.path.join(_MILCRID_DIR, "modelfile_entwuerfe.json")


def num_ctx_aus_text(text, standard=STANDARD_FENSTER):
    """Liest 'PARAMETER num_ctx <zahl>' aus einem Modelfile-Text (egal ob aus
    einer Datei gelesen oder ein im Portal gespeicherter Entwurfstext). Gibt
    die Zahl zurueck, oder den Standard, wenn die Zeile fehlt/kaputt ist."""
    if not text:
        return standard
    treffer = re.search(r"(?im)^\s*PARAMETER\s+num_ctx\s+(\d+)", text)
    if not treffer:
        return standard
    try:
        wert = int(treffer.group(1))
        return wert if wert > 0 else standard
    except ValueError:
        return standard


def _num_ctx_aus_modelfile(pfad=MODELFILE_PFAD, standard=STANDARD_FENSTER):
    """Liest num_ctx direkt aus einer Modelfile-Datei (Standardfall: das
    geschuetzte Original in ~/Milcrid/Modelfile)."""
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            inhalt = f.read()
    except Exception:
        return standard
    return num_ctx_aus_text(inhalt, standard)


# --- Modellname + Kontextfenster --------------------------------------------
# Der Name des Original-Ollama-Modells - fest, unveraenderlich, immer verfuegbar
# als Rueckfallebene. Eigene, ueber "Modelfile" im Portal installierte
# Varianten bekommen einen ANDEREN Namen (nie diesen hier).
URSPRUENGLICHES_MODELL = "qwen-milcrid"


def _aktives_modell_und_fenster_laden():
    """Welches Modell benutzt Milcrid gerade wirklich, und mit welchem
    Kontextfenster? Liest die vom Nutzer im Portal getroffene Wahl aus
    aktives_modell.json. Zeigt die Wahl auf eine eigene, installierte
    Variante, kommt num_ctx aus deren gespeichertem Entwurfstext - sonst
    (Original oder bei jedem Fehler) aus dem echten Modelfile."""
    name = URSPRUENGLICHES_MODELL
    try:
        with open(AKTIVES_MODELL_PFAD, "r", encoding="utf-8") as f:
            gespeichert = json.load(f).get("modell", "").strip()
        if gespeichert:
            name = gespeichert
    except Exception:
        pass

    if name == URSPRUENGLICHES_MODELL:
        return name, _num_ctx_aus_modelfile()

    try:
        with open(ENTWUERFE_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
        if name in daten.get("installiert", []):
            return name, num_ctx_aus_text(daten.get("entwuerfe", {}).get(name, ""))
    except Exception:
        pass
    # Kein eigener Entwurf - aber vielleicht ein Modell direkt aus der
    # Ollama-Bibliothek (gemma4, llama, qwen3.5)? Seit 2026-09-10 kann Klaus
    # die im Portal unter Lokale KI > Models auswaehlen.
    # OHNE diese Pruefung fiel Milcrid bei JEDEM Neustart still auf das
    # Original zurueck, obwohl in aktives_modell.json etwas anderes stand -
    # die Wahl hielt also nur bis zum naechsten Start (Klaus-Fund 2026-09-10).
    # Ein solches Modell bringt kein eigenes num_ctx mit, darum der Standard.
    try:
        import ollama
        antwort = ollama.list()
        roh = (antwort.get("models") if isinstance(antwort, dict)
               else getattr(antwort, "models", [])) or []
        vorhanden = set()
        for m in roh:
            n = m.get("model") if isinstance(m, dict) else getattr(m, "model", None)
            if n:
                vorhanden.add(n)
                vorhanden.add(n.split(":")[0])
        if name in vorhanden:
            return name, STANDARD_FENSTER
    except Exception:
        pass

    # Name steht in aktives_modell.json, gibt es aber wirklich nicht (mehr) -
    # sicherheitshalber aufs Original zurueck.
    return URSPRUENGLICHES_MODELL, _num_ctx_aus_modelfile()


# Die zwei Werte, die der Rest des Systems benutzt. main.py ruft
# ollama.chat(model=config.MODELL, ...) auf; token_counter.py liest
# config.KONTEXT_FENSTER bei jeder Antwort frisch (nicht als Kopie), daher
# wirkt ein Wechsel ueber modelfile_verwaltung.modell_aktivieren() sofort,
# ganz ohne Neustart des Portal-Servers.
MODELL, KONTEXT_FENSTER = _aktives_modell_und_fenster_laden()


def chat_optionen():
    """Die Optionen, die JEDER Modellaufruf mitgeben muss - an EINER Stelle.

    Opus-Fund 2026-09-10: Das num_ctx vom Vortag (siehe main.py) war nur im
    Chat-Aufruf von main.py eingebaut. Die acht anderen Aufrufe (Chat
    speichern, Webseiten-Analyse, Prompt erstellen, Systemcheck) liefen mit
    Ollamas Standard von 4096 und MIT Denken. Beim Chat-Speichern fuellte der
    Verlauf das Fenster schon allein (4087 von 4096 Tokens) - die
    Zusammenfassung kam leer zurueck, und im Kurzzeitgedaechtnis standen
    danach nur noch Fehlermeldungen statt Erinnerungen.

    Eine Funktion statt einer Konstante, weil KONTEXT_FENSTER sich beim
    Modellwechsel im laufenden Betrieb aendert (modelfile_verwaltung).
    Zusammen mit think=config.DENKEN_ERLAUBT an ollama.chat geben.

    Seit 2026-09-12 schreibt jeder Aufruf eine Zeile in die Mitschrift: welches
    Modell, welches Kontextfenster, ob gedacht wird. Vorher liess sich im
    Nachhinein nicht sagen, WOMIT ein Aufruf wirklich lief - genau die Frage,
    die beim num_ctx-Fund vom 10.09. offen blieb. Der Import steht absichtlich
    hier drin und nicht oben: config wird sehr frueh geladen, mitschrift
    spaeter, und ein Fehler beim Aufschreiben darf nie einen Modellaufruf
    verhindern."""
    optionen = {"num_ctx": KONTEXT_FENSTER or STANDARD_FENSTER}
    try:
        import mitschrift
        mitschrift.notiz("modell_optionen", modell=MODELL,
                         num_ctx=optionen["num_ctx"], denken=DENKEN_ERLAUBT)
    except Exception:
        pass
    return optionen


if __name__ == "__main__":
    print("Modelfile:", MODELFILE_PFAD)
    print("Gelesen:", os.path.exists(MODELFILE_PFAD))
    print("KONTEXT_FENSTER =", KONTEXT_FENSTER)
    print("MODELL =", MODELL)
    print("Original-Modell =", URSPRUENGLICHES_MODELL)
