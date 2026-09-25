#!/usr/bin/env python3
"""Prüfstand: Kürzel für Direkt-Aufgaben (Klaus-Wunsch 2026-09-20).

"cjs = chat jetzt speichern - wenn man am Tippen ist, geht cjs+Enter
schneller als 'computer speichere chat'." Wichtig ist vor allem, dass ein
Kürzel NUR dann greift, wenn es allein dasteht - sonst löst ein normaler
Satz, in dem die drei Buchstaben vorkommen, plötzlich etwas aus.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # ~/Milcrid, auch beim Nutzer
import direktaufgaben_verwaltung as da

fehler, geprueft = [], 0


def pruefe(was, ist, soll):
    global geprueft
    geprueft += 1
    if ist == soll:
        print("  ok   %-54s %s" % (was, str(ist)[:40]))
    else:
        fehler.append(was)
        print("  ROT  %-54s %s (erwartet: %s)" % (was, str(ist)[:50], soll))


sicherung = open(da.AUFGABEN_PFAD, encoding="utf-8").read() if os.path.exists(da.AUFGABEN_PFAD) else None
try:
    # Eigene Ablage für den Test, Klaus' Liste bleibt unberührt
    json.dump([{"name": "Chat speichern", "text": "speicher den chat", "kuerzel": "cjs"},
               {"name": "Uhr", "text": "öffne Uhr", "kuerzel": "ua"}],
              open(da.AUFGABEN_PFAD, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("\n1 · Ein Kürzel allein löst aus")
    pruefe("'cjs'", (da.kuerzel_aufloesen("cjs") or {}).get("text"), "speicher den chat")
    pruefe("'CJS' (groß)", (da.kuerzel_aufloesen("CJS") or {}).get("text"), "speicher den chat")
    pruefe("' ua ' (mit Leerzeichen)", (da.kuerzel_aufloesen(" ua ") or {}).get("text"), "öffne Uhr")
    pruefe("'cjs.' (mit Punkt)", (da.kuerzel_aufloesen("cjs.") or {}).get("text"), "speicher den chat")

    print("\n2 · Im Satz löst es NICHT aus")
    pruefe("'mach mal cjs bitte'", da.kuerzel_aufloesen("mach mal cjs bitte"), None)
    pruefe("'cjs und dann noch was'", da.kuerzel_aufloesen("cjs und dann noch was"), None)
    pruefe("'speicher den chat'", da.kuerzel_aufloesen("speicher den chat"), None)
    pruefe("leere Eingabe", da.kuerzel_aufloesen(""), None)
    pruefe("unbekanntes Kürzel 'xyz'", da.kuerzel_aufloesen("xyz"), None)

    print("\n3 · Was als Kürzel erlaubt ist")
    pruefe("leer ist erlaubt (kein Kürzel)", da.kuerzel_pruefen(""), None)
    pruefe("ein Zeichen ist zu kurz", bool(da.kuerzel_pruefen("a")), True)
    pruefe("mit Leerzeichen abgelehnt", bool(da.kuerzel_pruefen("c j")), True)
    pruefe("Umlaut abgelehnt", bool(da.kuerzel_pruefen("cüs")), True)
    pruefe("doppeltes Kürzel abgelehnt", bool(da.kuerzel_pruefen("cjs")), True)
    pruefe("dasselbe beim eigenen Eintrag erlaubt",
           da.kuerzel_pruefen("cjs", ausser="Chat speichern"), None)

    print("\n4 · Setzen und ändern")
    pruefe("neues Kürzel setzen", da.kuerzel_setzen("Uhr", "u1")["erfolg"], True)
    pruefe("greift danach", (da.kuerzel_aufloesen("u1") or {}).get("text"), "öffne Uhr")
    pruefe("altes Kürzel greift nicht mehr", da.kuerzel_aufloesen("ua"), None)
    pruefe("Kürzel eines unbekannten Eintrags", da.kuerzel_setzen("Gibtsnicht", "gg")["erfolg"], False)
    pruefe("Auftrag ändern", da.text_setzen("Uhr", "öffne Milcrid Uhr")["erfolg"], True)
    pruefe("neuer Auftrag steht", (da.kuerzel_aufloesen("u1") or {}).get("text"), "öffne Milcrid Uhr")
    pruefe("leerer Auftrag abgelehnt", da.text_setzen("Uhr", "  ")["erfolg"], False)
finally:
    if sicherung is not None:
        open(da.AUFGABEN_PFAD, "w", encoding="utf-8").write(sicherung)

print("\n" + "=" * 70)
print("  %d Prüfungen, %d Fehler" % (geprueft, len(fehler)))
if fehler:
    print("  ROT:", ", ".join(fehler))
print("=" * 70)
sys.exit(1 if fehler else 0)
