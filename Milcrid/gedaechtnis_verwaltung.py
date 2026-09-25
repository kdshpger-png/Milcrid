# gedaechtnis_verwaltung.py
# Portal > Profil Manager > KI Profil: Selbst, Tagebuch, Erfahrungs-Log und
# Gedaechtnis (Kurzzeit/Langzeit) - alle fuenf gleich aufgebaut (Klaus,
# 25.09.2026: "ein Feld von links - Anzeigen, Kopieren, Loeschen, An/Aus;
# Kopieren/Loeschen erst nach Anzeigen; am besten unter dem Feld, im Fenster
# selbst"). Vorher: Kurz-/Langzeit als Dateiliste mit Oeffnen (Firefox/Writer)
# und Kopieren-unter-neuem-Namen, Selbst/Tagebuch/Erfahrungs-Log "Noch nicht
# eingerichtet" - obwohl Tagebuch und Erfahrung seit 15.09. Eintraege hatten.
#
#   ansehen(art)   -> lesbare Eintraege (Titel + Text), neueste oben
#   loeschen(art)  -> in den Milcrid Papierkorb (zurueckholbar); beim Selbst
#                     nur der selbst-Teil, das fundament bleibt
#   aufzeichnen_umschalten(art, an) -> schreibt Milcrid dort weiter hinein?
#
# memory.py bleibt die EINZIGE Quelle fuer Pfade und Einstellungen (kein
# Zirkel-Import: memory.py kennt dieses Modul nicht).

import json
import os
import re
import shutil
import time

import memory

ARTEN = ("selbst", "tagebuch", "erfahrung", "kurzzeit", "langzeit")


def _json(pfad, standard):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return standard


def _datum(d):
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)", str(d or ""))
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else str(d or "")


def _lesbar(wert, einzug=""):
    """dict/list -> eingerueckter Text, wie man ihn vorliest (kein JSON)."""
    if isinstance(wert, dict):
        zeilen = []
        for k, v in wert.items():
            if k.startswith("_"):
                continue
            name = k.replace("_", " ")
            if isinstance(v, (dict, list)):
                inhalt = _lesbar(v, einzug + "  ")
                zeilen.append(f"{einzug}{name}:" + ("\n" + inhalt if inhalt else " (leer)"))
            else:
                zeilen.append(f"{einzug}{name}: {v}")
        return "\n".join(zeilen)
    if isinstance(wert, list):
        zeilen = []
        for v in wert:
            # Werte des Fundaments: "1. Wahrhaftigkeit – Sagt, was ist." statt
            # rang/wert/bedeutung untereinander (25.09.2026).
            if isinstance(v, dict) and "wert" in v and "bedeutung" in v:
                nr = f"{v['rang']}. " if v.get("rang") is not None else "• "
                zeilen.append(f"{einzug}{nr}{v['wert']} – {v['bedeutung']}")
                continue
            if isinstance(v, dict):
                zeilen.append(f"{einzug}• " + _lesbar(v, einzug + "  ").lstrip())
            else:
                zeilen.append(f"{einzug}• {v}")
        return "\n".join(zeilen)
    return f"{einzug}{wert}"


def _block_eintrag(block, textfeld, art_name=""):
    titel = " · ".join(t for t in (art_name, _datum(block.get("datum")),
                                    str(block.get("stichwort") or "").replace("_", " ")) if t)
    return {"titel": titel, "text": str(block.get(textfeld) or "").strip() or "(leer)"}


def _chat_dateien():
    try:
        return sorted((d for d in os.listdir(memory.LANGZEIT_ORDNER) if d.endswith(".txt")), reverse=True)
    except OSError:
        return []


def _chat_titel(name):
    m = re.match(r"(\d{4}-\d\d-\d\d)_(.+?)(?:_(\d\d)(\d\d)(\d\d))?\.txt$", name)
    if not m:
        return "Chat · " + name
    zeit = f" {m.group(3)}:{m.group(4)}" if m.group(3) else ""
    return f"Chat · {_datum(m.group(1))}{zeit} · {m.group(2).replace('_', ' ')}"


def _eintraege(art):
    if art == "selbst":
        ident = _json(os.path.join(memory.BASIS_ORDNER, "self", "identity.json"), {}) or {}
        selbst = _lesbar(ident.get("selbst") or {})
        return [
            {"titel": "Fundament – ändert nur Klaus", "text": _lesbar(ident.get("fundament") or {}) or "(leer)"},
            {"titel": "Selbstbild – schreibt Milcrid fort", "text": selbst if selbst.strip("•: \n") else "(noch leer)"},
        ]
    if art == "tagebuch":
        return [_block_eintrag(b, "diary_entry") for b in reversed(_json(memory.TAGEBUCH_DATEI, []) or [])]
    if art == "erfahrung":
        return [_block_eintrag(b, "experience_log") for b in reversed(_json(memory.ERFAHRUNG_DATEI, []) or [])]
    if art == "kurzzeit":
        return [_block_eintrag(b, "zusammenfassung") for b in (_json(memory.KURZZEIT_DATEI, []) or [])]
    if art == "langzeit":
        eintraege = [_block_eintrag(b, "zusammenfassung", "Zusammenfassung")
                     for b in reversed(_json(memory.LANGZEIT_JSON_DATEI, []) or [])]
        for name in _chat_dateien():
            try:
                with open(os.path.join(memory.LANGZEIT_ORDNER, name), encoding="utf-8", errors="replace") as f:
                    text = f.read().strip()
            except OSError:
                text = ""
            eintraege.append({"titel": _chat_titel(name), "text": text or "(leer)"})
        return eintraege
    return []


def _anzahl(art):
    if art == "selbst":
        ident = _json(os.path.join(memory.BASIS_ORDNER, "self", "identity.json"), {}) or {}
        return sum(len(v) for k, v in (ident.get("selbst") or {}).items() if isinstance(v, list))
    if art == "langzeit":
        return len(_json(memory.LANGZEIT_JSON_DATEI, []) or []) + len(_chat_dateien())
    pfad = {"tagebuch": memory.TAGEBUCH_DATEI, "erfahrung": memory.ERFAHRUNG_DATEI,
            "kurzzeit": memory.KURZZEIT_DATEI}[art]
    return len(_json(pfad, []) or [])


def info():
    memory.archiv_migrieren()  # einmalige Umstellung alte archiv.json -> long-term.json, danach No-op
    return {"einstellungen": memory.einstellungen_lesen(),
            "anzahlen": {a: _anzahl(a) for a in ARTEN}}


def ansehen(art):
    if art not in ARTEN:
        return {"erfolg": False, "fehler": "Unbekannte Art."}
    return {"erfolg": True, "art": art, "eintraege": _eintraege(art)}


def aufzeichnen_umschalten(art, an):
    if art not in ARTEN:
        return {"erfolg": False, "fehler": "Unbekannte Art."}
    daten = memory.einstellungen_lesen()
    daten[f"{art}_aufzeichnen"] = bool(an)
    memory.einstellungen_schreiben(daten)
    return {"erfolg": True, "art": art}


def loeschen(art):
    """In den Papierkorb - zurueckholbar im Fenster "Milcrid Papierkorb"."""
    import papierkorb_verwaltung
    if art not in ARTEN:
        return {"erfolg": False, "fehler": "Unbekannte Art."}
    weg = []
    if art == "selbst":
        # Nur den selbst-Teil leeren; vorher eine Kopie der ganzen Datei in den
        # Papierkorb, damit das alte Selbstbild zurueckholbar bleibt.
        import identity
        pfad = identity.IDENTITY_PFAD
        ident = _json(pfad, None)
        if not isinstance(ident, dict):
            return {"erfolg": False, "fehler": "self/identity.json fehlt oder ist unlesbar."}
        kopie = os.path.join(os.path.dirname(pfad), f"identity (Selbstbild bis {time.strftime('%Y-%m-%d %H%M')}).json")
        shutil.copy2(pfad, kopie)
        weg.append(kopie)
        selbst = ident.get("selbst") or {}
        for feld in identity.ERLAUBTE_SELBST_FELDER:
            selbst[feld] = []
        ident["selbst"] = selbst
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(ident, f, ensure_ascii=False, indent=2)
    elif art == "langzeit":
        weg += [os.path.join(memory.LANGZEIT_ORDNER, n) for n in _chat_dateien()]
        weg.append(memory.LANGZEIT_JSON_DATEI)
    else:
        weg.append({"tagebuch": memory.TAGEBUCH_DATEI, "erfahrung": memory.ERFAHRUNG_DATEI,
                    "kurzzeit": memory.KURZZEIT_DATEI}[art])
    fehler, anzahl = [], 0
    for pfad in weg:
        if not os.path.exists(pfad):
            continue
        erg = papierkorb_verwaltung.wegwerfen(pfad)
        if erg["erfolg"]:
            anzahl += 1
        else:
            fehler.append(erg["fehler"])
    if fehler:
        return {"erfolg": False, "art": art, "fehler": "Nicht alles ließ sich löschen: " + "; ".join(fehler[:3])}
    return {"erfolg": True, "art": art, "anzahl": anzahl}
