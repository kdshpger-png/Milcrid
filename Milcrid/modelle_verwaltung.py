# modelle_verwaltung.py
# Portal > Lokale KI > Models: welche Sprachmodelle liegen auf dem Rechner,
# was koennen sie, was nicht - und Umschalten mit einem Klick.
#
# Klaus-Wunsch 2026-09-10: "jedes modell fuer sich mit beschreibung staerken
# schwaechen - und dann da dann button je model - Anwenden - oben vieleicht
# hinweis model X ist aktiv".
#
# Warum ein eigener Bereich und nicht bei "Modelfile": dort geht es ums BAUEN
# eigener Varianten (Modelfile bearbeiten, installieren). Hier geht es ums
# AUSWAEHLEN. Zwei verschiedene Fragen, darum zwei Kacheln.
#
# Das eigentliche Umschalten macht weiterhin modelfile_verwaltung
# .modell_aktivieren() - EINE Stelle, an der der Wechsel passiert, damit
# aktives_modell.json und config.MODELL nie auseinanderlaufen koennen.

import modelfile_verwaltung
import config

# Was Klaus im Portal lesen soll. Bewusst in normalen Worten, keine Benchmarks.
# "vram_gb" ist der Platzbedarf im Grafikspeicher - siehe VRAM_FREI unten.
KATALOG = {
    "qwen-milcrid": {
        "familie": "Qwen (Milcrids eigene Variante)",
        "groesse": "7 Mrd. · 4,7 GB",
        "vram_gb": 4.7,
        "beschreibung": "Milcrids Standardmodell. Ein qwen2.5:7b mit Milcrids "
                        "eigenen Einstellungen (Kontextfenster, Verhalten).",
        "staerken": "Auf Milcrids Werkzeuge abgestimmt, schnell, laeuft "
                    "vollstaendig auf der Grafikkarte.",
        "schwaechen": "Kleines Modell - wenig Weltwissen, bei langen Texten "
                      "verliert es eher den Faden.",
    },
    "qwen2.5:7b": {
        "familie": "Qwen",
        "groesse": "7 Mrd. · 4,7 GB",
        "vram_gb": 4.7,
        "beschreibung": "Das unveraenderte Modell, auf dem Milcrids eigene "
                        "Variante aufbaut.",
        "staerken": "Zum Vergleichen gut: zeigt, was Milcrids eigene "
                    "Einstellungen ausmachen.",
        "schwaechen": "Ohne Milcrids Kontextfenster-Einstellung.",
    },
    "qwen3.5:4b": {
        "familie": "Qwen 3.5",
        "groesse": "4 Mrd. · 3,4 GB",
        "vram_gb": 3.4,
        "beschreibung": "Das schnellste Modell der Sammlung.",
        "staerken": "Sehr flott, braucht wenig Grafikspeicher. Fuer seine "
                    "Groesse erstaunlich zuverlaessig bei Werkzeugaufrufen.",
        "schwaechen": "Wenig Weltwissen. Bei mehrstufigen Aufgaben schnell "
                      "ueberfordert.",
    },
    "qwen3.5:9b": {
        "familie": "Qwen 3.5",
        "groesse": "9 Mrd. · 6,6 GB",
        "vram_gb": 6.6,
        "beschreibung": "Der Allrounder - vermutlich der beste Tausch aus "
                        "Tempo und Koennen fuer diesen Rechner.",
        "staerken": "Qwen gilt bei Werkzeugaufrufen als die zuverlaessigste "
                    "Familie, und genau das ist Milcrids Hauptaufgabe. Passt "
                    "ganz auf die Grafikkarte.",
        "schwaechen": "Weniger Allgemeinwissen als die grossen Modelle.",
    },
    "qwen3.5:27b": {
        "familie": "Qwen 3.5",
        "groesse": "27 Mrd. · 17 GB",
        "vram_gb": 17.0,
        "beschreibung": "Das grosse Qwen. Deutlich mehr Wissen, laengere und "
                        "durchdachtere Antworten.",
        "staerken": "Bestes Verstaendnis der Qwen-Reihe, bleibt auch bei "
                    "langen Aufgaben bei der Sache.",
        "schwaechen": "Passt NICHT ganz in den freien Grafikspeicher - ein "
                      "Teil laeuft auf dem Hauptprozessor. Erwarte das Fuenf- "
                      "bis Zehnfache an Wartezeit. Fuer Dokumente in Ordnung, "
                      "zum Plaudern zaeh.",
    },
    "gemma4:e2b": {
        "familie": "Gemma 4",
        "groesse": "klein · 7,2 GB",
        "vram_gb": 7.2,
        "beschreibung": "Googles kleines Gemma.",
        "staerken": "Angenehme, fluessige Sprache.",
        "schwaechen": "Werkzeugaufrufe sind bei Gemma die schwache Seite - "
                      "fuer Milcrids Befehle die schlechtere Wahl.",
    },
    "gemma4:12b": {
        "familie": "Gemma 4",
        "groesse": "12 Mrd. · 7,6 GB",
        "vram_gb": 7.6,
        "beschreibung": "Das Gemma zum Reden und Nachschlagen.",
        "staerken": "Sehr gut im Erklaeren, Zusammenfassen und Plaudern. "
                    "Breites Allgemeinwissen fuer seine Groesse. Passt ganz "
                    "auf die Grafikkarte.",
        "schwaechen": "Bei Werkzeugaufrufen schwaecher als Qwen - genau das, "
                      "was Klaus schon 2026 beim ersten Versuch als "
                      "\"schwerfaellig bei Befehlen\" bemerkt hat.",
    },
    "gemma4:26b": {
        "familie": "Gemma 4",
        "groesse": "26 Mrd. · 19 GB",
        "vram_gb": 19.0,
        "beschreibung": "Das groesste Modell der Sammlung.",
        "staerken": "Das meiste Wissen von allen hier. Am besten fuer lange "
                    "Texte, Erklaerungen und Recherche.",
        "schwaechen": "Passt nicht in den freien Grafikspeicher, laeuft zu "
                      "einem guten Teil auf dem Hauptprozessor - deutlich "
                      "langsamer. Werkzeugaufrufe bleiben Gemmas Schwaeche.",
    },
    "llama3.2:3b": {
        "familie": "Llama 3.2",
        "groesse": "3 Mrd. · 2 GB",
        "vram_gb": 2.0,
        "beschreibung": "Metas kleinstes Modell.",
        "staerken": "Winzig und sehr schnell, laeuft nebenbei.",
        "schwaechen": "Einfache Antworten, Werkzeugaufrufe unzuverlaessig. "
                      "Eher zum Zeigen, dass es laeuft, als zum Arbeiten.",
    },
    "llama3.1:8b": {
        "familie": "Llama 3.1",
        "groesse": "8 Mrd. · 4,7 GB",
        "vram_gb": 4.7,
        "beschreibung": "Der solide Klassiker von Meta.",
        "staerken": "Ausgewogen, gut erprobt, passt ganz auf die Grafikkarte.",
        "schwaechen": "Aelter als Qwen 3.5 und Gemma 4 - merkt man beim "
                      "Verstaendnis. Bei Werkzeugen Mittelfeld.",
    },
}

# Von den 16 GB der Grafikkarte haelt faster-whisper (Spracherkennung)
# dauerhaft rund 4 GB belegt. Was uebrig bleibt, entscheidet darueber, ob ein
# Modell ganz auf der Grafikkarte laeuft oder teilweise auf dem
# Hauptprozessor - und das ist der groesste Unterschied beim Tempo.
VRAM_GESAMT = 16.0
VRAM_BELEGT = 4.0
VRAM_FREI = VRAM_GESAMT - VRAM_BELEGT


def _unbekannt(name):
    return {
        "familie": "",
        "groesse": "",
        "vram_gb": None,
        "beschreibung": "Noch keine Beschreibung hinterlegt.",
        "staerken": "",
        "schwaechen": "",
    }


def info():
    """Alles fuer die Models-Ansicht: was ist da, was ist aktiv, was passt."""
    da = set(modelfile_verwaltung.fremde_modelle())
    da.add(modelfile_verwaltung.URSPRUENGLICH)
    # Nur zeigen, was wirklich auf dem Rechner liegt. Frueher kam alles aus
    # KATALOG dazu und stand, solange es fehlte, als "Wird geladen ..." da -
    # gedacht fuer die Downloads vom 10.09. Nach Klaus' Auswahl vom 13.09.
    # (10 Modelle per ollama rm entfernt) behaupteten vier davon auf Dauer,
    # sie wuerden geladen (Klaus-Fund 2026-09-24). Der KATALOG bleibt als
    # Beschreibungs-Vorrat: kommt ein Modell wieder, hat es sofort seinen Text.
    alle = sorted(da)
    aktiv = config.MODELL
    modelle = []
    for name in alle:
        k = KATALOG.get(name) or _unbekannt(name)
        vram = k.get("vram_gb")
        modelle.append({
            "name": name,
            "aktiv": name == aktiv,
            "passt": None if vram is None else vram <= VRAM_FREI,
            **k,
        })
    # Reihenfolge: nach Groesse
    modelle.sort(key=lambda m: m.get("vram_gb") or 99)
    return {
        "aktiv": aktiv,
        "modelle": modelle,
        "vram_frei": VRAM_FREI,
        "vram_gesamt": VRAM_GESAMT,
    }


def aktivieren(name):
    """Umschalten - macht modelfile_verwaltung, damit es nur EINE Stelle gibt."""
    return modelfile_verwaltung.modell_aktivieren(name)
