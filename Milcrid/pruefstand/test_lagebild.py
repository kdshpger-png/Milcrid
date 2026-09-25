#!/usr/bin/env python3
"""Prüfstand: sieht Milcrid, was gerade offen ist? (Lagebild, 20.09.2026)

Klaus' Wunsch: die KI soll wissen, welche Fenster offen sind, welches er
gerade ansieht, was im Thema liegt - und mitbekommen, wenn etwas
dazwischenkommt (Update-Frage, "alte Sitzung wiederherstellen").
"""
import os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # ~/Milcrid, auch beim Nutzer
import bridge

THEMA = os.path.join(bridge.BASE_DIR, "Schreibtisch Ablagen", "Pruefthema")
THEMA2 = os.path.join(bridge.BASE_DIR, "Schreibtisch Ablagen", "Pruefthema2")
fehler = []
geprueft = 0


def pruefe(was, bedingung, text=""):
    global geprueft
    geprueft += 1
    if bedingung:
        print("  ok   %-56s %s" % (was, text[:60]))
    else:
        fehler.append(was)
        print("  ROT  %-56s %s" % (was, text[:100]))


def melden(*fenster):
    """(Name, vorne) wie das Portal es meldet."""
    bridge.fensterstand_merken([{"name": n, "vorne": v, "gross": False, "klein": False}
                                for n, v in fenster])


try:
    os.makedirs(THEMA, exist_ok=True)
    os.makedirs(THEMA2, exist_ok=True)
    open(os.path.join(THEMA, "demo.txt"), "w").write("vorn\n")
    open(os.path.join(THEMA, "brief.odt"), "w").write("x\n")
    open(os.path.join(THEMA2, "demo.txt"), "w").write("hinten\n")

    print("\n1 · Nichts offen")
    melden()
    t = bridge.lagebild()
    pruefe("sagt, dass kein Fenster offen ist", "Kein Portal-Fenster ist offen" in t, t)

    print("\n2 · Zwei Fenster, eines vorne")
    melden(("Pruefthema", True), ("Milcrid Uhr", False))
    t = bridge.lagebild()
    pruefe("nennt beide Fenster", "Pruefthema" in t and "Milcrid Uhr" in t, t)
    pruefe("markiert das vordere", "Pruefthema (vorne)" in t, t)
    pruefe("nennt die Dateien des vorderen Themas",
           "demo.txt" in t and "brief.odt" in t, t)
    pruefe("bleibt kurz (unter 400 Zeichen)", len(t) < 400, "%d Zeichen" % len(t))

    print("\n3 · Das vordere Thema gewinnt bei der Dateisuche")
    melden(("Pruefthema2", True), ("Pruefthema", False))
    treffer = bridge._dateien_suchen("demo")
    pruefe("'demo' nimmt die Datei aus dem VORDEREN Thema",
           treffer == [os.path.join(THEMA2, "demo.txt")], str(treffer))
    melden(("Pruefthema", True), ("Pruefthema2", False))
    treffer = bridge._dateien_suchen("demo")
    pruefe("andersherum genauso",
           treffer == [os.path.join(THEMA, "demo.txt")], str(treffer))

    print("\n4 · Gegenprobe: nichts erfinden")
    melden(("Pruefthema", True))
    t = bridge.lagebild()
    pruefe("nennt kein Fenster, das nicht gemeldet wurde", "Milcrid Uhr" not in t, t)
    pruefe("sagt dem Modell, nichts zu vermuten", "statt es zu vermuten" in t, "")
    pruefe("Dateien eines NICHT offenen Themas kommen nicht vor",
           "hinten" not in t, t)
finally:
    shutil.rmtree(THEMA, ignore_errors=True)
    shutil.rmtree(THEMA2, ignore_errors=True)
    bridge.fensterstand_merken([])

print("\n" + "=" * 70)
print("  %d Prüfungen, %d Fehler" % (geprueft, len(fehler)))
if fehler:
    print("  ROT:", ", ".join(fehler))
print("=" * 70)
sys.exit(1 if fehler else 0)
