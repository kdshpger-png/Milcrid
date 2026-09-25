# online_ki_verwaltung.py
# Online-KI ueber API (Klaus, 15.09.2026): Portal-Bereich "API KI" fuer
# Anbieter und Schluessel, App "Milcrid Online KI" zum Chatten.
#
# Klaus' Vorgaben, auf denen alles hier steht:
#   - Schluessel eintragen mit Schalter "speichern ja/nein":
#       nein -> gilt, bis der PC ausgeht
#       ja   -> verschluesselt gespeichert (tresor.py), nach Neustart wieder da
#   - ZWEI Loesch-Knoepfe: aktiven Schluessel loeschen (= Verbindung kappen)
#     und gespeicherten Schluessel loeschen - unabhaengig voneinander.
#   - Mehrere Anbieter nebeneinander, im Chat waehlt man einen aus.
#   - Im Chat ein Schalter "Verbindung an/aus", beim Start IMMER aus.
#
# Wo was liegt:
#   ~/.config/milcrid/api_schluessel.tresor   gespeicherte Schluessel (verschluesselt)
#   /run/user/<uid>/milcrid/api_aktiv.tresor  aktive Schluessel. /run/user ist
#       ein Arbeitsspeicher-Laufwerk: beim Ausschalten ist es leer. Genau das ist
#       "gilt bis der PC ausgeht" - und ueberlebt trotzdem einen Neustart von
#       main.py mitten am Tag. Ebenfalls verschluesselt.
#   ~/Milcrid/online_ki.json                  Modellwahl, Modelllisten - nichts Geheimes
#   ~/Documents/Online KI Downloads/          gespeicherte Antworten, Code, Chats
#
# Der Schluessel geht nach dem Eintippen nie mehr zurueck ans Portal (nur die
# letzten 4 Zeichen zum Wiedererkennen) und steht nie in einer Adresse, einem
# Log oder der Mitschrift.
#
# Die Verbindung (an/aus) lebt nur im Arbeitsspeicher dieses Prozesses: jeder
# Start von main.py beginnt mit "aus". Die lokale KI soll spaeter ueber
# genau diese Pruefung gehen - was hier aus ist, geht nicht nach draussen.

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

import httpx

import tresor

BASIS_ORDNER = os.path.dirname(os.path.abspath(__file__))
EINSTELLUNGEN_PFAD = os.path.join(BASIS_ORDNER, "online_ki.json")
TRESOR_PFAD = os.path.join(tresor.ORDNER, "api_schluessel.tresor")
_laufzeit_basis = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
LAUFZEIT_PFAD = (os.path.join(_laufzeit_basis, "milcrid", "api_aktiv.tresor")
                 if os.path.isdir(_laufzeit_basis) else None)
ERGEBNIS_ORDNER = os.path.join(os.path.expanduser("~"), "Documents", "Online KI Downloads")

ZEITLIMIT = httpx.Timeout(180.0, connect=15.0)
MAX_DATEI_BYTES = 20 * 1024 * 1024
# Dateien werden als Ganzes mitgeschickt - bei jeder Nachricht erneut, weil die
# API kein Gedaechtnis hat. Gemini nimmt eingebettete Dateien nur bis ~20 MB je
# Anfrage an (Base64 macht daraus ein Drittel mehr).
MAX_ANHAENGE_BYTES = 14 * 1024 * 1024

SYSTEM_TEXT = (
    "Du wirst aus Milcrid heraus benutzt, einem lokalen KI-System auf dem PC des Nutzers. "
    "Antworte in der Sprache, in der der Nutzer schreibt. "
    "Wenn du Code schreibst, setze jeden Code in einen Markdown-Codeblock mit Sprachangabe "
    "(zum Beispiel ```python), damit Milcrid ihn als Datei speichern kann."
)

# ---------------------------------------------------------------------------
# Anbieter
# ---------------------------------------------------------------------------

ANBIETER = {
    "gemini": {
        "name": "Google Gemini",
        "schluessel_holen": "aistudio.google.com → Get API key",
        "getestet": True,
        "vorzug": ["gemini-flash-latest", "flash"],
    },
    "claude": {
        "name": "Anthropic Claude",
        "schluessel_holen": "platform.claude.com → API Keys",
        "getestet": False,
        "vorzug": ["claude-opus-5", "claude-sonnet-5", "opus", "sonnet"],
    },
    "chatgpt": {
        "name": "OpenAI ChatGPT",
        "schluessel_holen": "platform.openai.com → API keys",
        "getestet": False,
        "vorzug": ["gpt-5", "gpt-4.1", "gpt-4o"],
    },
    "mistral": {
        "name": "Mistral",
        "schluessel_holen": "console.mistral.ai → API Keys",
        "getestet": False,
        "vorzug": ["mistral-large-latest", "mistral-medium-latest", "large"],
    },
}


class OnlineKiFehler(Exception):
    """Alles, was der Nutzer als Satz zu lesen bekommt."""


def _anfrage(methode, url, kopf, koerper=None):
    """Die EINZIGE Stelle, die ins Internet geht. Tests ersetzen sie.
    Rueckgabe: (status, antwort-json oder None, rohtext)."""
    try:
        with httpx.Client(timeout=ZEITLIMIT) as client:
            antwort = client.request(methode, url, headers=kopf, json=koerper)
    except httpx.TimeoutException:
        raise OnlineKiFehler("Der Anbieter hat nicht rechtzeitig geantwortet (Zeitüberschreitung).")
    except httpx.HTTPError:
        raise OnlineKiFehler("Keine Verbindung zum Anbieter – ist das Internet da?")
    try:
        daten = antwort.json()
    except Exception:
        daten = None
    return antwort.status_code, daten, antwort.text[:500]


# Ueberlastung beim Anbieter ("high demand", 503) ist meist nach Sekunden
# vorbei - offen seit 16.09.: Milcrid gab sofort auf. Jetzt EIN zweiter
# Versuch, nur beim Senden (nicht beim Schluessel pruefen), nur bei diesen
# Fehlern. 429 (Grenze/Kontingent) NICHT: das wird durch Warten nicht besser.
WIEDERHOLEN_BEI = (502, 503, 504)
WIEDERHOLEN_NACH = 4.0  # Sekunden


def _senden_anfrage(methode, url, kopf, koerper):
    """Wie _anfrage, aber bei Ueberlastung einmal nach kurzer Pause nochmal.
    Ruft _anfrage erst beim Aufruf auf - die Tests ersetzen es."""
    status, daten, roh = _anfrage(methode, url, kopf, koerper)
    if status in WIEDERHOLEN_BEI:
        time.sleep(WIEDERHOLEN_NACH)
        status, daten, roh = _anfrage(methode, url, kopf, koerper)
    return status, daten, roh


def _fehlermeldung(anbieter_id, status, daten, roh, zweiter_versuch=False):
    name = ANBIETER[anbieter_id]["name"]
    text = ""
    if isinstance(daten, dict):
        f = daten.get("error")
        if isinstance(f, dict):
            text = f.get("message") or ""
        elif isinstance(f, str):
            text = f
        text = text or daten.get("message") or daten.get("detail") or ""
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
    text = (text or roh or "").strip().replace("\n", " ")[:300]
    # OpenAI nennt in der Meldung Anfang und Ende des Schluessels
    # ("Incorrect API key provided: sk-abc12***...***wxyz") - das gehoert
    # nicht ins Portal und nicht in die Mitschrift.
    text = re.sub(r"\S*\*{3,}\S*", "(Schlüssel ausgeblendet)", text)
    klein = text.lower()
    # 429 zuerst: die Meldung dazu nennt oft auch den "API key", ist aber
    # kein Schluessel-Problem.
    if status == 429:
        satz = f"{name}: Grenze erreicht – zu viele Anfragen oder Kontingent aufgebraucht. Später noch einmal."
    elif status in (401, 403) or "api key" in klein or "api_key" in klein or "x-api-key" in klein:
        satz = f"{name} nimmt den Schlüssel nicht an (ungültig, gesperrt oder ohne Berechtigung)."
    elif status == 404:
        satz = f"{name} kennt dieses Modell oder diese Adresse nicht."
    elif status == 402 or "credit" in klein or "billing" in klein or "quota" in klein:
        satz = f"{name}: kein Guthaben oder Kontingent für diesen Schlüssel."
    elif status >= 500:
        nochmal = " – auch der zweite Versuch ging nicht" if zweiter_versuch and status in WIEDERHOLEN_BEI else ""
        satz = f"{name} hat gerade selbst ein Problem (Fehler {status}{nochmal}). Später noch einmal."
    else:
        satz = f"{name} hat die Anfrage abgelehnt (Fehler {status})."
    return satz + (f" Meldung des Anbieters: „{text}“" if text else "")


def _gemini_kopf(s):
    return {"x-goog-api-key": s, "Content-Type": "application/json"}


def _claude_kopf(s):
    return {"x-api-key": s, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}


def _bearer_kopf(s):
    return {"Authorization": f"Bearer {s}", "Content-Type": "application/json"}


# Gemini liefert auch Modelle, die im Chat nicht antworten koennen (Bilder,
# Musik, Sprache, Recherche-Agenten ...). Sie standen in der Auswahl (offen
# seit 16.09., Liste vom 21.09.: deep-research, transcribe, omni, lyria,
# nano-banana, antigravity). Gemma-Modelle bleiben - die koennen Chat.
_GEMINI_NICHT_CHAT = re.compile(r"embedding|tts|image|live|audio|aqa|robotics|computer-use|deep-research|"
                                r"transcribe|omni|lyria|nano-banana|antigravity|veo|imagen")


def _gemini_chatfaehig(name):
    return not _GEMINI_NICHT_CHAT.search(name or "")


def _modelle_gemini(s):
    status, daten, roh = _anfrage("GET", "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                                  _gemini_kopf(s))
    if status != 200:
        raise OnlineKiFehler(_fehlermeldung("gemini", status, daten, roh))
    return [m["name"].split("/", 1)[-1] for m in (daten or {}).get("models", [])
            if "generateContent" in (m.get("supportedGenerationMethods") or [])
            and _gemini_chatfaehig(m.get("name", ""))]


def _modelle_claude(s):
    status, daten, roh = _anfrage("GET", "https://api.anthropic.com/v1/models?limit=1000", _claude_kopf(s))
    if status != 200:
        raise OnlineKiFehler(_fehlermeldung("claude", status, daten, roh))
    return [m["id"] for m in (daten or {}).get("data", []) if m.get("id")]


def _modelle_chatgpt(s):
    status, daten, roh = _anfrage("GET", "https://api.openai.com/v1/models", _bearer_kopf(s))
    if status != 200:
        raise OnlineKiFehler(_fehlermeldung("chatgpt", status, daten, roh))
    return [m["id"] for m in (daten or {}).get("data", [])
            if re.match(r"(gpt-|o\d|chatgpt-)", m.get("id", ""))
            and not re.search(r"audio|realtime|tts|transcribe|image|embedding|search|instruct|moderation",
                              m.get("id", ""))]


def _modelle_mistral(s):
    status, daten, roh = _anfrage("GET", "https://api.mistral.ai/v1/models", _bearer_kopf(s))
    if status != 200:
        raise OnlineKiFehler(_fehlermeldung("mistral", status, daten, roh))
    return [m["id"] for m in (daten or {}).get("data", [])
            if (m.get("capabilities") or {}).get("completion_chat", True)
            and not re.search(r"embed|moderation|ocr|transcribe", m.get("id", ""))]


def _teile_gemini(n):
    teile = [{"inlineData": {"mimeType": a["mime"], "data": a["b64"]}} for a in n["anhaenge"] if a["art"] != "text"]
    teile += [{"text": a["text"]} for a in n["anhaenge"] if a["art"] == "text"]
    if n["text"]:
        teile.append({"text": n["text"]})
    return teile


def _senden_gemini(s, modell, verlauf):
    koerper = {
        "systemInstruction": {"parts": [{"text": SYSTEM_TEXT}]},
        "contents": [{"role": "user" if n["rolle"] == "nutzer" else "model", "parts": _teile_gemini(n)}
                     for n in verlauf],
    }
    status, daten, roh = _senden_anfrage(
        "POST", f"https://generativelanguage.googleapis.com/v1beta/models/{modell}:generateContent",
        _gemini_kopf(s), koerper)
    if status != 200:
        raise OnlineKiFehler(_fehlermeldung("gemini", status, daten, roh, zweiter_versuch=True))
    daten = daten or {}
    kandidaten = daten.get("candidates") or []
    if not kandidaten:
        grund = (daten.get("promptFeedback") or {}).get("blockReason", "ohne Angabe")
        raise OnlineKiFehler(f"Gemini hat die Anfrage nicht beantwortet (Grund: {grund}).")
    teile = (kandidaten[0].get("content") or {}).get("parts") or []
    text = "".join(t.get("text", "") for t in teile if not t.get("thought"))
    if not text.strip():
        grund = kandidaten[0].get("finishReason", "ohne Angabe")
        raise OnlineKiFehler(f"Gemini hat eine leere Antwort geschickt (Grund: {grund}).")
    return text


def _senden_claude(s, modell, verlauf):
    nachrichten = []
    for n in verlauf:
        if n["rolle"] == "ki":
            nachrichten.append({"role": "assistant", "content": [{"type": "text", "text": n["text"]}]})
            continue
        bloecke = []
        for a in n["anhaenge"]:
            if a["art"] == "bild":
                bloecke.append({"type": "image", "source": {"type": "base64", "media_type": a["mime"], "data": a["b64"]}})
            elif a["art"] == "pdf":
                bloecke.append({"type": "document",
                                "source": {"type": "base64", "media_type": "application/pdf", "data": a["b64"]}})
            else:
                bloecke.append({"type": "text", "text": a["text"]})
        if n["text"]:
            bloecke.append({"type": "text", "text": n["text"]})
        nachrichten.append({"role": "user", "content": bloecke})
    koerper = {"model": modell, "max_tokens": 16000, "system": SYSTEM_TEXT, "messages": nachrichten}
    status, daten, roh = _senden_anfrage("POST", "https://api.anthropic.com/v1/messages", _claude_kopf(s), koerper)
    if status != 200:
        raise OnlineKiFehler(_fehlermeldung("claude", status, daten, roh, zweiter_versuch=True))
    daten = daten or {}
    if daten.get("stop_reason") == "refusal":
        raise OnlineKiFehler("Claude hat die Anfrage abgelehnt.")
    text = "".join(b.get("text", "") for b in daten.get("content") or [] if b.get("type") == "text")
    if not text.strip():
        raise OnlineKiFehler(f"Claude hat eine leere Antwort geschickt (Grund: {daten.get('stop_reason')}).")
    return text


def _senden_openai_art(anbieter_id, url, s, modell, verlauf):
    nachrichten = [{"role": "system", "content": SYSTEM_TEXT}]
    for n in verlauf:
        if n["rolle"] == "ki":
            nachrichten.append({"role": "assistant", "content": n["text"]})
            continue
        teile = []
        for a in n["anhaenge"]:
            daten_url = f"data:{a['mime']};base64,{a.get('b64', '')}"
            if a["art"] == "bild":
                teile.append({"type": "image_url", "image_url": {"url": daten_url}})
            elif a["art"] == "pdf":
                if anbieter_id == "mistral":
                    raise OnlineKiFehler("Mistral nimmt PDF-Dateien auf diesem Weg nicht an. "
                                         "Bitte als Text- oder Office-Datei senden.")
                teile.append({"type": "file", "file": {"filename": a["name"], "file_data": daten_url}})
            else:
                teile.append({"type": "text", "text": a["text"]})
        if n["text"]:
            teile.append({"type": "text", "text": n["text"]})
        nachrichten.append({"role": "user", "content": teile})
    status, daten, roh = _senden_anfrage("POST", url, _bearer_kopf(s), {"model": modell, "messages": nachrichten})
    if status != 200:
        raise OnlineKiFehler(_fehlermeldung(anbieter_id, status, daten, roh, zweiter_versuch=True))
    wahl = ((daten or {}).get("choices") or [{}])[0].get("message") or {}
    text = wahl.get("content") or ""
    if isinstance(text, list):
        text = "".join(t.get("text", "") for t in text if isinstance(t, dict))
    if not text.strip():
        grund = wahl.get("refusal") or "ohne Angabe"
        raise OnlineKiFehler(f"{ANBIETER[anbieter_id]['name']} hat eine leere Antwort geschickt ({grund}).")
    return text


_MODELLE = {"gemini": _modelle_gemini, "claude": _modelle_claude,
            "chatgpt": _modelle_chatgpt, "mistral": _modelle_mistral}
_SENDEN = {
    "gemini": _senden_gemini,
    "claude": _senden_claude,
    "chatgpt": lambda s, m, v: _senden_openai_art("chatgpt", "https://api.openai.com/v1/chat/completions", s, m, v),
    "mistral": lambda s, m, v: _senden_openai_art("mistral", "https://api.mistral.ai/v1/chat/completions", s, m, v),
}


def standard_modell(anbieter_id, modelle):
    """Aus der Liste des Anbieters ein vernuenftiges Modell vorwaehlen -
    erst genaue Namen, dann Wortteile. Klaus kann es im Bereich API KI aendern."""
    if not modelle:
        return ""
    for wunsch in ANBIETER[anbieter_id]["vorzug"]:
        if wunsch in modelle:
            return wunsch
    for wunsch in ANBIETER[anbieter_id]["vorzug"]:
        treffer = sorted((m for m in modelle if wunsch in m and "lite" not in m and "preview" not in m), reverse=True)
        if treffer:
            return treffer[0]
    return sorted(modelle)[0]


# ---------------------------------------------------------------------------
# Zustand: Einstellungen, gespeicherte und aktive Schluessel, Verbindung, Chat
# ---------------------------------------------------------------------------

_sperre = threading.RLock()
_sende_sperre = threading.Lock()
_fluechtig = {}          # nur falls es /run/user nicht gibt: aktive Schluessel im Arbeitsspeicher
_verbindung = {"offen": False, "anbieter": ""}
_chat = []               # [{rolle, text, anhaenge, anbieter, modell, zeit}]
# Bis zu welchem Eintrag der Chat schon als Datei gespeichert ist - fuer die
# Frage vor Neustart/Ausschalten (Klaus 22.09.: der Chat lebt nur im
# Arbeitsspeicher und war danach einfach weg).
_gespeichert_bis = {"n": 0}


def ungespeichert():
    """Wie viele Nachrichten im Online-KI-Chat noch nicht gespeichert sind -
    fuer die PC-Frage (bridge._pc_frage, Klaus 25.09.2026: "speichern ja/nein
    soll gleich bei Computer, PC Neustart kommen")."""
    return max(0, len(_chat) - _gespeichert_bis["n"])
_beschaeftigt = {"seit": 0.0}


def _einstellungen():
    try:
        with open(EINSTELLUNGEN_PFAD, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except Exception:
        daten = {}
    daten = daten if isinstance(daten, dict) else {}
    daten.setdefault("anbieter", {})
    return daten


def _einstellungen_schreiben(daten):
    zwischen = EINSTELLUNGEN_PFAD + ".neu"
    with open(zwischen, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(zwischen, EINSTELLUNGEN_PFAD)


def _gespeicherte():
    """{anbieter: schluessel} aus dem Tresor. Laesst er sich nicht oeffnen
    (spaeter: Passwort noch nicht eingegeben), gibt es eben keine."""
    try:
        return tresor.Tresor(TRESOR_PFAD).lesen().get("schluessel", {})
    except tresor.TresorFehler:
        return {}


def _laufzeit_lesen():
    if LAUFZEIT_PFAD is None:
        return _fluechtig or None
    try:
        return tresor.Tresor(LAUFZEIT_PFAD).lesen() or None
    except tresor.TresorFehler:
        return None


def _laufzeit_schreiben(inhalt):
    if LAUFZEIT_PFAD is None:
        _fluechtig.clear()
        _fluechtig.update(inhalt)
        return
    tresor.Tresor(LAUFZEIT_PFAD).schreiben(inhalt)


def _aktive():
    """{anbieter: schluessel}, die gerade gelten. Beim ersten Aufruf nach dem
    Einschalten des PCs gibt es die Laufzeit-Datei noch nicht - dann werden
    die gespeicherten Schluessel hineingeholt. Danach nie wieder von selbst:
    wer die Verbindung gekappt hat, soll sie nicht durch einen Neustart von
    main.py zurueckbekommen."""
    with _sperre:
        stand = _laufzeit_lesen()
        if stand is None:
            stand = {"gestartet": time.strftime("%Y-%m-%dT%H:%M:%S"), "schluessel": dict(_gespeicherte())}
            _laufzeit_schreiben(stand)
        return dict(stand.get("schluessel") or {})


def _aktive_setzen(anbieter_id, schluessel):
    with _sperre:
        _aktive()
        stand = _laufzeit_lesen() or {"gestartet": time.strftime("%Y-%m-%dT%H:%M:%S")}
        alle = dict(stand.get("schluessel") or {})
        if schluessel:
            alle[anbieter_id] = schluessel
        else:
            alle.pop(anbieter_id, None)
        stand["schluessel"] = alle
        _laufzeit_schreiben(stand)


def _pruefe_anbieter(anbieter_id):
    if anbieter_id not in ANBIETER:
        raise OnlineKiFehler(f'Unbekannter Anbieter "{anbieter_id}".')


def _ende(schluessel):
    return "…" + schluessel[-4:] if schluessel else ""


def _modelle_anzeigen(anbieter_id, modelle):
    """Auch eine schon gespeicherte Liste (vom letzten Pruefen) filtern -
    sonst verschwaenden die Nicht-Chat-Modelle erst beim naechsten Pruefen."""
    if anbieter_id == "gemini":
        return [m for m in modelle if _gemini_chatfaehig(m)]
    return list(modelle)


def aktueller_anbieter():
    """Mit wem gerade gesprochen wird bzw. wuerde - fuer die Mitschrift, auch
    wenn das Senden scheitert (dann fehlte der Anbieter bisher, offen seit 16.09.)."""
    with _sperre:
        if _verbindung["offen"] and _verbindung["anbieter"]:
            return _verbindung["anbieter"]
        # wie info(): ohne gueltige Auswahl der erste aktive Anbieter
        aktive = _aktive()
        auswahl = _einstellungen().get("auswahl", "")
        return auswahl if auswahl in aktive else next(iter(aktive), "")


def info():
    with _sperre:
        einst = _einstellungen()
        aktive = _aktive()
        gespeichert = _gespeicherte()
        anbieter = []
        for aid, a in ANBIETER.items():
            e = einst["anbieter"].get(aid, {})
            anbieter.append({
                "id": aid, "name": a["name"], "schluessel_holen": a["schluessel_holen"], "getestet": a["getestet"],
                "aktiv": aid in aktive, "gespeichert": aid in gespeichert,
                "ende_aktiv": _ende(aktive.get(aid, "")), "ende_gespeichert": _ende(gespeichert.get(aid, "")),
                "modell": e.get("modell", ""), "modelle": _modelle_anzeigen(aid, e.get("modelle", [])),
                "geprueft": e.get("geprueft", ""),
            })
        if _verbindung["offen"] and _verbindung["anbieter"] not in aktive:
            _verbindung.update(offen=False, anbieter="")
        auswahl = einst.get("auswahl", "")
        if auswahl not in aktive:
            auswahl = next(iter(aktive), "")
        return {
            "anbieter": anbieter,
            "auswahl": auswahl,
            "verbindung": dict(_verbindung),
            "chat": chat_fuer_anzeige(),
            "chat_ungespeichert": max(0, len(_chat) - _gespeichert_bis["n"]),
            "beschaeftigt": bool(_beschaeftigt["seit"]),
            "ordner": ERGEBNIS_ORDNER,
            "bis_pc_aus": LAUFZEIT_PFAD is not None,
            "tresor_art": tresor.Tresor(TRESOR_PFAD).art(),
        }


def _schluessel_bereinigen(schluessel):
    schluessel = (schluessel or "").strip()
    if not schluessel:
        raise OnlineKiFehler("Bitte einen Schlüssel eintragen.")
    if re.search(r"\s", schluessel) or len(schluessel) < 16 or len(schluessel) > 400:
        raise OnlineKiFehler("Das sieht nicht wie ein API-Schlüssel aus (Leerzeichen, zu kurz oder zu lang).")
    return schluessel


def _modelle_merken(anbieter_id, modelle):
    with _sperre:
        einst = _einstellungen()
        e = einst["anbieter"].setdefault(anbieter_id, {})
        e["modelle"] = sorted(modelle)
        if e.get("modell") not in modelle:
            e["modell"] = standard_modell(anbieter_id, modelle)
        e["geprueft"] = time.strftime("%d.%m.%Y %H:%M")
        _einstellungen_schreiben(einst)


def schluessel_eintragen(anbieter_id, schluessel, speichern):
    """Pruefen (Modellliste holen - kostet kein Kontingent), dann aktiv
    setzen und auf Wunsch zusaetzlich verschluesselt speichern. Ein Schluessel,
    den der Anbieter ablehnt, wird nirgends abgelegt."""
    _pruefe_anbieter(anbieter_id)
    schluessel = _schluessel_bereinigen(schluessel)
    modelle = _MODELLE[anbieter_id](schluessel)
    if not modelle:
        raise OnlineKiFehler(f"{ANBIETER[anbieter_id]['name']} nimmt den Schlüssel an, meldet aber kein nutzbares Modell.")
    _modelle_merken(anbieter_id, modelle)
    _aktive_setzen(anbieter_id, schluessel)
    if speichern:
        gespeichert_setzen(anbieter_id, schluessel)
    return {"erfolg": True, "meldung": f"{ANBIETER[anbieter_id]['name']}: Schlüssel angenommen"
            + (", verschlüsselt gespeichert." if speichern else ", gilt bis der PC ausgeht.")}


def gespeichert_setzen(anbieter_id, schluessel):
    with _sperre:
        t = tresor.Tresor(TRESOR_PFAD)
        inhalt = t.lesen()
        alle = dict(inhalt.get("schluessel") or {})
        if schluessel:
            alle[anbieter_id] = schluessel
        else:
            alle.pop(anbieter_id, None)
        t.schreiben({"schluessel": alle} if alle else {})


def aktiven_speichern(anbieter_id):
    """Schalter "speichern" nachtraeglich: den gerade aktiven Schluessel
    in den Tresor legen, ohne ihn neu eintippen zu muessen."""
    _pruefe_anbieter(anbieter_id)
    schluessel = _aktive().get(anbieter_id)
    if not schluessel:
        raise OnlineKiFehler("Es gibt keinen aktiven Schlüssel, der gespeichert werden könnte.")
    gespeichert_setzen(anbieter_id, schluessel)
    return {"erfolg": True, "meldung": "Aktiver Schlüssel verschlüsselt gespeichert."}


def aktiven_loeschen(anbieter_id):
    """= Verbindung kappen. Der gespeicherte Schluessel bleibt (eigener Knopf)."""
    _pruefe_anbieter(anbieter_id)
    with _sperre:
        _aktive_setzen(anbieter_id, "")
        if _verbindung["anbieter"] == anbieter_id:
            _verbindung.update(offen=False, anbieter="")
    return {"erfolg": True, "meldung": f"{ANBIETER[anbieter_id]['name']}: Verbindung getrennt, aktiver Schlüssel gelöscht."}


def gespeicherten_loeschen(anbieter_id):
    _pruefe_anbieter(anbieter_id)
    gespeichert_setzen(anbieter_id, "")
    return {"erfolg": True, "meldung": f"{ANBIETER[anbieter_id]['name']}: gespeicherter Schlüssel gelöscht."}


def gespeicherten_verwenden(anbieter_id):
    """Nach "Verbindung trennen": den gespeicherten Schluessel wieder aktiv
    machen, ohne auf den naechsten PC-Start zu warten."""
    _pruefe_anbieter(anbieter_id)
    schluessel = _gespeicherte().get(anbieter_id)
    if not schluessel:
        raise OnlineKiFehler("Für diesen Anbieter ist kein Schlüssel gespeichert.")
    _aktive_setzen(anbieter_id, schluessel)
    return {"erfolg": True, "meldung": f"{ANBIETER[anbieter_id]['name']}: gespeicherter Schlüssel ist wieder aktiv."}


def pruefen(anbieter_id):
    _pruefe_anbieter(anbieter_id)
    schluessel = _aktive().get(anbieter_id)
    if not schluessel:
        raise OnlineKiFehler("Kein aktiver Schlüssel für diesen Anbieter.")
    modelle = _MODELLE[anbieter_id](schluessel)
    _modelle_merken(anbieter_id, modelle)
    return {"erfolg": True, "meldung": f"Schlüssel gilt, {len(modelle)} Modelle verfügbar."}


def modell_setzen(anbieter_id, modell):
    _pruefe_anbieter(anbieter_id)
    with _sperre:
        einst = _einstellungen()
        e = einst["anbieter"].setdefault(anbieter_id, {})
        if e.get("modelle") and modell not in _modelle_anzeigen(anbieter_id, e["modelle"]):
            raise OnlineKiFehler(f'Das Modell "{modell}" steht nicht in der Liste des Anbieters.')
        e["modell"] = modell
        _einstellungen_schreiben(einst)
    return {"erfolg": True}


def auswahl_setzen(anbieter_id):
    _pruefe_anbieter(anbieter_id)
    with _sperre:
        einst = _einstellungen()
        einst["auswahl"] = anbieter_id
        _einstellungen_schreiben(einst)
        # Wer den Anbieter wechselt, schaltet damit nicht still auf einen
        # anderen Empfaenger um: die Verbindung geht zu.
        if _verbindung["offen"] and _verbindung["anbieter"] != anbieter_id:
            _verbindung.update(offen=False, anbieter="")
    return {"erfolg": True}


def verbindung_setzen(offen, anbieter_id=""):
    with _sperre:
        if not offen:
            _verbindung.update(offen=False, anbieter="")
            return {"erfolg": True}
        _pruefe_anbieter(anbieter_id)
        if anbieter_id not in _aktive():
            raise OnlineKiFehler(f"Für {ANBIETER[anbieter_id]['name']} ist kein Schlüssel aktiv – "
                                 "bitte zuerst im Bereich API KI eintragen.")
        _verbindung.update(offen=True, anbieter=anbieter_id)
        einst = _einstellungen()
        einst["auswahl"] = anbieter_id
        _einstellungen_schreiben(einst)
    return {"erfolg": True}


def darf_senden():
    """(ja/nein, anbieter, grund) - die Pruefung, durch die auch die lokale KI
    spaeter muss."""
    with _sperre:
        if not _verbindung["offen"]:
            return False, "", "Die Verbindung zur Online-KI ist aus."
        if _verbindung["anbieter"] not in _aktive():
            _verbindung.update(offen=False, anbieter="")
            return False, "", "Der Schlüssel ist nicht mehr aktiv."
        return True, _verbindung["anbieter"], ""


# ---------------------------------------------------------------------------
# Dateien
# ---------------------------------------------------------------------------

_BILD = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
_TEXT = {".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".htm", ".css", ".xml", ".log", ".yaml", ".yml",
         ".ini", ".sh", ".toml", ".sql", ".java", ".c", ".cpp", ".h", ".ts", ".php", ".rs", ".go", ".tex"}
_OFFICE_TEXT = {".odt", ".doc", ".docx", ".rtf"}
_OFFICE_TABELLE = {".ods", ".xls", ".xlsx"}
_OFFICE_FOLIEN = {".odp", ".ppt", ".pptx"}


def _office_umwandeln(pfad, ziel_format):
    """LibreOffice ohne Fenster. Eigenes Profil, sonst scheitert es still,
    sobald LibreOffice schon offen ist (bekannte Eigenheit)."""
    programm = shutil.which("soffice") or shutil.which("libreoffice")
    if not programm:
        raise OnlineKiFehler("Für Office-Dateien wird LibreOffice gebraucht – es ist nicht installiert.")
    with tempfile.TemporaryDirectory(prefix="milcrid-onlineki-") as ordner:
        profil = "file://" + os.path.join(ordner, "profil")
        try:
            subprocess.run([programm, f"-env:UserInstallation={profil}", "--headless", "--convert-to", ziel_format,
                            "--outdir", ordner, pfad], capture_output=True, timeout=90, check=False)
        except subprocess.TimeoutExpired:
            raise OnlineKiFehler(f"LibreOffice brauchte zu lange für {os.path.basename(pfad)}.")
        endung = ziel_format.split(":", 1)[0]
        ergebnis = os.path.join(ordner, os.path.splitext(os.path.basename(pfad))[0] + "." + endung)
        if not os.path.exists(ergebnis):
            raise OnlineKiFehler(f"{os.path.basename(pfad)} ließ sich nicht umwandeln.")
        with open(ergebnis, "rb") as f:
            return f.read()


def anhang_lesen(pfad):
    """Datei -> {name, art: bild|pdf|text, mime, b64|text, groesse}. Wird beim
    Senden EINMAL gelesen und im Chat gehalten: aendert oder verschwindet die
    Datei danach, bleibt der Chat trotzdem stimmig."""
    name = os.path.basename(pfad)
    if not os.path.isfile(pfad):
        raise OnlineKiFehler(f"Die Datei {name} gibt es nicht (mehr).")
    groesse = os.path.getsize(pfad)
    if groesse > MAX_DATEI_BYTES:
        raise OnlineKiFehler(f"{name} ist zu groß ({groesse // (1024 * 1024)} MB, höchstens 20 MB).")
    endung = os.path.splitext(name)[1].lower()
    if endung in _BILD:
        with open(pfad, "rb") as f:
            roh = f.read()
        return {"name": name, "art": "bild", "mime": _BILD[endung], "b64": base64.b64encode(roh).decode(), "groesse": len(roh)}
    if endung == ".pdf" or endung in _OFFICE_FOLIEN:
        if endung == ".pdf":
            with open(pfad, "rb") as f:
                roh = f.read()
        else:
            roh = _office_umwandeln(pfad, "pdf")
        return {"name": name, "art": "pdf", "mime": "application/pdf", "b64": base64.b64encode(roh).decode(),
                "groesse": len(roh)}
    if endung in _TEXT:
        with open(pfad, "rb") as f:
            roh = f.read()
    elif endung in _OFFICE_TEXT:
        roh = _office_umwandeln(pfad, "txt:Text (encoded):UTF8")
    elif endung in _OFFICE_TABELLE:
        roh = _office_umwandeln(pfad, "csv:Text - txt - csv (StarCalc):44,34,76,1")
    else:
        raise OnlineKiFehler(f"{name}: diese Dateiart kann Milcrid nicht senden. Möglich sind PDF, Bilder "
                             "(PNG/JPG/WebP), Text- und Code-Dateien und Office-Dateien.")
    inhalt = roh.decode("utf-8", errors="replace")
    return {"name": name, "art": "text", "mime": "text/plain", "groesse": len(roh),
            "text": f"Datei „{name}“:\n```\n{inhalt}\n```"}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

_CODEBLOCK = re.compile(r"```([\w+#.-]*)[^\n]*\n(.*?)```", re.S)


def chat_fuer_anzeige():
    return [{"rolle": n["rolle"], "text": n["text"], "dateien": [a["name"] for a in n["anhaenge"]],
             "anbieter": ANBIETER.get(n["anbieter"], {}).get("name", ""), "modell": n["modell"], "zeit": n["zeit"],
             "code": len(_CODEBLOCK.findall(n["text"])) if n["rolle"] == "ki" else 0}
            for n in _chat]


def senden(text, pfade=None):
    """Eine Nachricht an die Online-KI. Blockiert, bis die Antwort da ist
    (main.py ruft das in einem eigenen Faden). Rueckgabe enthaelt Zeichen-
    und Dateizahlen fuer die Mitschrift - nie den Inhalt."""
    text = (text or "").strip()
    pfade = [p for p in (pfade or []) if p]
    if not text and not pfade:
        raise OnlineKiFehler("Bitte etwas eingeben oder eine Datei anhängen.")
    if not _sende_sperre.acquire(blocking=False):
        raise OnlineKiFehler("Es läuft noch eine Anfrage – bitte die Antwort abwarten.")
    try:
        ok, anbieter_id, grund = darf_senden()
        if not ok:
            raise OnlineKiFehler(grund)
        schluessel = _aktive().get(anbieter_id)
        modell = _einstellungen()["anbieter"].get(anbieter_id, {}).get("modell", "")
        if not modell:
            raise OnlineKiFehler("Für diesen Anbieter ist noch kein Modell gewählt (Bereich API KI).")
        anhaenge = [anhang_lesen(p) for p in pfade]
        gesamt = sum(a["groesse"] for n in _chat for a in n["anhaenge"]) + sum(a["groesse"] for a in anhaenge)
        if gesamt > MAX_ANHAENGE_BYTES:
            raise OnlineKiFehler("Zusammen mit den Dateien, die schon im Chat sind, wird es zu groß (über 14 MB). "
                                 "Mit „Neuer Chat“ neu anfangen.")
        frage = {"rolle": "nutzer", "text": text, "anhaenge": anhaenge, "anbieter": anbieter_id, "modell": modell,
                 "zeit": time.strftime("%H:%M")}
        _beschaeftigt["seit"] = time.time()
        beginn = time.time()
        try:
            antwort = _SENDEN[anbieter_id](schluessel, modell, _chat + [frage])
        finally:
            _beschaeftigt["seit"] = 0.0
        _chat.append(frage)
        _chat.append({"rolle": "ki", "text": antwort, "anhaenge": [], "anbieter": anbieter_id, "modell": modell,
                      "zeit": time.strftime("%H:%M")})
        return {"erfolg": True, "anbieter": anbieter_id, "modell": modell, "zeichen_frage": len(text),
                "dateien": [a["name"] for a in anhaenge], "zeichen_antwort": len(antwort),
                "dauer": round(time.time() - beginn, 1)}
    finally:
        _sende_sperre.release()


def letzte_antwort():
    """Der Wortlaut der letzten Antwort der Online-KI - fuer das Werkzeug
    frage_online_ki in bridge.py. senden() selbst gibt bewusst nur Zahlen
    zurueck (die gehen in die Mitschrift), nie den Inhalt."""
    for n in reversed(_chat):
        if n["rolle"] == "ki":
            return n["text"]
    return ""


def neuer_chat():
    if _sende_sperre.locked():
        raise OnlineKiFehler("Es läuft noch eine Anfrage – bitte die Antwort abwarten.")
    _chat.clear()
    _gespeichert_bis["n"] = 0
    return {"erfolg": True}


def _dateiname(teil):
    return re.sub(r"[^\w.-]+", "_", teil).strip("_")[:60] or "ergebnis"


def _frei(pfad):
    stamm, endung = os.path.splitext(pfad)
    n = 2
    while os.path.exists(pfad):
        pfad = f"{stamm}_{n}{endung}"
        n += 1
    return pfad


_ENDUNGEN = {"python": ".py", "py": ".py", "javascript": ".js", "js": ".js", "typescript": ".ts", "ts": ".ts",
             "html": ".html", "css": ".css", "bash": ".sh", "sh": ".sh", "shell": ".sh", "json": ".json",
             "sql": ".sql", "java": ".java", "c": ".c", "cpp": ".cpp", "c++": ".cpp", "rust": ".rs", "go": ".go",
             "php": ".php", "xml": ".xml", "yaml": ".yaml", "yml": ".yaml", "markdown": ".md", "md": ".md",
             "csv": ".csv", "toml": ".toml", "ini": ".ini"}


def antwort_speichern(index, nur_code=False):
    """Eine Antwort als .md in den Ergebnis-Ordner - oder nur ihre
    Codebloecke, jeder als eigene Datei mit passender Endung."""
    if not (0 <= index < len(_chat)) or _chat[index]["rolle"] != "ki":
        raise OnlineKiFehler("Diese Antwort gibt es nicht mehr.")
    n = _chat[index]
    os.makedirs(ERGEBNIS_ORDNER, exist_ok=True)
    stempel = time.strftime("%Y-%m-%d_%H%M")
    frage = _chat[index - 1]["text"] if index > 0 else ""
    stichwort = _dateiname(" ".join(frage.split()[:5])) if frage else "antwort"
    gespeichert = []
    if nur_code:
        bloecke = _CODEBLOCK.findall(n["text"])
        if not bloecke:
            raise OnlineKiFehler("In dieser Antwort ist kein Codeblock.")
        for nr, (sprache, code) in enumerate(bloecke, 1):
            endung = _ENDUNGEN.get(sprache.lower(), ".txt")
            zusatz = f"_{nr}" if len(bloecke) > 1 else ""
            pfad = _frei(os.path.join(ERGEBNIS_ORDNER, f"{stempel}_{stichwort}{zusatz}{endung}"))
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(code)
            gespeichert.append(pfad)
    else:
        pfad = _frei(os.path.join(ERGEBNIS_ORDNER, f"{stempel}_{stichwort}.md"))
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(f"# Antwort von {ANBIETER[n['anbieter']]['name']} ({n['modell']}), {n['zeit']}\n\n")
            if frage:
                f.write("**Frage:** " + frage + "\n\n---\n\n")
            f.write(n["text"] + "\n")
        gespeichert.append(pfad)
    namen = ", ".join(os.path.basename(p) for p in gespeichert)
    return {"erfolg": True, "dateien": gespeichert, "meldung": f"Gespeichert in „Online KI Downloads“: {namen}"}


def chat_speichern():
    if not _chat:
        raise OnlineKiFehler("Der Chat ist leer.")
    os.makedirs(ERGEBNIS_ORDNER, exist_ok=True)
    pfad = _frei(os.path.join(ERGEBNIS_ORDNER, time.strftime("%Y-%m-%d_%H%M") + "_chat.md"))
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(f"# Online-KI-Chat vom {time.strftime('%d.%m.%Y')}\n\n")
        for n in _chat:
            if n["rolle"] == "nutzer":
                wer = "Ich"
            else:
                wer = f"{ANBIETER[n['anbieter']]['name']} ({n['modell']})"
            f.write(f"## {wer} · {n['zeit']}\n\n")
            if n["anhaenge"]:
                f.write("Dateien: " + ", ".join(a["name"] for a in n["anhaenge"]) + "\n\n")
            f.write(n["text"] + "\n\n")
    _gespeichert_bis["n"] = len(_chat)
    return {"erfolg": True, "dateien": [pfad], "meldung": f"Chat gespeichert: {os.path.basename(pfad)}"}
