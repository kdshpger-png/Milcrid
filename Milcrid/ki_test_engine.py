# ki_test_engine.py
# Wiederverwendbare Engine fuer die "KI Test"-Ansicht (Portal > Lokale KI >
# KI Test): startet EINE isolierte Milcrid-Sitzung (eigene PortalSitzung-
# Instanz, NICHT die laufende Kiosk-Sitzung), schickt eine Aufgabenliste
# durch, misst Zeit und Kontext-Auslastung je Antwort. Speichert NICHTS von
# sich aus - das macht ki_test_verwaltung.py erst wenn Klaus auf "Speichern"
# drueckt. Jeder einzelne Test (siehe ki_test_verwaltung.TESTS) benutzt
# dieselbe Funktion hier - neuer Test = neue Aufgabenliste, kein neuer Code.

import time


def testlauf_ausfuehren(aufgaben):
    """aufgaben: Liste von Strings (Fragen/Auftraege an Milcrid, wie Klaus sie
    im Portal tippen wuerde). Gibt ein Dict zurueck mit Gesamtdauer und einer
    Liste von Einzelergebnissen (Frage, Antwort, Dauer, Kontext-Auslastung)."""
    import main as milcrid_main  # spaeter Import - main.py importiert am Ende
                                   # ki_test_verwaltung, das wiederum diese
                                   # Datei importiert. Ein Import von main auf
                                   # Modul-Ebene HIER wuerde einen Zirkel-
                                   # Import beim Start ausloesen - deshalb
                                   # erst beim tatsaechlichen Aufruf laden,
                                   # wenn main.py laengst fertig geladen ist.

    sitzung = milcrid_main.PortalSitzung()
    ergebnisse = []
    start_gesamt = time.time()

    for i, frage in enumerate(aufgaben, start=1):
        start = time.time()
        try:
            antwort = sitzung.frage(frage)
            fehler = None
        except Exception as e:
            antwort = ""
            fehler = f"{type(e).__name__}: {e}"
        dauer = round(time.time() - start, 2)
        tokens = dict(sitzung.tokens) if sitzung.tokens else None
        ergebnisse.append({
            "nr": i,
            "frage": frage,
            "antwort": antwort,
            "dauer_sekunden": dauer,
            "fehler": fehler,
            "kontext_prozent": tokens["prozent"] if tokens else None,
        })

    gesamt_dauer = round(time.time() - start_gesamt, 1)
    return {
        "gesamt_dauer_sekunden": gesamt_dauer,
        "anzahl_aufgaben": len(aufgaben),
        "ergebnisse": ergebnisse,
    }


def bericht_als_text(testname, bericht):
    """Formatiert einen Bericht als lesbaren Text - fuers Anzeigen im Portal,
    Kopieren in die Zwischenablage und Speichern als .txt."""
    zeilen = [
        f"Milcrid KI-Test: {testname}",
        f"Gesamtdauer: {bericht['gesamt_dauer_sekunden']}s fuer "
        f"{bericht['anzahl_aufgaben']} Aufgabe(n)"
        + (f" (Schnitt {round(bericht['gesamt_dauer_sekunden']/bericht['anzahl_aufgaben'], 1)}s/Aufgabe)"
           if bericht['anzahl_aufgaben'] else ""),
        "=" * 70,
        "",
    ]
    for e in bericht["ergebnisse"]:
        zeilen.append(f"[{e['nr']:02d}] {e['dauer_sekunden']}s  Kontext={e['kontext_prozent']}%")
        zeilen.append(f"FRAGE:   {e['frage']}")
        if e["fehler"]:
            zeilen.append(f"FEHLER:  {e['fehler']}")
        zeilen.append(f"ANTWORT: {e['antwort']}")
        zeilen.append("-" * 70)
    return "\n".join(zeilen)
