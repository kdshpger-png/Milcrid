#!/usr/bin/env python3
"""Prüfstand: findet Milcrid die Datei, die Klaus meint?

Klaus' Bild vom 19.09.2026: "Thema Opus ist offen, darin liegt demo.txt, ich
sage 'öffne demo' - dann soll sie die Datei öffnen." Dazu sein Grundsatz:
passen mehrere, wird GEFRAGT, nicht geraten.

Der Test legt eigene Dateien in einem Test-Thema an und räumt sie wieder weg.
"""
import os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # ~/Milcrid, auch beim Nutzer
import bridge

THEMEN = os.path.join(bridge.BASE_DIR, "Schreibtisch Ablagen")
TEST_THEMA = os.path.join(THEMEN, "Pruefthema")
ZWEITES = os.path.join(THEMEN, "Pruefthema2")
ANDERSWO = os.path.join(bridge.BASE_DIR, "Pruefordner")

fehler = []
geprueft = 0


def pruefe(was, ist, soll):
    global geprueft
    geprueft += 1
    if ist == soll:
        print("  ok   %-52s %s" % (was, ist))
    else:
        fehler.append(was)
        print("  ROT  %-52s %s  (erwartet: %s)" % (was, ist, soll))


def aufbauen():
    for ordner in (TEST_THEMA, ZWEITES, ANDERSWO):
        os.makedirs(ordner, exist_ok=True)
    open(os.path.join(TEST_THEMA, "demo.txt"), "w").write("Thema-Datei\n")
    open(os.path.join(TEST_THEMA, "Rechnung_2026.pdf"), "w").write("x\n")
    open(os.path.join(ZWEITES, "demo.txt"), "w").write("anderes Thema\n")
    open(os.path.join(ANDERSWO, "demo.odt"), "w").write("woanders\n")
    open(os.path.join(ANDERSWO, "einmalig.txt"), "w").write("nur hier\n")


def abbauen():
    for ordner in (TEST_THEMA, ZWEITES, ANDERSWO):
        shutil.rmtree(ordner, ignore_errors=True)


def offen(*namen):
    """So tun, als hätte das Portal diese Fenster gemeldet."""
    bridge.fensterstand_merken([{"name": n} for n in namen])


def kurz(treffer):
    return sorted(os.path.basename(t) + "@" + os.path.basename(os.path.dirname(t))
                  for t in treffer)


try:
    aufbauen()

    print("\n1 · Datei im offenen Thema gewinnt")
    offen("Pruefthema")
    pruefe("'demo' bei offenem Pruefthema", kurz(bridge._dateien_suchen("demo")),
           ["demo.txt@Pruefthema"])
    pruefe("'demo.txt' bei offenem Pruefthema", kurz(bridge._dateien_suchen("demo.txt")),
           ["demo.txt@Pruefthema"])

    print("\n2 · Kein Thema offen: alle Treffer, also fragen")
    offen()
    pruefe("'demo' ohne offenes Thema", kurz(bridge._dateien_suchen("demo")),
           ["demo.odt@Pruefordner", "demo.txt@Pruefthema", "demo.txt@Pruefthema2"])

    print("\n3 · Zwei Themen offen, in beiden liegt etwas: fragen")
    offen("Pruefthema", "Pruefthema2")
    pruefe("'demo' bei zwei offenen Themen", kurz(bridge._dateien_suchen("demo")),
           ["demo.txt@Pruefthema", "demo.txt@Pruefthema2"])

    print("\n4 · Teil eines Namens, Groß/klein egal")
    offen()
    pruefe("'rechnung'", kurz(bridge._dateien_suchen("rechnung")),
           ["Rechnung_2026.pdf@Pruefthema"])
    pruefe("'EINMALIG'", kurz(bridge._dateien_suchen("EINMALIG")),
           ["einmalig.txt@Pruefordner"])

    print("\n5 · Gibt es nicht")
    pruefe("'gibtesnicht'", kurz(bridge._dateien_suchen("gibtesnicht")), [])

    print("\n6 · open_file: eine Datei öffnen, bei mehreren fragen")
    offen("Pruefthema")
    bridge.portal_aktionen_abholen()
    antwort = bridge.open_file("demo")
    pruefe("open_file('demo') öffnet", "wird geoeffnet" in antwort, True)
    aktionen = bridge.portal_aktionen_abholen()
    pruefe("open_file('demo') nimmt die Thema-Datei",
           [os.path.basename(os.path.dirname(a["pfad"])) for a in aktionen if a["typ"] == "datei_oeffnen"],
           ["Pruefthema"])
    offen()
    antwort = bridge.open_file("demo")
    pruefe("open_file bei mehreren fragt", "Welche" in antwort or "welche" in antwort, True)
    pruefe("open_file bei mehreren öffnet NICHTS",
           [a for a in bridge.portal_aktionen_abholen() if a["typ"] == "datei_oeffnen"], [])
    antwort = bridge.open_file("gibtesnicht")
    pruefe("open_file ohne Treffer sagt es", "gibt es nicht" in antwort or "existiert nicht" in antwort, True)

    print("\n7 · Gegenprobe: das Falsche darf NICHT gehen")
    pruefe("Ordnername ist keine Datei", kurz(bridge._dateien_suchen("Pruefordner")), [])
    pruefe("leerer Name findet nichts", kurz(bridge._dateien_suchen("")), [])
finally:
    abbauen()
    bridge.fensterstand_merken([])

print("\n" + "=" * 70)
print("  %d Prüfungen, %d Fehler" % (geprueft, len(fehler)))
if fehler:
    print("  ROT:", ", ".join(fehler))
print("=" * 70)
sys.exit(1 if fehler else 0)
