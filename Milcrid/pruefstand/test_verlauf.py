"""Test fuer _anleitung_abschliessen / _verlauf_kuerzen / gespraech_komplett
(Opus 2026-09-19). Laeuft in einer Probe-Kopie, OHNE Portal und OHNE Modell:
die Sitzung wird ohne __init__ gebaut."""
import copy, sys
import main, config

def sitzung(anzahl_zuege, gesamt_anteil):
    s = main.PortalSitzung.__new__(main.PortalSitzung)
    s.messages = [{"role": "system", "content": "S" * 5000},
                  {"role": "user", "content": "[Zusammenfassungen] " + "Z" * 2000},
                  {"role": "assistant", "content": "Verstanden."}]
    s._kopf = 3
    for i in range(anzahl_zuege):
        s.messages += [{"role": "user", "content": f"Befehl {i} " + "x" * 300},
                       {"role": "assistant", "content": f"[TOOL_CALL: open_app(name=\"U{i}\")]"},
                       {"role": "user", "content": "[WERKZEUG-ERGEBNIS]\n" + "e" * 200},
                       {"role": "assistant", "content": f"Antwort {i}."}]
    s._ausgeblendet = []
    s._mit_anleitung = []
    s.warnung_90_gesendet = False
    s.sitzung_id = "test"
    maxi = config.KONTEXT_FENSTER or config.STANDARD_FENSTER
    s.tokens = {"gesamt": int(gesamt_anteil * maxi), "max": maxi, "prozent": gesamt_anteil * 100}
    return s, maxi

fehler = 0
def pruef(bed, text):
    global fehler
    print(("OK  " if bed else "ROT ") + text)
    fehler += (not bed)

# 1) Kuerzen bei 80 %
s, maxi = sitzung(40, 0.80)
vorher = copy.deepcopy(s.messages)
s._verlauf_kuerzen()
pruef(len(s.messages) < len(vorher), f"gekuerzt: {len(vorher)} -> {len(s.messages)} Nachrichten")
pruef(s.messages[:3] == vorher[:3], "Kopf (System, Erinnerung) unveraendert")
erste = s.messages[3]
pruef(erste["role"] == "user" and erste["content"].startswith("Befehl"), f"Schnitt an Zuggrenze: {erste['content'][:12]!r}")
pruef(s.messages[-8:] == vorher[-8:], "letzte zwei Zuege unveraendert")
pruef(s.gespraech_komplett() == vorher, "gespraech_komplett == alter Verlauf (nichts verloren)")
pruef(s.tokens["prozent"] <= 41, f"Schaetzung danach {s.tokens['prozent']} % (Ziel <= 40)")
pruef(s.tokens["frage_speichern"] is True, "beim ersten Kuerzen Speicherfrage")
# echter Anteil nach Zeichen nachrechnen
anteil = sum(len(m["content"]) for m in s.messages) / sum(len(m["content"]) for m in vorher) * 0.80
pruef(0.30 <= anteil <= 0.42, f"nachgerechnet nach Zeichen: {anteil*100:.0f} %")

# 2) zweites Kuerzen: keine zweite Speicherfrage, Reihenfolge bleibt
s.tokens["gesamt"] = int(0.80 * maxi)
s.messages += [{"role": "user", "content": "noch ein Befehl"}, {"role": "assistant", "content": "ok"}]
voll = s.gespraech_komplett()
s._verlauf_kuerzen()
pruef(s.tokens["frage_speichern"] is False, "zweites Kuerzen fragt nicht noch einmal")
pruef(s.gespraech_komplett() == voll, "auch nach zweitem Kuerzen nichts verloren, Reihenfolge stimmt")

# 3) Gegenprobe: unter der Schwelle passiert nichts
s, maxi = sitzung(40, 0.60)
vorher = copy.deepcopy(s.messages)
s._verlauf_kuerzen()
pruef(s.messages == vorher and s._ausgeblendet == [], "bei 60 % bleibt alles stehen")

# 4) Gegenprobe: nur zwei Zuege -> nie kuerzen, auch wenn voll
s, maxi = sitzung(2, 0.95)
vorher = copy.deepcopy(s.messages)
s._verlauf_kuerzen()
pruef(s.messages == vorher, "mit nur zwei Zuegen wird nicht gekuerzt")

# 5) Stufe 1: Anleitungen bleiben bis zum Aufraeumen, dann alle auf einmal raus
s, maxi = sitzung(0, 0.1)
ANL = "[Zusätzliches Werkzeug für diese Anfrage verfügbar:] " + "a" * 2200 + "\n\n"
for i in range(20):
    n = {"role": "user", "content": ANL + f"minimiere Fenster {i}"}
    s.messages += [n, {"role": "assistant", "content": "[TOOL_CALL: minimize_window(name=\"x\")]"},
                   {"role": "user", "content": "[WERKZEUG-ERGEBNIS]\nok"}, {"role": "assistant", "content": "Erledigt."}]
    s._mit_anleitung.append((n, f"minimiere Fenster {i}"))
vorher = copy.deepcopy(s.messages)
s._verlauf_kuerzen()                       # bei 10 %: nichts
pruef(s.messages == vorher, "unter 75 %: Anleitungen bleiben stehen (Zwischenspeicher bleibt gueltig)")
komplett = s.gespraech_komplett()
pruef(all("Zusätzliches Werkzeug" not in str(m["content"]) for m in komplett[3:]), "Speichern: Transkript ohne Anleitungen")
pruef(any("Zusätzliches Werkzeug" in str(m["content"]) for m in s.messages), "...aber der laufende Verlauf hat sie noch")
s.tokens["gesamt"] = int(0.80 * maxi)
s._verlauf_kuerzen()
pruef(all("Zusätzliches Werkzeug" not in str(m["content"]) for m in s.messages), "ab 75 %: alle Anleitungen auf einmal entfernt")
pruef(s._ausgeblendet == [], "Anleitungen allein reichten - kein Zug musste weg")
pruef(s.messages[-4]["content"] == "minimiere Fenster 19", "Klaus' Satz bleibt stehen")
pruef(s.tokens["prozent"] < 40, f"danach {s.tokens['prozent']} %")
pruef(s._mit_anleitung == [], "Liste danach leer")
pruef(s.tokens["frage_speichern"] is False, "nur Anleitungen entfernt: keine Speicherfrage")

print("\nFEHLER:", fehler)
sys.exit(1 if fehler else 0)
