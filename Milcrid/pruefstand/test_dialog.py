#!/usr/bin/env python3
"""Prüfstand: fremde Dialoge - Regel-Liste und die Sperre vor dem Klicken.

Klaus' Gedanke vom 20.09.2026: die KI liest den Dialog, ein SKRIPT sagt, was
zu tun ist ("Update kommt immer wieder - mitten in der Arbeit heißt das
später, also Abbrechen"). Und: nie selbst klicken, bevor Klaus zugestimmt hat.
"""
import os, sys, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # ~/Milcrid, auch beim Nutzer
import dialog_verwaltung as dv
import faehigkeiten_verwaltung as fv
import bridge

# Die Faehigkeit ist ab Werk AUS (Klaus schaltet sie im Portal ein) - fuer den
# Lauf einschalten und danach genau so zuruecksetzen, wie sie war.
_WAR_AN = fv.ist_aktiv("fenster_vorlesen")
fv.umschalten("fenster_vorlesen", True)

fehler, geprueft = [], 0


def pruefe(was, ist, soll):
    global geprueft
    geprueft += 1
    if ist == soll:
        print("  ok   %-56s %s" % (was, str(ist)[:50]))
    else:
        fehler.append(was)
        print("  ROT  %-56s %s (erwartet: %s)" % (was, str(ist)[:60], soll))


# Regeln auf einer Kopie prüfen, damit Klaus' echte Zähler unberührt bleiben
sicherung = {}
for pfad in (dv.REGEL_PFAD, dv.UNBEKANNT_PFAD):
    if os.path.exists(pfad):
        sicherung[pfad] = open(pfad, encoding="utf-8").read()
try:
    print("\n1 · Die Liste erkennt die bekannten Fälle")
    r = dv.regel_fuer("Bestätigung", "LibreOffice-Dokumentwiederherstellungsdaten verwerfen?")
    pruefe("Wiederherstellung -> abbrechen", r and r["vorschlag"], "abbrechen")
    r = dv.regel_fuer("Dokument speichern?", "Änderungen am Dokument vor dem Schließen speichern?")
    pruefe("Speichern-Frage -> nichts tun", r and r["vorschlag"], "nichts")
    r = dv.regel_fuer("Software-Aktualisierung", "Update verfügbar, jetzt neu starten?")
    pruefe("Update -> abbrechen", r and r["vorschlag"], "abbrechen")
    pruefe("Portal-Fenster ist kein Dialog", dv.regel_fuer("Milcrid Uhr", "12:30"), None)

    print("\n2 · Was wir noch nicht kennen, wird gemerkt")
    dv.regel_fuer("Ganz neues Fenster", "irgendeine Frage")
    dv.regel_fuer("Ganz neues Fenster", "irgendeine Frage")
    treffer = [e for e in dv.unbekannte() if e["titel"] == "Ganz neues Fenster"]
    pruefe("unbekanntes Fenster landet in der Liste", bool(treffer), True)
    pruefe("und wird gezählt", treffer[0]["anzahl"] if treffer else 0, 2)

    print("\n3 · Veraltete Regeln findet man")
    namen = [r["name"] for r in dv.veraltet(tage=3650)]
    pruefe("mit 10 Jahren Frist ist nichts veraltet", namen, [])

    print("\n4 · Gesperrt: klicken ohne Klaus' Zustimmung")
    bridge._DIALOG_ANFRAGE["fenster"] = ""
    pruefe("ohne offene Frage abgelehnt",
           bridge.dialog_abbrechen("egal").startswith("[Abgelehnt"), True)
    bridge._DIALOG_ANFRAGE["fenster"] = "Testfenster"
    bridge._DIALOG_ANFRAGE["eingabe_nr"] = bridge._EINGABE_ZAEHLER
    pruefe("im selben Zug abgelehnt (Klaus hat nicht geantwortet)",
           bridge.dialog_abbrechen("Testfenster").startswith("[Abgelehnt"), True)

    print("\n5 · Erlaubt, wenn Klaus geantwortet hat - dann wird Escape gedrückt")
    gedrueckt = []
    echtes_finden, echtes_run = bridge._fremdes_fenster_finden, bridge.subprocess.run

    # "geschlossen" ist der Zustand des nachgestellten Fensters: Escape
    # schliesst es, genau wie bei einem echten Dialog. Vor jedem Block, der
    # Erfolg erwartet, wird es wieder aufgemacht.
    geschlossen = {"ja": False}

    def finden(name):
        if geschlossen["ja"]:
            return None
        return ("0x123", "Testfenster", 0, 0, 100, 50)

    def run(befehl, **rest):
        gedrueckt.append(befehl)
        if any("Escape" in str(t) for t in befehl):
            geschlossen["ja"] = True
        class E: returncode = 0
        return E()

    bridge._fremdes_fenster_finden = finden
    bridge.subprocess.run = run
    try:
        geschlossen["ja"] = False
        bridge._DIALOG_ANFRAGE["fenster"] = "Testfenster"
        bridge._DIALOG_ANFRAGE["eingabe_nr"] = bridge._EINGABE_ZAEHLER - 1
        antwort = bridge.dialog_abbrechen("Testfenster")
        pruefe("meldet Abbrechen", "Abbrechen gedrueckt" in antwort, True)
        pruefe("hat wirklich Escape geschickt",
               any("Escape" in str(b) for b in gedrueckt), True)
        pruefe("Frage ist danach zu", bridge._DIALOG_ANFRAGE["fenster"], "")
        pruefe("zweites Mal wird wieder abgelehnt",
               bridge.dialog_abbrechen("Testfenster").startswith("[Abgelehnt"), True)
    finally:
        bridge._fremdes_fenster_finden = echtes_finden
        bridge.subprocess.run = echtes_run

    print("\n6 · Klaus' „ja bitte\" kommt beim Werkzeug an (Klaus-Fund 20.09.)")
    # Der eigentliche Fehler war NICHT die Sperre, sondern dass die Faehigkeit
    # bei einer stichwortlosen Antwort gar nicht erst mitgeladen wurde.
    def wird_angeboten(satz, schon_gezeigt=None):
        _, neue = fv.kontext_fuer_eingabe(satz, set(schon_gezeigt or []))
        return "fenster_vorlesen" in neue

    bridge._dialog_anfrage_loeschen()
    # Gegenprobe zuerst: ohne offene Frage darf "ja bitte" NICHTS mitbringen.
    pruefe("ohne offene Frage bringt „ja bitte\" nichts", wird_angeboten("ja bitte"), False)
    pruefe("Stichwort wirkt weiter wie immer", wird_angeboten("was steht in dem Fenster"), True)

    bridge._dialog_anfrage_setzen("Testfenster")
    pruefe("bei offener Frage kommt „ja bitte\" an", wird_angeboten("ja bitte"), True)
    pruefe("auch „mach das\"", wird_angeboten("mach das"), True)
    pruefe("auch schon einmal gezeigt", wird_angeboten("ja", ["fenster_vorlesen"]), True)

    # Der Schalter im Portal muss trotzdem das letzte Wort behalten.
    fv.umschalten("fenster_vorlesen", False)
    pruefe("ausgeschaltet bleibt aus, auch bei offener Frage",
           wird_angeboten("ja bitte"), False)
    fv.umschalten("fenster_vorlesen", True)

    print("\n7 · Die offene Frage wird auch wieder abgemeldet")
    pruefe("angemeldet, solange die Frage steht",
           "fenster_vorlesen" in fv.offene_fragen(), True)
    bridge._dialog_anfrage_loeschen()
    pruefe("nach dem Schliessen abgemeldet",
           "fenster_vorlesen" in fv.offene_fragen(), False)
    pruefe("und „ja bitte\" bringt wieder nichts", wird_angeboten("ja bitte"), False)

    # Und der Weg, den Klaus wirklich geht: vorlesen -> abbrechen -> zu.
    bridge._dialog_anfrage_setzen("Testfenster")
    bridge._DIALOG_ANFRAGE["eingabe_nr"] = bridge._EINGABE_ZAEHLER - 1
    geschlossen["ja"] = False
    bridge._fremdes_fenster_finden = finden
    bridge.subprocess.run = run
    try:
        bridge.dialog_abbrechen("Testfenster")
    finally:
        bridge._fremdes_fenster_finden = echtes_finden
        bridge.subprocess.run = echtes_run
    pruefe("nach echtem Abbrechen abgemeldet",
           "fenster_vorlesen" in fv.offene_fragen(), False)

    # Fenster inzwischen weg -> ebenfalls abmelden, sonst haengt die
    # Faehigkeit fuer den Rest der Sitzung an jeder Eingabe.
    bridge._dialog_anfrage_setzen("Verschwundenes")
    bridge._DIALOG_ANFRAGE["eingabe_nr"] = bridge._EINGABE_ZAEHLER - 1
    bridge._fremdes_fenster_finden = lambda name: None
    try:
        bridge.dialog_abbrechen("Verschwundenes")
    finally:
        bridge._fremdes_fenster_finden = echtes_finden
    pruefe("Fenster weg -> auch abgemeldet",
           "fenster_vorlesen" in fv.offene_fragen(), False)

    print("\n8 · Der schnelle Weg: „brich ab\" ohne Modell")
    import werkzeug_worte_verwaltung as merkliste
    def merk(satz):
        t = merkliste.passenden_eintrag_finden(satz)
        return t.get("werkzeug", "") if t.get("art") == "eindeutig" else t.get("art")
    pruefe("„ja brich ab\" geht direkt ins Werkzeug", merk("ja brich ab"), "dialog_abbrechen")
    pruefe("„brich ab\" ebenso", merk("brich ab"), "dialog_abbrechen")
    # Gegenprobe: das blosse Ja darf NICHT am Modell vorbei klicken.
    pruefe("„ja bitte\" landet NICHT im Werkzeug",
           merk("ja bitte") == "dialog_abbrechen", False)
    pruefe("„ja\" allein auch nicht", merk("ja") == "dialog_abbrechen", False)

    print("\n9 · Nochmal vorlesen darf die Uhr nicht zurückstellen (Live-Fund 20.09.)")
    # Auf "ja bitte" ruft das Modell erst fenster_vorlesen und dann
    # dialog_abbrechen - beides im selben Zug. Stellt das Vorlesen dabei die
    # Uhr neu, lehnt der Abbruch mit "Klaus hat nicht geantwortet" ab und das
    # Fenster bleibt für immer offen.
    bridge._dialog_anfrage_loeschen()
    bridge._EINGABE_ZAEHLER = 100
    bridge._dialog_anfrage_setzen("Software-Aktualisierung")
    pruefe("Uhr steht auf dem Zug des Vorlesens",
           bridge._DIALOG_ANFRAGE["eingabe_nr"], 100)

    bridge._EINGABE_ZAEHLER = 101              # Klaus sagt "ja bitte"
    bridge._dialog_anfrage_setzen("Software-Aktualisierung")   # Modell liest nochmal vor
    pruefe("dasselbe Fenster lässt die Uhr stehen",
           bridge._DIALOG_ANFRAGE["eingabe_nr"], 100)

    gedrueckt.clear()
    geschlossen["ja"] = False
    bridge._fremdes_fenster_finden = finden
    bridge.subprocess.run = run
    try:
        antwort = bridge.dialog_abbrechen("Software-Aktualisierung")
    finally:
        bridge._fremdes_fenster_finden = echtes_finden
        bridge.subprocess.run = echtes_run
    pruefe("und der Abbruch geht jetzt durch", "Abbrechen gedrueckt" in antwort, True)
    pruefe("Escape ist wirklich geschickt worden",
           any("Escape" in str(b) for b in gedrueckt), True)

    # Gegenprobe: ein ANDERES Fenster muss die Uhr sehr wohl neu starten,
    # sonst könnte Klaus' altes "ja" ein frisch aufgeplopptes Fenster treffen.
    bridge._dialog_anfrage_loeschen()
    bridge._EINGABE_ZAEHLER = 200
    bridge._dialog_anfrage_setzen("Erstes Fenster")
    bridge._EINGABE_ZAEHLER = 201
    bridge._dialog_anfrage_setzen("Ganz anderes Fenster")
    pruefe("anderes Fenster startet die Uhr neu",
           bridge._DIALOG_ANFRAGE["eingabe_nr"], 201)
    pruefe("und im selben Zug wird abgelehnt",
           bridge.dialog_abbrechen("Ganz anderes Fenster").startswith("[Abgelehnt"), True)
    bridge._dialog_anfrage_loeschen()

    print("\n10 · Gemeldet wird die Wirklichkeit, nicht der Rückgabecode")
    # Beide Richtungen sind am 20.09. wirklich aufgetreten und waren falsch.
    def mit_fenstern(folge):
        """_fremdes_fenster_finden gibt der Reihe nach zurück, was folge sagt."""
        rest = list(folge)
        def finden(name):
            return rest.pop(0) if rest else None
        return finden

    FENSTER = ("0x123", "Software-Aktualisierung", 0, 0, 100, 50)

    def abbrechen_mit(finden, xdotool_rueckgabe):
        def run(befehl, **rest):
            class E:
                returncode = xdotool_rueckgabe
            if xdotool_rueckgabe:
                raise bridge.subprocess.CalledProcessError(xdotool_rueckgabe, befehl)
            return E()
        bridge._fremdes_fenster_finden = finden
        bridge.subprocess.run = run
        try:
            bridge._EINGABE_ZAEHLER = 500
            bridge._dialog_anfrage_setzen("Software-Aktualisierung")
            bridge._EINGABE_ZAEHLER = 501
            return bridge.dialog_abbrechen("Software-Aktualisierung")
        finally:
            bridge._fremdes_fenster_finden = echtes_finden
            bridge.subprocess.run = echtes_run

    # a) Escape wirkt, aber xdotool bricht mit BadWindow ab, weil das Fenster
    #    unter ihm wegstirbt. Frueher: "hat nicht geklappt", obwohl es klappte.
    antwort = abbrechen_mit(mit_fenstern([FENSTER]), 0)   # danach nicht mehr da
    pruefe("Fenster zu -> Erfolg gemeldet", "jetzt zu" in antwort, True)
    pruefe("und die Frage ist abgemeldet",
           "fenster_vorlesen" in fv.offene_fragen(), False)

    # b) Das Fenster beachtet Escape gar nicht (xmessage tut das nicht).
    #    Frueher: xdotool meldet 0, Milcrid meldete Erfolg - der Dialog stand
    #    aber weiter im Weg. Ein erfundener Erfolg ist schlimmer als ein
    #    Fehlschlag.
    antwort = abbrechen_mit(mit_fenstern([FENSTER] * 20), 0)
    pruefe("Fenster bleibt -> KEIN Erfolg gemeldet", "jetzt zu" in antwort, False)
    pruefe("sondern die Wahrheit", "immer noch offen" in antwort, True)
    pruefe("und die Frage bleibt offen",
           "fenster_vorlesen" in fv.offene_fragen(), True)
    bridge._dialog_anfrage_loeschen()

    # c) Das Fenster war schon weg, bevor überhaupt gedrückt wurde - dann
    #    steht der Name trotzdem in der Meldung (stand dort mal als "").
    antwort = abbrechen_mit(mit_fenstern([]), 0)
    pruefe("Name steht in der Meldung",
           "Software-Aktualisierung" in antwort, True)

    print("\n11 · Escape wird immer wieder losgelassen (Fund 20.09.)")
    # Bleibt Escape haengen, wiederholt es sich 25-mal pro Sekunde: jeder
    # Dialog schliesst sich dann von selbst und Klaus' Eingaben geraten
    # durcheinander. Gemessen: 173 Anschlaege in 7 Sekunden.
    befehle = []

    def run_merkt(befehl, **rest):
        befehle.append(list(befehl))
        if any("Escape" in str(t) for t in befehl) and befehl[1] == "key":
            geschlossen["ja"] = True
        class E:
            returncode = 0
        return E()

    geschlossen["ja"] = False
    bridge._fremdes_fenster_finden = finden
    bridge.subprocess.run = run_merkt
    try:
        bridge._EINGABE_ZAEHLER = 600
        bridge._dialog_anfrage_setzen("Testfenster")
        bridge._EINGABE_ZAEHLER = 601
        bridge.dialog_abbrechen("Testfenster")
    finally:
        bridge._fremdes_fenster_finden = echtes_finden
        bridge.subprocess.run = echtes_run
    pruefe("es wird gedrückt", any(b[1] == "key" for b in befehle), True)
    pruefe("und danach wieder losgelassen",
           any(b[1] == "keyup" and b[2] == "Escape" for b in befehle), True)

    # Gegenprobe: auch wenn das Drücken schiefgeht, MUSS losgelassen werden -
    # gerade dann, denn genau da bleibt die Taste sonst hängen.
    befehle.clear()

    def run_kaputt(befehl, **rest):
        befehle.append(list(befehl))
        if befehl[1] == "key":
            raise bridge.subprocess.TimeoutExpired(befehl, 5)
        class E:
            returncode = 0
        return E()

    geschlossen["ja"] = False      # Fenster fuer diese Probe wieder aufmachen
    bridge._fremdes_fenster_finden = finden
    bridge.subprocess.run = run_kaputt
    try:
        bridge._EINGABE_ZAEHLER = 700
        bridge._dialog_anfrage_setzen("Testfenster")
        bridge._EINGABE_ZAEHLER = 701
        antwort = bridge.dialog_abbrechen("Testfenster")
    finally:
        bridge._fremdes_fenster_finden = echtes_finden
        bridge.subprocess.run = echtes_run
    pruefe("Fehlschlag wird gemeldet", "nicht geklappt" in antwort, True)
    pruefe("aber losgelassen wird trotzdem",
           any(b[1] == "keyup" and b[2] == "Escape" for b in befehle), True)
    bridge._dialog_anfrage_loeschen()
finally:
    fv.umschalten("fenster_vorlesen", _WAR_AN)
    for pfad, inhalt in sicherung.items():
        open(pfad, "w", encoding="utf-8").write(inhalt)
    if not sicherung.get(dv.UNBEKANNT_PFAD) and os.path.exists(dv.UNBEKANNT_PFAD):
        os.remove(dv.UNBEKANNT_PFAD)

print("\n" + "=" * 70)
print("  %d Prüfungen, %d Fehler" % (geprueft, len(fehler)))
if fehler:
    print("  ROT:", ", ".join(fehler))
print("=" * 70)
sys.exit(1 if fehler else 0)
